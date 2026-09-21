"""Content-aware sharing derivatives preserve source bytes and explicit lineage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from execweave.finalization import record_finalization
from execweave.redacted_archive import (
    DERIVATIVE_FORMAT,
    LINEAGE_FORMAT,
    RedactedArchiveError,
    create_redacted_archive,
    verify_redacted_archive,
)


def _ref(root: Path, raw: bytes, suffix: str, **metadata):
    digest = hashlib.sha256(raw).hexdigest()
    path = f"content/sha256/{digest}.{suffix}"
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {
        "path": path,
        "sha256": digest,
        "size_bytes": len(raw),
        "content_kind": metadata.pop("content_kind", "test.content"),
        "media_type": metadata.pop(
            "media_type",
            "application/json"
            if suffix == "json"
            else "text/plain; charset=utf-8"
            if suffix == "txt"
            else "application/octet-stream",
        ),
        "representation": metadata.pop("representation", "raw_bytes"),
        "complete_from_source": True,
        **metadata,
    }


def source_archive(root: Path):
    text = _ref(root, b"hello SECRET alice@example.com", "txt", content_kind="tool.output")
    data = _ref(
        root,
        json.dumps(
            {
                "user": "alice@example.com",
                "nested": {"token": "SECRET", "safe": True},
                "password": "SECRET",
            },
            sort_keys=True,
        ).encode(),
        "json",
        content_kind="model.response",
    )
    binary = _ref(root, b"\x00SECRET\xff", "bin", content_kind="artifact.snapshot")
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "source-SECRET-run",
        "source_path": "/private/SECRET/events.jsonl",
        "nodes": [
            {
                "id": "agent:SECRET",
                "type": "agent",
                "name": "Alice SECRET",
                "attributes": {"cwd": "/home/SECRET", "hostname": "secret-host"},
            },
            {"id": "text", "type": "observed_content", "attributes": text},
            {"id": "json", "type": "observed_content", "attributes": data},
            {"id": "bin", "type": "observed_content", "attributes": binary},
        ],
        "edges": [
            {
                "id": "edge:SECRET",
                "source": "agent:SECRET",
                "target": "text",
                "relation": "HAS_TOOL_OUTPUT",
            },
        ],
        "note": "contact alice@example.com and keep SECRET private",
    }
    conversations = {"session_id": graph["session_id"], "entries": [text, data, binary]}
    (root / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (root / "conversations.json").write_text(json.dumps(conversations), encoding="utf-8")
    (root / "viewer.html").write_text("<html>source SECRET viewer</html>", encoding="utf-8")
    record_finalization(root, state="complete")
    return graph, {"text": text, "json": data, "binary": binary}


def policy(path: Path):
    value = {
        "format": "execweave.redaction-policy.v1",
        "name": "external sharing",
        "replacement": "[REDACTED]",
        "literals": ["SECRET", "alice@example.com"],
        "json_pointers": ["/nested/token"],
        "redact_keys": ["cwd", "hostname", "password"],
        "binary": "drop",
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def tree_bytes(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_create_redacted_derivative_changes_hashes_preserves_source_and_verifies(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _, refs = source_archive(source)
    before = tree_bytes(source)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    derived = tmp_path / "derived"

    result = create_redacted_archive(source, derived, policy_path)

    assert result["state"] == result["source_state"] == "complete"
    assert result["mapping_count"] == 3
    assert tree_bytes(source) == before
    assert verify_redacted_archive(derived)["source_state"] == "not_checked"
    assert verify_redacted_archive(derived, source_root=source)["source_state"] == "complete"
    report = json.loads((derived / "finalization.json").read_text())
    assert report["state"] == "complete"
    assert report["derivation"]["format"] == DERIVATIVE_FORMAT
    graph = json.loads((derived / "graph.json").read_text())
    assert graph["session_id"].startswith("redacted-") and graph["source_path"] is None
    assert graph["redacted_derivative"]["format"] == DERIVATIVE_FORMAT
    assert graph["nodes"][0]["id"] == "agent:[REDACTED]"
    assert graph["edges"][0]["source"] == "agent:[REDACTED]"
    assert graph["nodes"][0]["attributes"]["cwd"] == "[REDACTED]"
    assert graph["nodes"][0]["attributes"]["hostname"] == "[REDACTED]"
    all_output = b"\n".join(tree_bytes(derived).values())
    assert b"SECRET" not in all_output and b"alice@example.com" not in all_output
    assert refs["text"]["sha256"].encode() in (derived / "lineage.json").read_bytes()


def test_text_json_and_binary_redaction_are_content_addressed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    derived = tmp_path / "derived"
    create_redacted_archive(source, derived, policy_path)
    lineage = json.loads((derived / "lineage.json").read_text())
    assert lineage["format"] == LINEAGE_FORMAT
    assert len(lineage["mappings"]) == 3
    by_suffix = {Path(row["source"]["path"]).suffix: row for row in lineage["mappings"]}
    text = (derived / by_suffix[".txt"]["derived"]["path"]).read_text()
    assert text == "hello [REDACTED] [REDACTED]"
    data = json.loads((derived / by_suffix[".json"]["derived"]["path"]).read_text())
    assert data == {
        "nested": {"safe": True, "token": "[REDACTED]"},
        "password": "[REDACTED]",
        "user": "[REDACTED]",
    }
    assert (derived / by_suffix[".bin"]["derived"]["path"]).read_bytes() == b""
    assert "binary_dropped" in by_suffix[".bin"]["actions"]
    for row in lineage["mappings"]:
        raw = (derived / row["derived"]["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["derived"]["sha256"]
        assert len(raw) == row["derived"]["size_bytes"]


def test_derivative_generation_is_byte_deterministic(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    one, two = tmp_path / "one", tmp_path / "two"
    create_redacted_archive(source, one, policy_path)
    create_redacted_archive(source, two, policy_path)
    assert tree_bytes(one) == tree_bytes(two)


@pytest.mark.parametrize("target", ["lineage.json", "graph.json", "content"])
def test_tampering_never_verifies(tmp_path, target):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    derived = tmp_path / "derived"
    create_redacted_archive(source, derived, policy_path)
    if target == "lineage.json":
        value = json.loads((derived / target).read_text())
        value["policy"]["name"] = "changed"
        (derived / target).write_text(json.dumps(value))
    elif target == "graph.json":
        (derived / target).write_bytes((derived / target).read_bytes() + b" ")
    else:
        lineage = json.loads((derived / "lineage.json").read_text())
        path = lineage["mappings"][0]["derived"]["path"]
        (derived / path).write_bytes(b"tampered")
    with pytest.raises((RedactedArchiveError, Exception)):
        verify_redacted_archive(derived)


def test_source_archive_must_be_complete_and_finalized(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _, refs = source_archive(source)
    (source / refs["text"]["path"]).unlink()
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    with pytest.raises(RedactedArchiveError, match="source_archive_incomplete"):
        create_redacted_archive(source, tmp_path / "derived", policy_path)


def test_identity_collision_after_redaction_fails_closed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    graph = json.loads((source / "graph.json").read_text())
    graph["nodes"].extend(
        [
            {"id": "SECRET-x", "type": "agent", "name": "one"},
            {"id": "[REDACTED]-x", "type": "agent", "name": "two"},
        ]
    )
    (source / "graph.json").write_text(json.dumps(graph))
    record_finalization(source, state="complete")
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    with pytest.raises(RedactedArchiveError, match="identity_collision"):
        create_redacted_archive(source, tmp_path / "derived", policy_path)


def test_destination_is_never_overwritten(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    dest = tmp_path / "derived"
    dest.mkdir()
    (dest / "keep").write_text("keep")
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    with pytest.raises(RedactedArchiveError, match="destination_exists"):
        create_redacted_archive(source, dest, policy_path)
    assert (dest / "keep").read_text() == "keep"


def test_policy_is_bounded_regular_and_reserved_keys_cannot_be_redacted(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    policy_path = tmp_path / "policy.json"
    value = policy(policy_path)
    value["redact_keys"] = ["path"]
    policy_path.write_text(json.dumps(value))
    with pytest.raises(RedactedArchiveError, match="invalid_policy"):
        create_redacted_archive(source, tmp_path / "derived", policy_path)
    policy_path.unlink()
    real = tmp_path / "real-policy"
    policy(real)
    policy_path.symlink_to(real)
    with pytest.raises(RedactedArchiveError, match="unsafe_policy"):
        create_redacted_archive(source, tmp_path / "derived2", policy_path)


def test_source_finalization_link_is_refused(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    original = source / "original-finalization.json"
    (source / "finalization.json").replace(original)
    (source / "finalization.json").symlink_to(original)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    with pytest.raises(RedactedArchiveError, match="unsafe_metadata_file"):
        create_redacted_archive(source, tmp_path / "derived", policy_path)


def test_cli_create_and_verify_are_explicit(tmp_path):
    import subprocess
    import sys

    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    derived = tmp_path / "derived"
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "execweave.redacted_archive",
            "create",
            str(source),
            str(derived),
            "--policy",
            str(policy_path),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0 and json.loads(result.stdout)["source_state"] == "complete"
    checked = subprocess.run(
        [
            sys.executable,
            "-m",
            "execweave.redacted_archive",
            "verify",
            str(derived),
            "--source",
            str(source),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert checked.returncode == 0 and json.loads(checked.stdout)["state"] == "complete"

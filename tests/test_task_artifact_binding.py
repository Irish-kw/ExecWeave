"""Explicitly selected file versions are not proof of executed task checks."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from execweave.task_validation import main
from test_task_validation_reports import graph, receipt, xml


def invoke(tmp_path, *artifacts):
    (tmp_path / "graph.json").write_text(json.dumps(graph()), encoding="utf-8")
    (tmp_path / "tests.xml").write_text(xml(), encoding="utf-8")
    args = [
        "--graph",
        str(tmp_path / "graph.json"),
        "--task-id",
        "task:1",
        "--junit",
        str(tmp_path / "tests.xml"),
        "--validator",
        "Selected QA",
        "--criterion",
        "Selected checks",
        "--output",
        str(tmp_path / "receipt.json"),
    ]
    for item in artifacts:
        args.extend(["--artifact", item])
    return main(args)


def test_cli_binds_selected_artifact_bytes(tmp_path):
    source = tmp_path / "delivered.py"
    source.write_bytes(b"print(42)\n")
    assert invoke(tmp_path, f"src/main.py={source}") == 0
    value = json.loads((tmp_path / "receipt.json").read_text())
    assert value["format"] == "execweave.external-task-report.v2"
    assert value["artifacts"]["entries"] == [
        {
            "path": "src/main.py",
            "size_bytes": 10,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    ]
    assert str(tmp_path) not in json.dumps(value["artifacts"])
    assert value["summary"]["task_success_implied"] is False
    assert source.read_bytes() == b"print(42)\n"


def test_cli_version_changes_with_same_size_file(tmp_path):
    source = tmp_path / "a"
    source.write_bytes(b"aaaa")
    assert invoke(tmp_path, f"a={source}") == 0
    first = json.loads((tmp_path / "receipt.json").read_text())
    (tmp_path / "receipt.json").unlink()
    source.write_bytes(b"bbbb")
    assert invoke(tmp_path, f"a={source}") == 0
    second = json.loads((tmp_path / "receipt.json").read_text())
    assert first["report"] == second["report"]
    assert first["artifacts"]["manifest_sha256"] != second["artifacts"]["manifest_sha256"]


def test_legacy_receipt_without_artifacts_is_unchanged(tmp_path):
    assert invoke(tmp_path) == 0
    value = json.loads((tmp_path / "receipt.json").read_text())
    assert value["format"] == "execweave.external-task-report.v1"
    assert "artifacts" not in value


def test_binding_is_reproducible_and_does_not_mutate_inputs(tmp_path):
    from execweave.task_artifacts import bind_artifacts

    p = tmp_path / "part"
    p.write_bytes(b"\x00\xff")
    original = receipt()
    before = copy.deepcopy(original)
    one = bind_artifacts(original, [f"b={p}", f"a={p}"])
    two = bind_artifacts(original, [f"a={p}", f"b={p}"])
    assert one == two and original == before
    assert [e["path"] for e in one["artifacts"]["entries"]] == ["a", "b"]
    assert one["authority"] == "operator_supplied_not_authenticated"


@pytest.mark.parametrize(
    "name",
    [
        "../a",
        "/a",
        "a//b",
        "a/./b",
        "a/../b",
        "C:/a",
        "a\\b",
        "NUL.txt",
        "dir/COM1",
        "a.",
        "a ",
        "a\x00b",
        "e\u0301.txt",
        "a" * 513,
    ],
    ids=[
        "parent",
        "absolute",
        "empty-part",
        "dot",
        "parent-part",
        "drive",
        "backslash",
        "nul",
        "device",
        "trailing-dot",
        "trailing-space",
        "control",
        "not-nfc",
        "oversized",
    ],
)
def test_unsafe_artifact_names_are_rejected_before_file_reads(tmp_path, name):
    from execweave.task_artifacts import bind_artifacts

    with pytest.raises(ValueError):
        bind_artifacts(receipt(), [f"{name}={tmp_path / 'missing'}"])


@pytest.mark.parametrize(
    "change", ["hash", "size", "bool", "extra-file", "duplicate", "case-collision"]
)
def test_modified_manifest_is_not_a_version_match(tmp_path, change):
    from execweave.task_artifacts import bind_artifacts, validate_manifest

    p = tmp_path / "a"
    p.write_bytes(b"abc")
    m = bind_artifacts(receipt(), [f"a={p}"])["artifacts"]
    if change == "hash":
        m["entries"][0]["sha256"] = "f" * 64
    elif change == "size":
        m["entries"][0]["size_bytes"] = 1
    elif change == "bool":
        m["entries"][0]["size_bytes"] = True
    elif change == "extra-file":
        m["entries"].append({**m["entries"][0], "path": "b"})
    elif change == "duplicate":
        m["entries"].append(dict(m["entries"][0]))
    else:
        m["entries"].append({**m["entries"][0], "path": "A"})
    with pytest.raises(ValueError):
        validate_manifest(m)


def test_unicode_empty_file_and_equals_in_local_path(tmp_path):
    from execweave.task_artifacts import bind_artifacts, validate_manifest

    p = tmp_path / "a=b"
    p.write_bytes(b"")
    m = bind_artifacts(receipt(), [f"成果/報告.txt={p}"])["artifacts"]
    assert validate_manifest(m) == m
    assert m["entries"][0]["size_bytes"] == 0
    assert m["entries"][0]["sha256"] == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("kind", ["directory", "missing", "oversized"])
def test_nonfile_or_unbounded_selection_refused(tmp_path, kind):
    from execweave.task_artifacts import bind_artifacts, MAX_FILE_BYTES

    p = tmp_path / "input"
    if kind == "directory":
        p.mkdir()
    elif kind == "oversized":
        with p.open("wb") as f:
            f.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises((ValueError, OSError)):
        bind_artifacts(receipt(), [f"input={p}"])


def test_cli_does_not_overwrite_receipt_or_follow_report_paths(tmp_path):
    source = tmp_path / "a"
    source.write_bytes(b"abc")
    assert invoke(tmp_path, f"a={source}") == 0
    before = (tmp_path / "receipt.json").read_bytes()
    assert invoke(tmp_path, f"a={source}") == 2
    assert (tmp_path / "receipt.json").read_bytes() == before


def test_duplicate_selection_rejected_even_with_identical_bytes(tmp_path):
    from execweave.task_artifacts import bind_artifacts

    p = tmp_path / "a"
    p.write_bytes(b"abc")
    with pytest.raises(ValueError):
        bind_artifacts(receipt(), [f"a={p}", f"A={p}"])


def test_output_is_not_created_when_artifact_is_missing(tmp_path):
    assert invoke(tmp_path, f"a={tmp_path / 'missing'}") == 2
    assert not (tmp_path / "receipt.json").exists()

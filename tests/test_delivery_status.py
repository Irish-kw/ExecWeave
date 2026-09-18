"""Delivery facts stay scoped and independent of execution/task success."""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import re
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from execweave.delivery_status import summarize_finalization
from execweave.finalization import record_finalization
from execweave.viewer_archive_verifier import ARCHIVE_VERIFIER_JS


def archive(tmp_path, *, content=b"body", extra=False):
    digest = hashlib.sha256(content).hexdigest()
    ref = {"path": f"content/sha256/{digest}.txt", "sha256": digest, "size_bytes": len(content)}
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "delivery-run",
        "source_path": "/recorded/run/events.jsonl",
        "nodes": [
            {"id": "a", "type": "agent", "name": "agent"},
            {"id": "body", "type": "observed_content", "attributes": ref},
        ],
        "edges": [],
    }
    conversations = {"session_id": graph["session_id"], "entries": [ref]}
    (tmp_path / ref["path"]).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / ref["path"]).write_bytes(content)
    (tmp_path / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (tmp_path / "conversations.json").write_text(json.dumps(conversations), encoding="utf-8")
    (tmp_path / "viewer.html").write_text("<html>Recorded viewer</html>", encoding="utf-8")
    report = record_finalization(tmp_path, state="complete")
    if extra:
        (tmp_path / "do-not-read.txt").write_text("unrelated secret", encoding="utf-8")
    return graph, ref, report


def files_from(tmp_path):
    import base64

    return {
        p.relative_to(tmp_path).as_posix(): base64.b64encode(p.read_bytes()).decode("ascii")
        for p in tmp_path.rglob("*")
        if p.is_file()
    }


def node_verify(tmp_path, files, graph, *, limits=None, before=""):
    script = (
        "const {webcrypto}=require('node:crypto');globalThis.crypto=webcrypto;\n"
        + ARCHIVE_VERIFIER_JS
    )
    script += (
        "\nconst input="
        + json.dumps(
            {
                "files": files,
                "scope": {
                    "session_id": graph.get("session_id"),
                    "source_path": graph.get("source_path"),
                },
                "limits": limits or {},
            }
        )
        + ";\n"
    )
    script += (
        """
const files=new Map(Object.entries(input.files).map(([name,body])=>[name,new File([Buffer.from(body,'base64')],name)]));
const controller=new AbortController();
"""
        + before
        + """
(async()=>{try{
const result=await __execweaveArchiveVerifier.verifyArchive(files,input.scope,{signal:controller.signal,limits:input.limits});
console.log(JSON.stringify(result));
}catch(e){console.log(JSON.stringify({state:'not_verified',code:e.code||e.message,location:e.location}))}})();
"""
    )
    path = tmp_path / "verifier.cjs"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["node", str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    return json.loads(result.stdout)


def replace_file(files, name, body, *, repin=True):
    import base64

    raw = body.encode("utf-8") if isinstance(body, str) else body
    files[name] = base64.b64encode(raw).decode("ascii")
    if repin and name in ("graph.json", "conversations.json", "viewer.html"):
        report = json.loads(base64.b64decode(files["finalization.json"]))
        report["artifacts"][name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
        files["finalization.json"] = base64.b64encode(json.dumps(report).encode()).decode("ascii")


def test_real_receipt_is_bounded_and_does_not_change_report(tmp_path):
    _, _, report = archive(tmp_path)
    original = copy.deepcopy(report)
    summary = summarize_finalization(report)
    assert summary["state"] == "complete"
    assert summary["verified_file_count"] == 1 and summary["rechecked_now"] is False
    assert "verified_files" not in summary and "artifacts" not in summary
    assert report == original


@pytest.mark.parametrize(
    "change",
    [
        {"missing": ["viewer.html"]},
        {"artifact_errors": {"viewer.html": "missing_file"}},
        {"schema_version": "future"},
        {"state": "SUCCESS"},
        {"artifacts": {}},
        {"content_integrity": {}},
    ],
)
def test_inconsistent_or_unsupported_receipt_never_passes(tmp_path, change):
    _, _, report = archive(tmp_path)
    report.update(change)
    assert summarize_finalization(report)["state"] != "complete"


@pytest.mark.parametrize(
    "key,value",
    [
        ("verified_file_count", True),
        ("unique_file_count", 10),
        ("errors_truncated", True),
        ("reference_count_truncated", True),
        ("error_count", 1),
        ("verified_files", {}),
        ("state", "incomplete"),
        ("index_files", {}),
        ("scope", "all_telemetry"),
    ],
)
def test_false_complete_content_receipt_stays_unknown(tmp_path, key, value):
    _, _, report = archive(tmp_path)
    report["content_integrity"][key] = value
    assert summarize_finalization(report)["state"] == "unavailable"


@pytest.mark.parametrize("state", ["recording", "exporting", "failed", "incomplete"])
def test_non_success_states_survive_publication(tmp_path, state):
    _, _, report = archive(tmp_path)
    report["state"] = state
    assert summarize_finalization(report)["state"] == state


@pytest.mark.parametrize("kind", ["snapshot", "delta", "noop", "resync"])
def test_receipt_in_all_live_envelopes_without_file_io(tmp_path, monkeypatch, kind):
    from execweave.live_core import _LiveState

    graph, _, report = archive(tmp_path)
    state = _LiveState(graph["session_id"], tmp_path / "events.jsonl")
    state.publish_finalization(report)
    state.finish(graph, final_html="<html></html>")
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("payload must not reread files"))
    after = {"snapshot": None, "delta": 0, "noop": state._update_sequence, "resync": 999}[kind]
    response = state.live_update(after)
    assert response["kind"] == ("snapshot" if kind == "resync" else kind)
    receipt = response["finalization_assessment"]
    assert receipt["state"] == "complete" and receipt["rechecked_now"] is False
    assert receipt["source_path"] == graph["source_path"]
    assert receipt["session_id"] == graph["session_id"]


def test_native_failed_workload_keeps_complete_receipt(tmp_path, monkeypatch):
    from execweave import live_core

    original = live_core._LiveState
    states = []

    class Observe(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

    monkeypatch.setattr(live_core, "_LiveState", Observe)
    result = live_core.run_live(
        [sys.executable, "-c", "raise SystemExit(7)"],
        watch_root=tmp_path,
        output_dir=tmp_path / "run",
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )
    assert result.return_code == 7
    packet = states[0].live_update(None)
    assert packet["run_assessment"]["execution"]["state"] == "failed"
    assert packet["run_assessment"]["task_validation"]["state"] == "unverified"
    assert packet["finalization_assessment"]["state"] == "complete"
    assert "finalization_assessment" not in json.loads(result.graph.read_text())
    assert "finalization_assessment" not in json.loads(
        (result.output_dir / "finalization.json").read_text()
    )


def test_native_http_receipt_requires_auth_and_is_not_cached(tmp_path):
    from execweave.live import _LiveState, _handler_factory

    graph, _, report = archive(tmp_path)
    state = _LiveState(graph["session_id"], tmp_path / "events.jsonl")
    state.publish_finalization(report)
    state.finish(graph, final_html="<html></html>")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(state, "test-secret"))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for token, code in [(None, 401), ("bad", 401), ("test-secret", 200)]:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                connection.request(
                    "GET", "/live.json", headers={"X-ExecWeave-Token": token} if token else {}
                )
                response = connection.getresponse()
                data = response.read()
                assert response.status == code
                if code == 200:
                    assert json.loads(data)["finalization_assessment"]["state"] == "complete"
                    assert "no-store" in response.getheader("Cache-Control", "")
            finally:
                connection.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


@pytest.mark.parametrize("content", [b"", b"hello", b"\x00\xffbinary", "中文𝄞".encode()])
def test_offline_verifier_uses_native_webcrypto_and_all_declared_refs(tmp_path, content):
    graph, _, _ = archive(tmp_path, content=content, extra=True)
    result = node_verify(tmp_path, files_from(tmp_path), graph)
    assert result["state"] == "verified_now"
    assert result["reference_count"] == 2 and result["verified_file_count"] == 1
    assert result["primary_file_count"] == 3


@pytest.mark.parametrize("target", ["graph.json", "conversations.json", "viewer.html", "body"])
def test_offline_missing_file_cannot_pass(tmp_path, target):
    graph, ref, _ = archive(tmp_path)
    files = files_from(tmp_path)
    files.pop(ref["path"] if target == "body" else target)
    assert node_verify(tmp_path, files, graph)["code"] == "missing_file"


@pytest.mark.parametrize("target", ["graph.json", "conversations.json", "viewer.html", "body"])
def test_offline_tampered_file_cannot_pass(tmp_path, target):
    graph, ref, _ = archive(tmp_path)
    files = files_from(tmp_path)
    name = ref["path"] if target == "body" else target
    import base64

    raw = base64.b64decode(files[name])
    replace_file(files, name, b"x" + raw[1:], repin=False)
    assert node_verify(tmp_path, files, graph)["code"] == "hash_mismatch"


@pytest.mark.parametrize("key,value", [("session_id", "different"), ("source_path", "/other/path")])
def test_offline_wrong_run_cannot_pass(tmp_path, key, value):
    graph, _, _ = archive(tmp_path)
    files = files_from(tmp_path)
    graph[key] = value
    assert node_verify(tmp_path, files, graph)["code"] == "run_mismatch"


@pytest.mark.parametrize("key", ["graph.json", "conversations.json", "viewer.html"])
def test_missing_primary_fingerprint_cannot_bypass_hash_check(tmp_path, key):
    graph, _, report = archive(tmp_path)
    files = files_from(tmp_path)
    report["artifacts"].pop(key)
    replace_file(files, "finalization.json", json.dumps(report))
    assert node_verify(tmp_path, files, graph)["code"] == "invalid_receipt"


@pytest.mark.parametrize(
    "body", ['{"x":1,"x":2}', '{"x":1,"\\u0078":2}', '[{"nested":{"a":1,"a":2}}]']
)
def test_duplicate_decoded_json_keys_fail_closed(tmp_path, body):
    graph, _, _ = archive(tmp_path)
    files = files_from(tmp_path)
    replace_file(files, "graph.json", body)
    assert node_verify(tmp_path, files, graph)["code"] == "duplicate_json_key"


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "/etc/passwd",
        "https://example.com/file",
        "content/sha256/" + "0" * 64 + ".txt",
    ],
)
def test_unsafe_and_inconsistent_references_are_not_read(tmp_path, path):
    graph, _, _ = archive(tmp_path)
    files = files_from(tmp_path)
    graph["nodes"][1]["attributes"]["path"] = path
    replace_file(files, "graph.json", json.dumps(graph))
    assert node_verify(tmp_path, files, graph)["code"] == "invalid_reference"


@pytest.mark.parametrize(
    "limits",
    [
        {"fileBytes": 1},
        {"totalBytes": 1},
        {"manifestBytes": 1},
        {"references": 1},
        {"jsonTokens": 1},
    ],
)
def test_safety_limits_never_issue_complete_verdict(tmp_path, limits):
    graph, _, _ = archive(tmp_path)
    assert (
        node_verify(tmp_path, files_from(tmp_path), graph, limits=limits)["code"]
        == "verification_limit"
    )


def test_cancelled_verification_is_not_success(tmp_path):
    graph, _, _ = archive(tmp_path)
    assert (
        node_verify(tmp_path, files_from(tmp_path), graph, before="controller.abort();")["code"]
        == "cancelled"
    )


def test_opaque_and_source_partial_do_not_mean_corrupt_bytes(tmp_path):
    graph, _, _ = archive(tmp_path)
    files = files_from(tmp_path)
    graph["nodes"][1]["attributes"].update(
        complete_from_source=False, representation="opaque_encrypted"
    )
    replace_file(files, "graph.json", json.dumps(graph))
    assert node_verify(tmp_path, files, graph)["state"] == "verified_now"


def test_unknown_schema_never_claims_verified(tmp_path):
    graph, _, report = archive(tmp_path)
    files = files_from(tmp_path)
    report["schema_version"] = "0.1"
    replace_file(files, "finalization.json", json.dumps(report))
    assert node_verify(tmp_path, files, graph)["code"] == "unsupported_receipt"


def test_all_shared_shells_compile_and_inject_once(tmp_path):
    from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html
    from execweave.viewer_projection import render_graph_html

    graph, _, _ = archive(tmp_path)
    for i, html in enumerate(
        [DASHBOARD_HTML, render_static_dashboard_html(graph), render_graph_html(graph)]
    ):
        assert html.count('id="execweave-archive-verifier-script"') == 1
        assert html.count('id="execweave-delivery-status-script"') == 1
        for j, script in enumerate(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)):
            p = tmp_path / f"script-{i}-{j}.js"
            p.write_text(script, encoding="utf-8")
            subprocess.run(["node", "--check", str(p)], check=True, capture_output=True)


def test_index_publishes_scope_without_mutating_graph(tmp_path):
    from execweave.conversation_records import conversation_index_payload

    graph = {
        "session_id": "scope-run",
        "source_path": str(tmp_path / "events.jsonl"),
        "nodes": [],
        "edges": [],
    }
    original = copy.deepcopy(graph)
    payload = conversation_index_payload(graph, tmp_path)
    assert payload["session_id"] == graph["session_id"]
    assert payload["source_path"] == graph["source_path"]
    assert graph == original


def test_offline_expansion_content_is_not_ignored(tmp_path):
    graph, ref, _ = archive(tmp_path)
    files = files_from(tmp_path)
    graph["expansion"] = {"clusters": {"hidden": {"nodes": [graph["nodes"].pop()], "edges": []}}}
    replace_file(files, "graph.json", json.dumps(graph))
    files.pop(ref["path"])
    assert node_verify(tmp_path, files, graph)["code"] == "missing_file"


def test_offline_duplicate_sizes_conflict(tmp_path):
    graph, ref, _ = archive(tmp_path)
    files = files_from(tmp_path)
    replace_file(files, "conversations.json", json.dumps({"entries": [{**ref, "size_bytes": 1}]}))
    assert node_verify(tmp_path, files, graph)["code"] == "conflicting_reference"


def test_cancellation_between_reads_is_not_success(tmp_path):
    graph, _, _ = archive(tmp_path)
    before = """const f=files.get('graph.json'),original=f.arrayBuffer.bind(f);
    f.arrayBuffer=async()=>{const b=await original();controller.abort();return b};"""
    assert node_verify(tmp_path, files_from(tmp_path), graph, before=before)["code"] == "cancelled"

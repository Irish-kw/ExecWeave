"""Regression tests for #110/#111 evidence gaps (original v0.8.35 baseline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.graph import build_execution_graph
from execweave.schema import Entity, RuntimeEvent
from execweave.session_summary import SessionSummary
from execweave.validate import validate_event_stream
from execweave.viewer_agent_panel import _AGENT_PANEL_JS


def _stream(path: Path, versions: list[str]) -> None:
    session = Entity(type="session", id="session:fixed")
    events = [
        RuntimeEvent.create(
            session_id="fixed",
            event_type=event_type,
            relation=relation,
            source=session,
        ).to_dict()
        for event_type, relation in [
            ("session.started", "STARTED_SESSION"),
            ("session.finished", "FINISHED_SESSION"),
        ]
    ]
    for i, event in enumerate(events):
        event["schema_version"] = versions[i]
        event["sequence"] = i + 1
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )


@pytest.mark.parametrize("versions", [
    ["9.9", "9.9"],
    ["0.2", "9.9"],
    ["0.1", "0.1"],
])
def test_unknown_or_mixed_stream_versions_are_rejected(
    tmp_path: Path, versions: list[str],
) -> None:
    path = tmp_path / "stream.jsonl"
    _stream(path, versions)
    for allow_incomplete in (False, True):
        result = validate_event_stream(
            path, require_complete_session=not allow_incomplete
        )
        assert result.valid is False
        assert any("unsupported stream schema version" in error for error in result.errors)
        with pytest.raises(ValueError, match="unsupported stream schema version"):
            build_execution_graph(path, allow_incomplete=allow_incomplete)


def test_0834_current_stream_schema_remains_accepted(tmp_path: Path) -> None:
    path = tmp_path / "stream.jsonl"
    _stream(path, ["0.2", "0.2"])
    assert validate_event_stream(path).valid
    graph = build_execution_graph(path)
    assert graph.source_schema_versions == ["0.2"]


def _handoff(message_id: str, kind: str, recipient: str = "agent:reviewer") -> dict:
    return {
        "session_id": "fixed",
        "event_id": kind + message_id,
        "event_type": kind,
        "relation": kind,
        "source": {"type": "agent", "id": "agent:engineer"},
        "target": {"type": "agent", "id": recipient},
        "attributes": {
            "framework": "rolesdemo",
            "message_id": message_id,
            "sender_agent_id": "agent:engineer",
            "recipient_agent_id": recipient,
            "session_id": "fixed",
        },
    }


def _finish() -> dict:
    return {
        "event_type": "session.finished",
        "event_id": "terminal",
        "timestamp": "2026-10-11T00:00:00Z",
        "attributes": {"return_code": 0},
    }


def test_handoff_missing_receive_is_persisted_as_uncertainty() -> None:
    session = SessionSummary()
    session.observe(_handoff("msg-1", "MESSAGE_SENT"))
    session.observe(_handoff("msg-1", "MESSAGE_RECEIVED"))
    session.observe(_handoff("msg-2", "MESSAGE_SENT"))
    # Do not flag a message still in flight as a terminal observation gap.
    assert "message_receive_not_observed" not in session.observation["reasons"]
    session.observe(_finish())
    assessment = session.observation
    assert assessment["state"] == "observation_incomplete"
    assert "message_receive_not_observed" in assessment["reasons"]
    assert assessment["message_delivery"]["unconfirmed_count"] == 1
    assert assessment["message_delivery"]["unconfirmed"] == [
        {
            "message_id": "msg-2",
            "sender_id": "agent:engineer",
            "recipient_id": "agent:reviewer",
            "state": "receive_not_observed",
        }
    ]
    assert assessment["message_delivery"]["delivery_failure_proven"] is False


def test_handoff_receipt_must_match_message_and_recipient() -> None:
    session = SessionSummary()
    session.observe(_handoff("msg-1", "MESSAGE_SENT"))
    session.observe(_handoff("msg-1", "MESSAGE_RECEIVED", "agent:other"))
    session.observe(_finish())
    assert session.observation["message_delivery"]["unconfirmed_count"] == 1
    assert session.observation["message_delivery"]["unconfirmed"][0]["recipient_id"] == "agent:reviewer"


def test_handoff_matching_receive_clears_unconfirmed_gap() -> None:
    session = SessionSummary()
    session.observe(_handoff("msg-1", "MESSAGE_RECEIVED"))
    session.observe(_handoff("msg-1", "MESSAGE_SENT"))
    session.observe(_finish())
    assert session.observation["message_delivery"]["unconfirmed_count"] == 0
    assert "message_receive_not_observed" not in session.observation["reasons"]


def test_unknown_writer_inspector_never_silently_hides_attribution() -> None:
    assert "a.writer_identity==='unknown'" in _AGENT_PANEL_JS
    assert "add('Writer','unknown" in _AGENT_PANEL_JS
    assert "a.snapshot_state==='not_captured'" in _AGENT_PANEL_JS


def test_exact_framework_model_request_preview_from_recorded_content(tmp_path: Path) -> None:
    """The exact Reviewer MODEL_REQUEST must enter the conversation index."""
    import hashlib

    from execweave.conversation_records import conversation_index_payload

    prompt = "You are a code reviewer. The handoff content is absent."
    payload = prompt.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    relative = f"content/sha256/{digest}.txt"
    archive = tmp_path / relative
    archive.parent.mkdir(parents=True)
    archive.write_bytes(payload)
    agent = "agent:rolesdemo:session:Reviewer"
    content_id = "observed-content:model:sha256:" + digest
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "session",
        "source_path": str(tmp_path / "semantic.jsonl"),
        "nodes": [
            {"id": agent, "type": "agent", "name": "Reviewer",
             "attributes": {"framework": "rolesdemo", "session_id": "session"}},
            {"id": content_id, "type": "observed_content",
             "name": "rolesdemo.model_request",
             "attributes": {
                 "path": relative, "sha256": digest, "size_bytes": len(payload),
                 "content_kind": "rolesdemo.model_request",
                 "media_type": "text/plain; charset=utf-8",
                 "representation": "text",
                 "complete_from_source": True,
             }},
        ],
        "edges": [
            {"id": "request", "source": agent, "target": content_id,
             "relation": "HAS_MODEL_CONTENT", "first_sequence": 1,
             "first_seen": "2026-10-10T17:57:54Z"},
        ],
    }
    result = conversation_index_payload(graph, tmp_path)
    exact = [
        entry for entry in result["entries"]
        if entry["source_id"] == agent
        and entry["relation"] == "HAS_MODEL_CONTENT"
        and entry["content_kind"] == "rolesdemo.model_request"
    ]
    assert len(exact) == 1
    messages = exact[0]["conversation_preview"]["messages"]
    assert any(
        msg["kind"] == "model_request" and msg["phase"] == "request"
        and msg["text"] == prompt
        for msg in messages
    )
    assert "String(entry?.source_id||'')===String(node.id||'')" in _AGENT_PANEL_JS
    assert "message?.kind==='model_request'" in _AGENT_PANEL_JS


def test_file_history_uses_canonical_node_counts_not_shared_edge_counts() -> None:
    """The original #111 Dashboard read ×11 from an edge against file node count 5."""
    assert "const node=rawNode(id)||nodeNamed(id)" in _AGENT_PANEL_JS
    assert "node.event_count" in _AGENT_PANEL_JS
    history = _AGENT_PANEL_JS.split("function fileHistory(id){", 1)[1].split(
        "function reachedBy(id){", 1
    )[0]
    assert "edge?.count" not in history
    assert "edge?.first_seen" not in history


def test_framework_group_must_not_promote_partial_delivery_to_delivered() -> None:
    from test_execution_flow_integrity import _edge, _project
    from test_session_execution_flow import _graph

    graph = _graph("camel")
    for node in graph["nodes"]:
        if node["type"] == "agent":
            node["attributes"]["conversation_scope"] = "framework_agent"
    graph["edges"] = [edge for edge in graph["edges"] if edge["id"] != "reply"]
    graph["edges"].extend([
        _edge("sent", "root", "child", "MESSAGE_SENT", 3),
        _edge("recv", "root", "child", "MESSAGE_RECEIVED", 4),
    ])
    graph["observation_assessment"] = {
        "message_delivery": {
            "unconfirmed": [
                {"message_id": "second", "sender_id": "root",
                 "recipient_id": "child", "state": "receive_not_observed"}
            ]
        }
    }
    projected = _project(graph)
    message = next(
        node for node in projected["nodes"]
        if node.get("attributes", {}).get("viewer_framework_messages")
        and node["attributes"].get("sender_agent_id") == "root"
        and node["attributes"].get("recipient_agent_id") == "child"
    )
    assert message["attributes"]["viewer_message_delivery_state"] == "receive_not_observed"
    assert message["attributes"]["viewer_message_unconfirmed_count"] == 1
    routed = [
        edge for edge in projected["edges"]
        if edge["source"] == message["id"] and edge["target"] == "child"
    ]
    assert len(routed) == 1
    assert routed[0]["relation"] == "ADDRESSED_TO"


def test_integrity_cli_explicitly_reports_unanchored_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    from execweave.integrity_cli import main as integrity_main

    run = tmp_path / "run"
    run.mkdir()
    (run / "graph.json").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    assert integrity_main(["seal", str(run)]) == 0
    sealed = json.loads(capsys.readouterr().out)
    assert sealed["external_anchor_state"] == "unanchored"
    assert sealed["malicious_writer_resistance"] is False
    assert integrity_main(["verify", str(run)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True
    assert verified["external_anchor_state"] == "unanchored"
    assert verified["malicious_writer_resistance"] is False
    assert integrity_main([
        "verify", str(run), "--expected-manifest-body-sha256",
        sealed["manifest_body_sha256"],
    ]) == 0
    matching = json.loads(capsys.readouterr().out)
    assert matching["external_anchor_state"] == "external_digest_match"
    assert integrity_main([
        "verify", str(run), "--expected-manifest-body-sha256", "0" * 64,
    ]) == 1
    mismatching = json.loads(capsys.readouterr().out)
    assert mismatching["external_anchor_state"] == "external_digest_mismatch_or_invalid"


def test_github_external_digest_publisher_checks_target_and_acknowledgement() -> None:
    import urllib.error

    from execweave.external_anchor import publish_github_anchor, github_anchor_text

    digest = "a" * 64
    body = github_anchor_text(digest)
    destination = "https://github.com/Irish-kw/ChatGPT2GrokBot/issues/110#issuecomment-12345"
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self):
            return 201

        def read(self, size):
            return json.dumps({
                "id": 12345, "html_url": destination, "body": body,
            }).encode("utf-8")

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    result = publish_github_anchor(
        "Irish-kw/ChatGPT2GrokBot#110", digest, token="test-isolated-token",
        opener=opener,
    )
    assert result["state"] == "submitted_not_independently_verified"
    assert result["comment_url"] == destination
    assert captured["method"] == "POST"
    assert captured["url"] == (
        "https://api.github.com/repos/Irish-kw/ChatGPT2GrokBot/issues/110/comments"
    )
    assert captured["payload"] == {"body": body}
    assert captured["authorization"] == "Bearer test-isolated-token"
    assert "test-isolated-token" not in json.dumps(result)

    for target in (
        "http://github.com/evil", "owner/repo#0", "owner/repo#1/path",
        "owner/repo#1\nAuthorization: secret",
    ):
        with pytest.raises(ValueError):
            publish_github_anchor(target, digest, token="test-isolated-token", opener=opener)

    class WrongAck(Response):
        def read(self, size):
            return json.dumps({
                "id": 12345, "html_url": destination, "body": "different",
            }).encode("utf-8")

    with pytest.raises(ValueError, match="target/body mismatch"):
        publish_github_anchor(
            "Irish-kw/ChatGPT2GrokBot#110", digest, token="test-isolated-token",
            opener=lambda request, *, timeout: WrongAck(),
        )


def test_external_anchor_cli_requires_local_integrity_and_supports_retry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from execweave.integrity_cli import main as integrity_main

    root = tmp_path / "run"
    root.mkdir()
    graph = root / "graph.json"
    graph.write_text('{"nodes":[],"edges":[]}', encoding="utf-8")

    def submitted(target, digest):
        assert target == "trusted/repo#7"
        assert len(digest) == 64
        return {
            "state": "submitted_not_independently_verified",
            "comment_url": "https://github.com/trusted/repo/issues/7#issuecomment-9",
        }

    monkeypatch.setattr("execweave.integrity_cli.publish_github_anchor", submitted)
    assert integrity_main(["seal", str(root), "--anchor-github", "trusted/repo#7"]) == 0
    sealed = json.loads(capsys.readouterr().out)
    assert sealed["external_anchor_state"] == "submitted_not_independently_verified"
    assert sealed["malicious_writer_resistance"] is False
    assert integrity_main(["anchor", str(root), "--github-target", "trusted/repo#7"]) == 0
    retried = json.loads(capsys.readouterr().out)
    assert retried["status"] == "submitted"

    graph.write_text("tampered", encoding="utf-8")
    assert integrity_main(["anchor", str(root), "--github-target", "trusted/repo#7"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["local_integrity_valid"] is False

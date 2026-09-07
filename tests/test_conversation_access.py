from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

import execweave.live as live_module
from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import claude_conversation_archive_events
from execweave.conversation_records import conversation_record_entries, write_conversation_records
from execweave.viewer_projection import write_graph_html


def _conversation_graph() -> dict[str, object]:
    digest = "a" * 64
    source = {
        "id": "agent:Claude Code",
        "type": "agent",
        "name": "Claude Code",
        "attributes": {"provider": "claude"},
    }
    content = {
        "id": f"observed-content:claude.assistant_final_response:sha256:{digest}",
        "type": "observed_content",
        "name": "claude.assistant_final_response",
        "attributes": {
            "sha256": digest,
            "path": f"content/sha256/{digest}.txt",
            "media_type": "text/plain; charset=utf-8",
            "size_bytes": 12,
            "content_kind": "claude.assistant_final_response",
            "representation": "raw_utf8",
            "complete_from_source": True,
        },
    }
    edge = {
        "id": f"agent:Claude Code--PRODUCED_ASSISTANT_RESPONSE-->{content['id']}",
        "source": source["id"],
        "target": content["id"],
        "relation": "PRODUCED_ASSISTANT_RESPONSE",
        "count": 1,
        "first_seen": "2026-08-28T00:00:00Z",
        "last_seen": "2026-08-28T00:00:00Z",
        "first_sequence": 3,
        "last_sequence": 3,
        "event_ids": ["event-3"],
        "event_types": ["semantic.claude.content.observed"],
        "backends": ["semantic"],
        "attributions": ["claude_hook"],
        "causal": False,
        "inferred": False,
        "identity_exact": None,
        "identity_methods": [],
    }
    return {
        "graph_schema_version": "0.2",
        "session_id": "conversation-test",
        "event_count": 1,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [source, content],
        "edges": [edge],
    }


def test_content_store_streams_provider_file_into_run(tmp_path: Path) -> None:
    provider_file = tmp_path / "provider-transcript.jsonl"
    payload = (b'{"type":"user","text":"hello"}\n' * 5000) + b"tail\n"
    provider_file.write_bytes(payload)
    store = FullFidelityContentStore(tmp_path / "run")

    reference = store.put_file(
        provider_file,
        content_kind="test.conversation_transcript",
        media_type="text/plain; charset=utf-8",
        representation="provider_transcript_jsonl_snapshot",
    )

    assert (store.run_root / reference.path).read_bytes() == payload
    assert reference.size_bytes == len(payload)
    assert reference.path.startswith("content/sha256/")
    assert reference.path.endswith(".txt")


def test_claude_transcripts_are_copied_without_external_path_leak(tmp_path: Path) -> None:
    provider_root = tmp_path / "provider"
    provider_root.mkdir()
    main = provider_root / "session-1.jsonl"
    main.write_text('{"type":"assistant","message":{"content":"main"}}\n', encoding="utf-8")
    child = provider_root / "session-1" / "subagents" / "agent-7.jsonl"
    child.parent.mkdir(parents=True)
    child.write_text('{"type":"assistant","message":{"content":"child"}}\n', encoding="utf-8")
    store = FullFidelityContentStore(tmp_path / "run")

    main_events = claude_conversation_archive_events(
        {"hook_event_name": "SessionEnd", "session_id": "session-1", "transcript_path": str(main)},
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    child_events = claude_conversation_archive_events(
        {
            "hook_event_name": "SubagentStop",
            "session_id": "session-1",
            "agent_id": "7",
            "agent_type": "Explore",
            "transcript_path": str(main),
            "agent_transcript_path": str(child),
        },
        store=store,
        timestamp="2026-08-28T00:00:01Z",
    )

    assert len(main_events) == len(child_events) == 1
    assert main_events[0]["relation"] == "HAS_CONVERSATION_TRANSCRIPT"
    assert child_events[0]["source"]["id"] == "agent:claude:session-1:subagent:7"
    serialized = json.dumps(main_events + child_events, sort_keys=True)
    assert str(provider_root) not in serialized
    for event in main_events + child_events:
        assert (store.run_root / event["target"]["attributes"]["path"]).is_file()


def test_claude_subagent_archive_rejects_arbitrary_transcript_path(tmp_path: Path) -> None:
    provider_root = tmp_path / "provider"
    provider_root.mkdir()
    main = provider_root / "session-1.jsonl"
    main.write_text("{}\n", encoding="utf-8")
    arbitrary = tmp_path / "secret.jsonl"
    arbitrary.write_text("secret\n", encoding="utf-8")

    assert claude_conversation_archive_events(
        {
            "hook_event_name": "SubagentStop",
            "session_id": "session-1",
            "agent_id": "7",
            "transcript_path": str(main),
            "agent_transcript_path": str(arbitrary),
        },
        store=FullFidelityContentStore(tmp_path / "run"),
        timestamp="2026-08-28T00:00:00Z",
    ) == []


def test_antigravity_archives_only_validated_brain_transcript(tmp_path: Path) -> None:
    conversation_id = "conversation-a"
    transcript = (
        tmp_path
        / "antigravity-cli"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{"source":"MODEL","type":"PLANNER_RESPONSE"}\n', encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    payload = {
        "executionNum": 1,
        "terminationReason": "model_stop",
        "error": "",
        "fullyIdle": True,
        "conversationId": conversation_id,
        "workspacePaths": [str(workspace)],
        "transcriptPath": str(transcript),
        "artifactDirectoryPath": str(transcript.parents[3]),
        "modelName": "agy-test",
    }
    store = FullFidelityContentStore(tmp_path / "run")

    events = antigravity_hook_to_content_events(
        payload, hook_event="Stop", store=store, timestamp="2026-08-28T00:00:00Z"
    )
    archived = [event for event in events if event["relation"] == "HAS_CONVERSATION_TRANSCRIPT"]
    assert len(archived) == 1
    assert archived[0]["source"]["id"] == f"agent:antigravity:conversation:{conversation_id}"
    assert str(transcript) not in json.dumps(archived, sort_keys=True)
    assert (store.run_root / archived[0]["target"]["attributes"]["path"]).read_text() == (
        transcript.read_text()
    )

    invalid = dict(payload)
    invalid["transcriptPath"] = str(tmp_path / "arbitrary.jsonl")
    invalid_events = antigravity_hook_to_content_events(
        invalid, hook_event="Stop", store=store, timestamp="2026-08-28T00:00:01Z"
    )
    assert not [event for event in invalid_events if event["relation"] == "HAS_CONVERSATION_TRANSCRIPT"]


def test_conversation_index_and_static_dashboard_use_run_local_links(tmp_path: Path) -> None:
    graph = _conversation_graph()
    digest = "a" * 64
    content_path = tmp_path / "content" / "sha256" / f"{digest}.txt"
    content_path.parent.mkdir(parents=True)
    content_path.write_text("assistant answer", encoding="utf-8")

    entries = conversation_record_entries(graph)
    assert len(entries) == 1
    assert entries[0]["provider"] == "claude"
    assert entries[0]["path"] == f"content/sha256/{digest}.txt"

    json_path, markdown_path = write_conversation_records(graph, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["external_provider_folder_lookup_required"] is False
    assert f"[Open](content/sha256/{digest}.txt)" in markdown_path.read_text(encoding="utf-8")

    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)
    html = viewer.read_text(encoding="utf-8")
    assert "window.__execweaveStaticConversations=" in html
    assert f"content/sha256/{digest}.txt" in html
    assert "Conversation records" not in html
    assert "Open complete conversation index" not in html
    assert (tmp_path / "conversations.md").is_file()
    assert (tmp_path / "conversations.json").is_file()


def test_live_dashboard_includes_conversation_panel_and_authenticated_links() -> None:
    html = live_module._LIVE_HTML
    assert "window.__execweaveAgentPanel" in html
    assert 'id="conversation-records"' not in html
    assert 'id="execweave-conversation-panel"' not in html
    assert (
        "fetch('/conversations.json',{cache:'no-store',headers,signal:controller.signal})"
        in html
    )
    assert "stopConversationPolling" in html
    assert "conversationRefreshController.abort()" in html
    assert "window.__execweaveToken" in live_module._AUTHENTICATED_LIVE_HTML
    assert "X-ExecWeave-Token" in live_module._AUTHENTICATED_LIVE_HTML


def test_live_content_server_auth_and_path_boundaries(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    digest = "b" * 64
    content = tmp_path / "content" / "sha256" / f"{digest}.txt"
    content.parent.mkdir(parents=True)
    content.write_text("stored conversation", encoding="utf-8")
    (tmp_path / "conversations.md").write_text("# index\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("must not serve\n", encoding="utf-8")
    state = live_module._LiveState("s1", event_path)
    token = "test-token"
    server = live_module._LocalThreadingHTTPServer(
        ("127.0.0.1", 0), live_module._handler_factory(state, token)
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(f"{base}/content/sha256/{digest}.txt", timeout=2)
        assert unauthorized.value.code == 401

        with urlopen(f"{base}/content/sha256/{digest}.txt?t={token}", timeout=2) as response:
            assert response.read().decode("utf-8") == "stored conversation"
        with urlopen(f"{base}/conversations.md?t={token}", timeout=2) as response:
            assert response.read().decode("utf-8").splitlines() == ["# index"]

        with pytest.raises(HTTPError) as traversal:
            urlopen(f"{base}/content/../secret.txt?t={token}", timeout=2)
        assert traversal.value.code == 404
        with pytest.raises(HTTPError) as arbitrary:
            urlopen(f"{base}/secret.txt?t={token}", timeout=2)
        assert arbitrary.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import execweave.live as live_module
from execweave.agent_trace import cursor_subagent
from execweave.conversation_records import conversation_record_entries, write_conversation_records
from execweave.viewer_projection import write_graph_html


def _stored_content(
    root: Path,
    *,
    content_kind: str,
    value: object,
) -> dict[str, Any]:
    if isinstance(value, str):
        data = value.encode("utf-8")
        suffix = "txt"
        media_type = "text/plain; charset=utf-8"
    else:
        data = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        suffix = "json"
        media_type = "application/json"
    digest = hashlib.sha256(data).hexdigest()
    relative = f"content/sha256/{digest}.{suffix}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "id": f"observed-content:{content_kind}:sha256:{digest}",
        "type": "observed_content",
        "name": content_kind,
        "attributes": {
            "sha256": digest,
            "path": relative,
            "media_type": media_type,
            "size_bytes": len(data),
            "content_kind": content_kind,
            "representation": "raw_utf8" if suffix == "txt" else "canonical_json",
            "complete_from_source": True,
        },
    }


def _add_content(
    graph: dict[str, Any],
    root: Path,
    *,
    source: dict[str, Any],
    content_kind: str,
    value: object,
    sequence: int,
    relation: str = "OBSERVED_CONVERSATION_CONTENT",
) -> None:
    if source["id"] not in {node["id"] for node in graph["nodes"]}:
        graph["nodes"].append(source)
    content = _stored_content(root, content_kind=content_kind, value=value)
    graph["nodes"].append(content)
    graph["edges"].append(
        {
            "id": f"{source['id']}--{relation}-->{content['id']}:{sequence}",
            "source": source["id"],
            "target": content["id"],
            "relation": relation,
            "count": 1,
            "first_sequence": sequence,
            "last_sequence": sequence,
            "first_seen": f"2026-08-29T00:00:{sequence:02d}Z",
            "last_seen": f"2026-08-29T00:00:{sequence:02d}Z",
        }
    )


def _graph() -> dict[str, Any]:
    return {
        "graph_schema_version": "0.2",
        "session_id": "provider-parity",
        "event_count": 0,
        "node_count": 0,
        "edge_count": 0,
        "nodes": [],
        "edges": [],
    }


def _preview_by_provider(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        preview = entry.get("conversation_preview")
        if isinstance(preview, dict):
            result[str(entry["provider"])] = preview
    return result


def test_provider_neutral_conversation_preview_parity(tmp_path: Path) -> None:
    graph = _graph()
    providers = {
        "claude": {
            "source": {
                "id": "agent:Claude Code",
                "type": "agent",
                "name": "Claude Code",
                "attributes": {"provider": "claude"},
            },
            "user_kind": "claude.user_prompt",
            "user": "claude user",
            "assistant_kind": "claude.assistant_final_response",
            "assistant": "claude answer",
        },
        "cursor": {
            "source": {
                "id": "agent:Cursor",
                "type": "agent",
                "name": "Cursor",
                "attributes": {"provider": "cursor"},
            },
            "user_kind": "cursor.prompt_submission_candidate",
            "user": "cursor user",
            "assistant_kind": "cursor.assistant_response",
            "assistant": "cursor answer",
        },
        "opencode": {
            "source": {
                "id": "agent:OpenCode",
                "type": "agent",
                "name": "OpenCode",
                "attributes": {"provider": "opencode"},
            },
            "user_kind": "opencode.user_message",
            "user": {"role": "user", "content": "opencode user"},
            "assistant_kind": "opencode.completed_text",
            "assistant": "opencode answer",
        },
        "anthropic": {
            "source": {
                "id": "inference-request:anthropic:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"provider_name": "anthropic"},
            },
            "user_kind": "anthropic.request_messages",
            "user": [{"role": "user", "content": "anthropic user"}],
            "assistant_kind": "anthropic.assistant_content_blocks",
            "assistant": [{"type": "text", "text": "anthropic answer"}],
        },
        "openrouter": {
            "source": {
                "id": "inference-request:openrouter:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"gateway": "openrouter"},
            },
            "user_kind": "inference_gateway.openrouter.request_messages",
            "user": [{"role": "user", "content": "openrouter user"}],
            "assistant_kind": "inference_gateway.openrouter.response",
            "assistant": {
                "choices": [{"message": {"role": "assistant", "content": "openrouter answer"}}]
            },
        },
        "litellm": {
            "source": {
                "id": "inference-request:litellm:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"gateway": "litellm"},
            },
            "user_kind": "inference_gateway.litellm.request_messages",
            "user": [{"role": "user", "content": "litellm user"}],
            "assistant_kind": "inference_gateway.litellm.response_object",
            "assistant": {
                "choices": [{"message": {"role": "assistant", "content": "litellm answer"}}]
            },
        },
        "ollama": {
            "source": {
                "id": "inference-request:ollama:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"provider": "ollama"},
            },
            "user_kind": "model_runtime.ollama.request_messages",
            "user": [{"role": "user", "content": "ollama user"}],
            "assistant_kind": "model_runtime.ollama.assistant_messages",
            "assistant": [{"role": "assistant", "content": "ollama answer"}],
        },
        "llamacpp": {
            "source": {
                "id": "inference-request:llamacpp:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"provider": "llamacpp"},
            },
            "user_kind": "model_runtime.llamacpp.request_messages",
            "user": [{"role": "user", "content": "llamacpp user"}],
            "assistant_kind": "model_runtime.llamacpp.assistant_messages",
            "assistant": [{"role": "assistant", "content": "llamacpp answer"}],
        },
        "vllm": {
            "source": {
                "id": "inference-request:vllm:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"provider": "vllm"},
            },
            "user_kind": "model_runtime.vllm.request_messages",
            "user": [{"role": "user", "content": "vllm user"}],
            "assistant_kind": "model_runtime.vllm.assistant_messages",
            "assistant": [{"role": "assistant", "content": "vllm answer"}],
        },
        "lmstudio": {
            "source": {
                "id": "inference-request:lmstudio:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"provider": "lmstudio"},
            },
            "user_kind": "model_runtime.lmstudio.request_messages",
            "user": [{"role": "user", "content": "lmstudio user"}],
            "assistant_kind": "model_runtime.lmstudio.assistant_messages",
            "assistant": [{"role": "assistant", "content": "lmstudio answer"}],
        },
        "openai-compatible": {
            "source": {
                "id": "inference-request:openai-compatible:1",
                "type": "inference_request",
                "name": "1",
                "attributes": {"protocol": "openai_compatible"},
            },
            "user_kind": "openai_compatible.request_messages",
            "user": [{"role": "user", "content": "compatible user"}],
            "assistant_kind": "openai_compatible.assistant_messages",
            "assistant": [{"role": "assistant", "content": "compatible answer"}],
        },
    }

    sequence = 1
    for item in providers.values():
        _add_content(
            graph,
            tmp_path,
            source=item["source"],
            content_kind=item["user_kind"],
            value=item["user"],
            sequence=sequence,
        )
        sequence += 1
        _add_content(
            graph,
            tmp_path,
            source=item["source"],
            content_kind=item["assistant_kind"],
            value=item["assistant"],
            sequence=sequence,
        )
        sequence += 1

    entries = conversation_record_entries(graph, tmp_path)
    previews = _preview_by_provider(entries)
    assert set(previews) == set(providers)

    required_preview_fields = {
        "thread_id",
        "parent_thread_id",
        "agent_path",
        "agent_label",
        "provider_label",
        "is_root",
        "message_count",
        "messages_truncated",
        "messages",
    }
    required_message_fields = {
        "timestamp",
        "ordinal",
        "kind",
        "sender",
        "recipient",
        "text",
        "content_state",
        "phase",
        "task_name",
    }
    for provider, preview in previews.items():
        assert required_preview_fields <= set(preview)
        assert preview["agent_path"] == "/root", provider
        assert preview["is_root"] is True, provider
        assert preview["message_count"] == 2, provider
        assert len(preview["messages"]) == 2, provider
        assert all(required_message_fields <= set(message) for message in preview["messages"])
        assert preview["messages"][0]["sender"] == "user", provider

    assert previews["cursor"]["messages"][0]["kind"] == "user_prompt_candidate"
    assert previews["anthropic"]["provider_label"] == "Anthropic"
    assert previews["openrouter"]["provider_label"] == "OpenRouter"
    assert previews["litellm"]["provider_label"] == "LiteLLM"
    assert previews["ollama"]["provider_label"] == "Ollama"
    assert previews["llamacpp"]["provider_label"] == "llama.cpp"
    assert previews["vllm"]["provider_label"] == "vLLM"
    assert previews["lmstudio"]["provider_label"] == "LM Studio"
    assert previews["openai-compatible"]["provider_label"] == "OpenAI-compatible"


def test_archived_transcripts_project_to_same_schema(tmp_path: Path) -> None:
    graph = _graph()
    claude = {
        "id": "agent:Claude Code",
        "type": "agent",
        "name": "Claude Code",
        "attributes": {"provider": "claude"},
    }
    claude_transcript = (
        '{"type":"user","message":{"role":"user","content":"transcript user"}}\n'
        '{"type":"assistant","message":{"role":"assistant","content":"transcript answer"}}\n'
    )
    _add_content(
        graph,
        tmp_path,
        source=claude,
        content_kind="claude.conversation_transcript.main",
        value=claude_transcript,
        sequence=1,
        relation="HAS_CONVERSATION_TRANSCRIPT",
    )

    antigravity = {
        "id": "agent:antigravity:conversation:conversation-a",
        "type": "agent",
        "name": "Antigravity conversation",
        "attributes": {
            "provider": "antigravity",
            "conversation_id": "conversation-a",
            "identity_semantics": "provider_conversation_id",
        },
    }
    antigravity_transcript = (
        '{"source":"USER","type":"USER_MESSAGE","content":"antigravity user"}\n'
        '{"source":"MODEL","type":"PLANNER_RESPONSE","content":"antigravity answer"}\n'
    )
    _add_content(
        graph,
        tmp_path,
        source=antigravity,
        content_kind="antigravity.conversation_transcript",
        value=antigravity_transcript,
        sequence=2,
        relation="HAS_CONVERSATION_TRANSCRIPT",
    )

    previews = _preview_by_provider(conversation_record_entries(graph, tmp_path))
    assert previews["claude"]["is_root"] is True
    assert [m["text"] for m in previews["claude"]["messages"]] == [
        "transcript user",
        "transcript answer",
    ]
    assert previews["antigravity"]["is_root"] is True
    assert [m["text"] for m in previews["antigravity"]["messages"]] == [
        "antigravity user",
        "antigravity answer",
    ]


def test_subagent_preview_uses_same_parent_child_contract(tmp_path: Path) -> None:
    graph = _graph()
    root = {
        "id": "agent:Cursor",
        "type": "agent",
        "name": "Cursor",
        "attributes": {"provider": "cursor"},
    }
    child = cursor_subagent(
        {
            "session_id": "session-1",
            "subagent_id": "child-1",
            "subagent_type": "Explore",
        }
    )
    assert child is not None
    _add_content(
        graph,
        tmp_path,
        source=root,
        content_kind="cursor.assistant_response",
        value="root answer",
        sequence=1,
    )
    _add_content(
        graph,
        tmp_path,
        source=child,
        content_kind="cursor.subagent_summary",
        value="child summary",
        sequence=2,
    )
    previews = [
        entry["conversation_preview"]
        for entry in conversation_record_entries(graph, tmp_path)
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    root_preview = next(preview for preview in previews if preview["is_root"])
    child_preview = next(preview for preview in previews if not preview["is_root"])
    assert root_preview["thread_id"] == "cursor:root"
    assert child_preview["parent_thread_id"] == "cursor:root"
    assert child_preview["agent_path"].startswith("/root/")
    assert child_preview["messages"][0]["recipient"] == "/root"
    assert child_preview["topology_state"] == "provider_reported"
    assert child_preview["agent_path_source"] == "execweave_derived"
    assert child_preview["parent_relation_source"] == "provider_subagent_lifecycle_hook"


def test_dashboard_copy_and_root_detection_are_provider_neutral(tmp_path: Path) -> None:
    html = live_module._LIVE_HTML
    for root_id in (
        "agent:Claude Code",
        "agent:OpenAI Codex",
        "agent:Codex",
        "agent:Cursor",
        "agent:OpenCode",
        "agent:Antigravity",
    ):
        assert root_id in html
    # Provider neutrality is a data/index contract, not visible dashboard copy.
    assert "window.__execweaveAgentPanel" in html
    assert "Open raw conversation evidence" not in html
    assert "provider-neutral run-local record" not in html
    assert "not exposed by the Codex rollout" not in html

    graph = _graph()
    source = {
        "id": "agent:Claude Code",
        "type": "agent",
        "name": "Claude Code",
        "attributes": {"provider": "claude"},
    }
    _add_content(
        graph,
        tmp_path,
        source=source,
        content_kind="claude.assistant_final_response",
        value="visible answer",
        sequence=1,
    )
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)
    rendered = viewer.read_text(encoding="utf-8")
    assert "window.__execweaveStaticConversations=" in rendered
    assert "window.__execweaveAgentPanel" in rendered
    assert "Open raw conversation evidence" not in rendered
    assert "provider-neutral run-local evidence" not in rendered
    assert "not exposed by the Codex rollout" not in rendered


def test_conversation_index_schema_marks_provider_neutral_projection(tmp_path: Path) -> None:
    graph = _graph()
    source = {
        "id": "agent:OpenCode",
        "type": "agent",
        "name": "OpenCode",
        "attributes": {"provider": "opencode"},
    }
    _add_content(
        graph,
        tmp_path,
        source=source,
        content_kind="opencode.completed_text",
        value="done",
        sequence=1,
    )
    json_path, markdown_path = write_conversation_records(graph, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.3"
    assert payload["scope"] == "run_local_provider_neutral_conversation_projection"
    assert payload["visible_message_count"] == 1
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "provider-neutral visible conversation projection" in markdown
    assert "OpenCode" in markdown

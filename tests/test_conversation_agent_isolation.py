from __future__ import annotations

from execweave.conversation_records import _merge_conversation_previews


def _entry(
    provider: str,
    source_id: str,
    agent_path: str,
    text: str,
    *,
    thread_id: str = "shared-thread",
    parent_thread_id: str | None = None,
    sequence: int = 1,
) -> dict:
    return {
        "provider": provider,
        "source_id": source_id,
        "path": f"content/{source_id}.json",
        "size_bytes": len(text),
        "last_sequence": sequence,
        "conversation_preview": {
            "thread_id": thread_id,
            "parent_thread_id": parent_thread_id,
            "agent_path": agent_path,
            "agent_label": agent_path,
            "provider_label": provider,
            "is_root": agent_path == "/root",
            "messages": [
                {
                    "timestamp": f"2026-08-29T00:00:0{sequence}Z",
                    "ordinal": sequence,
                    "kind": "assistant_message",
                    "sender": agent_path,
                    "recipient": None,
                    "text": text,
                    "content_state": "plaintext",
                    "phase": "response",
                    "task_name": None,
                }
            ],
        },
    }


def _rich(entries: list[dict]) -> list[dict]:
    return [entry["conversation_preview"] for entry in entries if "conversation_preview" in entry]


def test_multi_agent_providers_never_merge_different_agent_paths() -> None:
    for provider in ("codex", "claude", "cursor", "opencode", "antigravity"):
        entries = [
            _entry(provider, "root", "/root", "root-private", sequence=1),
            _entry(
                provider,
                "agent-1",
                "/root/agent-1",
                "agent-1-private",
                parent_thread_id="shared-thread",
                sequence=2,
            ),
            _entry(
                provider,
                "agent-2",
                "/root/agent-2",
                "agent-2-private",
                parent_thread_id="shared-thread",
                sequence=3,
            ),
        ]

        _merge_conversation_previews(entries)

        previews = _rich(entries)
        assert len(previews) == 3
        by_path = {preview["agent_path"]: preview for preview in previews}
        assert set(by_path) == {"/root", "/root/agent-1", "/root/agent-2"}
        assert [message["text"] for message in by_path["/root"]["messages"]] == [
            "root-private"
        ]
        assert [
            message["text"] for message in by_path["/root/agent-1"]["messages"]
        ] == ["agent-1-private"]
        assert [
            message["text"] for message in by_path["/root/agent-2"]["messages"]
        ] == ["agent-2-private"]

        thread_ids = {preview["thread_id"] for preview in previews}
        assert len(thread_ids) == 3
        assert by_path["/root/agent-1"]["parent_thread_id"] == by_path["/root"]["thread_id"]
        assert by_path["/root/agent-2"]["parent_thread_id"] == by_path["/root"]["thread_id"]


def test_single_root_request_response_providers_still_merge_incrementally() -> None:
    for provider in (
        "gemini",
        "anthropic",
        "openrouter",
        "litellm",
        "ollama",
        "llamacpp",
        "vllm",
        "lmstudio",
        "openai-compatible",
    ):
        entries = [
            _entry(provider, "root-a", "/root", "first", thread_id=f"{provider}:root", sequence=1),
            _entry(provider, "root-b", "/root", "second", thread_id=f"{provider}:root", sequence=2),
        ]

        _merge_conversation_previews(entries)

        previews = _rich(entries)
        assert len(previews) == 1
        preview = previews[0]
        assert preview["agent_path"] == "/root"
        assert preview["thread_id"] == f"{provider}:root"
        assert [message["text"] for message in preview["messages"]] == ["first", "second"]

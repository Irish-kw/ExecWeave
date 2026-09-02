from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from .agent_topology import (
    EVIDENCE_CROSS_AGENT_ROUTING,
    PATH_EXECWEAVE_DERIVED,
    PATH_PROVIDER_DECLARED,
    THREAD_ID_EXECWEAVE_DERIVED,
    THREAD_ID_PROVIDER_NATIVE,
)

_MAX_IDENTITY_SCAN_LINES = 64
_MAX_PREVIEW_MESSAGES = 80
_MAX_PREVIEW_TEXT_CHARS = 6000


def _canonical_absolute_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _codex_sessions_root() -> Path:
    configured = os.environ.get("CODEX_HOME")
    home = Path(configured).expanduser() if configured else Path.home() / ".codex"
    return (home / "sessions").resolve(strict=False)


def _inside_codex_sessions(path: Path) -> bool:
    try:
        path.relative_to(_codex_sessions_root())
    except ValueError:
        return False
    return True


def _history_base_end_ordinal(payload: dict[str, Any]) -> int:
    history_base = payload.get("history_base")
    if not isinstance(history_base, dict):
        return 0
    value = history_base.get("end_ordinal_exclusive")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _session_meta_identity(payload: dict[str, Any]) -> dict[str, Any] | None:
    thread_id = payload.get("id") or payload.get("session_id")
    if not isinstance(thread_id, str) or not thread_id:
        return None
    source = payload.get("source")
    spawn: dict[str, Any] = {}
    if isinstance(source, dict):
        subagent = source.get("subagent")
        if isinstance(subagent, dict):
            candidate = subagent.get("thread_spawn")
            if isinstance(candidate, dict):
                spawn = candidate
    agent_path = payload.get("agent_path") or spawn.get("agent_path")
    nickname = payload.get("agent_nickname") or spawn.get("agent_nickname")
    parent_thread_id = payload.get("parent_thread_id") or spawn.get("parent_thread_id")
    history_start = payload.get("subagent_history_start_ordinal")
    return {
        "thread_id": thread_id,
        "parent_thread_id": parent_thread_id if isinstance(parent_thread_id, str) else None,
        "agent_path": agent_path if isinstance(agent_path, str) else None,
        "agent_nickname": nickname if isinstance(nickname, str) else None,
        "history_base_end_ordinal": _history_base_end_ordinal(payload),
        "subagent_history_start_ordinal": (
            history_start
            if isinstance(history_start, int) and not isinstance(history_start, bool) and history_start >= 0
            else None
        ),
    }


def _sanitize_path_leaf(value: str) -> str | None:
    leaf = " ".join(value.replace("\\", "-").replace("/", "-").split())
    return leaf or None


def _resolved_agent_path(identity: dict[str, Any]) -> tuple[str | None, str]:
    """Prefer Codex's own path; otherwise /root/<nickname> when a parent exists.

    Windows Codex sessions in the field have been observed to publish nickname and
    parent_thread_id without agent_path. The dashboard child-round splitter addresses
    messages by recipient === path, so a missing path drops every later fold.
    """
    declared = identity.get("agent_path")
    if isinstance(declared, str) and declared:
        return declared, PATH_PROVIDER_DECLARED
    if identity.get("parent_thread_id") is None:
        return "/root", PATH_EXECWEAVE_DERIVED
    nickname = identity.get("agent_nickname")
    if not isinstance(nickname, str):
        return None, PATH_EXECWEAVE_DERIVED
    leaf = _sanitize_path_leaf(nickname)
    if leaf is None:
        return None, PATH_EXECWEAVE_DERIVED
    return f"/root/{leaf}", PATH_EXECWEAVE_DERIVED


def codex_rollout_identity(path: str | Path) -> dict[str, Any] | None:
    """Read only leading Codex session metadata needed for exact thread identity."""
    source = Path(path).expanduser().resolve(strict=False)
    try:
        with source.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= _MAX_IDENTITY_SCAN_LINES:
                    break
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                return _session_meta_identity(payload) if isinstance(payload, dict) else None
    except (OSError, RuntimeError, UnicodeError):
        return None
    return None


def _transcript_candidate(payload: dict[str, Any]) -> tuple[Path, str, str] | None:
    """Select the rollout a Codex hook payload actually describes.

    Codex reports a subagent stop with two different rollouts on one payload:
    ``agent_transcript_path`` is the spawned child rollout while ``transcript_path``
    keeps pointing at the parent session rollout. Selecting the parent for a child
    stop silently drops every subagent conversation, so pick by observed agent id.
    """
    agent_id = payload.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        for field in ("agent_transcript_path", "transcript_path"):
            path = _canonical_absolute_path(payload.get(field))
            if path is not None and path.stem.endswith(f"-{agent_id}"):
                return path, agent_id, field
        return None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    path = _canonical_absolute_path(payload.get("transcript_path"))
    if path is None or not path.stem.endswith(f"-{session_id}"):
        return None
    return path, session_id, "transcript_path"


def codex_transcript_observed_field(payload: dict[str, Any]) -> str | None:
    """Name the payload field a validated Codex rollout was actually observed on."""
    candidate = _transcript_candidate(payload)
    return candidate[2] if candidate is not None else None


def validated_codex_transcript(payload: dict[str, Any]) -> tuple[Path, dict[str, Any]] | None:
    """Validate a hook-supplied rollout path before ExecWeave reads or copies it."""
    candidate = _transcript_candidate(payload)
    if candidate is None:
        return None
    path, expected, _field = candidate
    if path.suffix.lower() != ".jsonl" or not path.name.startswith("rollout-"):
        return None
    if not _inside_codex_sessions(path) or not path.is_file():
        return None
    identity = codex_rollout_identity(path)
    if identity is None or identity.get("thread_id") != expected:
        return None
    agent_id = payload.get("agent_id")
    session_id = payload.get("session_id")
    if isinstance(agent_id, str) and agent_id and isinstance(session_id, str) and session_id:
        parent = identity.get("parent_thread_id")
        if isinstance(parent, str) and parent and parent != session_id:
            return None
    return path, identity


def codex_rollout_identity_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    validated = validated_codex_transcript(payload)
    return validated[1] if validated is not None else None


def _content_text(content: object) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") not in {"input_text", "output_text", "Text"}:
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts).strip()


def _trim_text(value: str) -> str:
    if len(value) <= _MAX_PREVIEW_TEXT_CHARS:
        return value
    return value[: _MAX_PREVIEW_TEXT_CHARS - 1] + "…"


def _agent_message_header(text: str) -> dict[str, str]:
    """Parse Codex routing headers only from an explicit Payload envelope.

    Plain agent output is free-form text and may legitimately quote lines such as
    ``Sender:`` or ``Task name:``. Those strings are routing metadata only when a
    standalone ``Payload:`` line terminates a recognized header block.
    """
    lines = text.splitlines()
    try:
        payload_index = next(index for index, line in enumerate(lines) if line.strip() == "Payload:")
    except StopIteration:
        return {}
    result: dict[str, str] = {}
    for line in lines[:payload_index]:
        key, separator, value = line.partition(":")
        if not separator:
            continue
        normalized = key.strip().lower().replace(" ", "_")
        if normalized in {"message_type", "task_name", "sender"} and value.strip():
            result[normalized] = value.strip()
    if not result:
        return {}
    payload_text = "\n".join(lines[payload_index + 1 :]).strip()
    if payload_text:
        result["payload_text"] = payload_text
    return result


def _agent_message_visible_text(text: str, header: dict[str, str]) -> str | None:
    """Return provider plaintext while stripping only a validated routing envelope."""
    payload = header.get("payload_text")
    if isinstance(payload, str) and payload:
        return _trim_text(payload)
    return _trim_text(text) if text else None


def _message(timestamp: object, ordinal: object, **fields: Any) -> dict[str, Any]:
    return {
        "timestamp": timestamp if isinstance(timestamp, str) else None,
        "ordinal": ordinal if isinstance(ordinal, int) and not isinstance(ordinal, bool) else None,
        **fields,
    }


def _parent_agent_path(identity: dict[str, Any], agent_path: str | None) -> str | None:
    if identity.get("parent_thread_id") is None:
        return None
    if isinstance(agent_path, str) and agent_path.startswith("/root/"):
        parent = agent_path.rsplit("/", 1)[0]
        if parent:
            return parent
    return "/root"


def _rollout_ordinal(record: dict[str, Any], projected_ordinal: int) -> tuple[int, int]:
    explicit = record.get("ordinal")
    if isinstance(explicit, int) and not isinstance(explicit, bool) and explicit >= 0:
        return explicit, explicit + 1
    return projected_ordinal, projected_ordinal + 1


def _spawn_target_path(output: object) -> str | None:
    """Read the agent path Codex returns from a collaboration spawn tool call."""
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return None
    if not isinstance(output, dict):
        return None
    task_name = output.get("task_name")
    if isinstance(task_name, str) and task_name.startswith("/root"):
        return task_name
    return None


def _subagent_activity(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return a Codex SubAgentActivity item, the exact agent id/agent path linkage."""
    if record.get("type") != "event_msg":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "item_completed":
        return None
    item = payload.get("item")
    if isinstance(item, dict) and item.get("type") == "SubAgentActivity":
        return item
    return None


def _encrypted_message_argument(arguments: object) -> tuple[str | None, bool]:
    """Split a spawn payload into visible text and Codex's encrypted-envelope marker."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None, False
    if not isinstance(arguments, dict):
        return None, False
    value = arguments.get("message")
    if not isinstance(value, str) or not value:
        return None, False
    if value.startswith("gAAAAA"):
        return None, True
    return _trim_text(value), False


class _DerivedThreads:
    """Collect per-agent conversation records carried by explicit routing evidence.

    A Codex parent rollout physically records the delegations it issues and the
    returns its children send back. Those records are owned by the child agent's
    execution context, so they materialize the child's own conversation instead of
    being absorbed into the parent thread. Nothing is synthesized: an agent only
    appears once the rollout names it on a real routing record.
    """

    def __init__(self, owner_thread_id: object, owner_agent_path: str | None) -> None:
        self._owner_thread_id = owner_thread_id if isinstance(owner_thread_id, str) else None
        self._owner_agent_path = owner_agent_path
        self._delegated: set[str] = set()
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._thread_ids: dict[str, str] = {}
        self._nicknames: dict[str, str] = {}

    def delegate(self, agent_path: object, thread_id: object = None) -> None:
        """Record that this rollout's own agent spawned ``agent_path``."""
        if not isinstance(agent_path, str) or not agent_path.startswith("/root/"):
            return
        if agent_path == self._owner_agent_path:
            return
        self._delegated.add(agent_path)
        if isinstance(thread_id, str) and thread_id:
            self._thread_ids.setdefault(agent_path, thread_id)

    def owns(self, agent_path: object) -> bool:
        """Only an agent this rollout delegated to has a thread derivable from here.

        A peer message merely names its sender. Treating that as the sender's thread
        would invent an execution identity this rollout never observed, so inbound
        peer routing stays a record of the receiving thread alone.
        """
        return isinstance(agent_path, str) and agent_path in self._delegated

    def add(self, agent_path: object, message: dict[str, Any]) -> None:
        if not self.owns(agent_path):
            return
        self._messages.setdefault(str(agent_path), []).append(message)

    def previews(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for agent_path in sorted(self._messages):
            messages = sorted(
                self._messages[agent_path],
                key=lambda message: (
                    message.get("ordinal") if isinstance(message.get("ordinal"), int) else 2**63 - 1,
                    str(message.get("timestamp") or ""),
                ),
            )
            truncated = len(messages) > _MAX_PREVIEW_MESSAGES
            if truncated:
                messages = messages[:10] + messages[-(_MAX_PREVIEW_MESSAGES - 10) :]
            thread_id = self._thread_ids.get(agent_path)
            results.append(
                {
                    "thread_id": thread_id or f"{self._owner_thread_id or 'codex'}::{agent_path}",
                    "thread_id_source": (
                        THREAD_ID_PROVIDER_NATIVE if thread_id else THREAD_ID_EXECWEAVE_DERIVED
                    ),
                    "parent_thread_id": self._owner_thread_id,
                    "agent_id": thread_id,
                    "agent_path": agent_path,
                    "agent_nickname": self._nicknames.get(agent_path),
                    "message_count": len(messages),
                    "messages_truncated": truncated,
                    "messages": messages,
                    "evidence_scope": EVIDENCE_CROSS_AGENT_ROUTING,
                }
            )
        return results


def codex_rollout_preview(path: str | Path) -> dict[str, Any] | None:
    """Extract only thread-owned visible conversation items from a Codex rollout."""
    previews = codex_rollout_previews(path)
    return previews[0] if previews else None


def codex_rollout_previews(path: str | Path) -> list[dict[str, Any]]:
    """Extract agent-local conversations a single Codex rollout provides evidence for.

    The first result is the rollout's own thread. Codex subagent rollouts can
    physically contain inherited parent history: newer paginated rollouts persist
    ordinals on each line, while older compatible rollouts derive them from physical
    valid-line order, so Codex's own subagent_history_start_ordinal boundary is
    applied in either representation and inherited history is never rendered as if
    it belonged to the child agent.

    Any further results are agent-local threads for other agents this rollout carries
    explicit routing evidence about — a delegation it issued, or a return it received.
    Those records belong to the other agent's execution context, so they are attributed
    there instead of being absorbed into this rollout's own conversation.
    """
    source = Path(path).expanduser().resolve(strict=False)
    identity = codex_rollout_identity(source)
    if identity is None:
        return []
    cutoff = identity.get("subagent_history_start_ordinal")
    min_ordinal = cutoff if isinstance(cutoff, int) else 0
    projected_ordinal = identity.get("history_base_end_ordinal")
    if not isinstance(projected_ordinal, int) or projected_ordinal < 0:
        projected_ordinal = 0
    agent_path, agent_path_source = _resolved_agent_path(identity)
    parent_agent_path = _parent_agent_path(identity, agent_path)
    derived = _DerivedThreads(identity.get("thread_id"), agent_path)
    messages: list[dict[str, Any]] = []
    pending_spawns: dict[str, dict[str, Any]] = {}
    try:
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                ordinal, projected_ordinal = _rollout_ordinal(record, projected_ordinal)
                if ordinal < min_ordinal:
                    continue
                activity = _subagent_activity(record)
                if activity is not None:
                    derived.delegate(
                        activity.get("agent_path"), activity.get("agent_thread_id")
                    )
                    continue
                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_type = payload.get("type")
                if payload_type == "agent_message":
                    content = payload.get("content")
                    text = _content_text(content)
                    header = _agent_message_header(text)
                    encrypted = isinstance(content, list) and any(
                        isinstance(part, dict) and part.get("type") == "encrypted_content"
                        for part in content
                    )
                    sender = payload.get("author") or header.get("sender")
                    recipient = payload.get("recipient") or header.get("task_name")
                    routed = _message(
                        record.get("timestamp"),
                        ordinal,
                        kind=header.get("message_type", "agent_message").lower(),
                        sender=sender,
                        recipient=recipient,
                        text=(
                            None
                            if encrypted
                            else _agent_message_visible_text(text, header)
                        ),
                        content_state="provider_encrypted" if encrypted else "plaintext",
                        phase=None,
                        task_name=header.get("task_name"),
                    )
                    messages.append(routed)
                    derived.add(sender, dict(routed))
                elif payload_type == "function_call" and payload.get("name") == "spawn_agent":
                    call_id = payload.get("call_id")
                    if isinstance(call_id, str) and call_id:
                        text, encrypted = _encrypted_message_argument(payload.get("arguments"))
                        pending_spawns[call_id] = {
                            "timestamp": record.get("timestamp"),
                            "ordinal": ordinal,
                            "text": text,
                            "encrypted": encrypted,
                        }
                elif payload_type == "function_call_output" and isinstance(
                    payload.get("call_id"), str
                ):
                    spawn = pending_spawns.pop(str(payload.get("call_id")), None)
                    target = _spawn_target_path(payload.get("output"))
                    if spawn is None or target is None:
                        continue
                    derived.delegate(target)
                    if not derived.owns(target):
                        continue
                    delegation = _message(
                        spawn["timestamp"],
                        spawn["ordinal"],
                        kind="task",
                        sender=agent_path,
                        recipient=target,
                        text=spawn["text"],
                        content_state=(
                            "provider_encrypted" if spawn["encrypted"] else "plaintext"
                        ),
                        phase="assignment",
                        task_name=target,
                    )
                    messages.append(delegation)
                    derived.add(target, dict(delegation))
                elif payload_type == "message":
                    role = payload.get("role")
                    phase = payload.get("phase")
                    text = _content_text(payload.get("content"))
                    if role == "assistant" and text and phase in {"commentary", "final_answer"}:
                        is_subagent_final = phase == "final_answer" and parent_agent_path is not None
                        messages.append(
                            _message(
                                record.get("timestamp"),
                                ordinal,
                                kind=(
                                    "subagent_final_response"
                                    if is_subagent_final
                                    else "assistant_message"
                                ),
                                sender=agent_path,
                                recipient=parent_agent_path if is_subagent_final else None,
                                text=_trim_text(text),
                                content_state="plaintext",
                                phase=phase,
                                task_name=None,
                            )
                        )
                    elif role == "user" and text:
                        metadata = payload.get("internal_chat_message_metadata_passthrough")
                        kinds = metadata.get("content_item_kinds") if isinstance(metadata, dict) else None
                        if isinstance(kinds, list) and "user.text" in kinds:
                            messages.append(
                                _message(
                                    record.get("timestamp"),
                                    ordinal,
                                    kind="user_message",
                                    sender="user",
                                    recipient=agent_path,
                                    text=_trim_text(text),
                                    content_state="plaintext",
                                    phase=None,
                                    task_name=None,
                                )
                            )
                        elif parent_agent_path is not None:
                            messages.append(
                                _message(
                                    record.get("timestamp"),
                                    ordinal,
                                    kind="task",
                                    sender=parent_agent_path,
                                    recipient=agent_path,
                                    text=_trim_text(text),
                                    content_state="plaintext",
                                    phase="assignment",
                                    task_name=None,
                                )
                            )
                elif (
                    payload_type == "function_call"
                    and payload.get("namespace") == "collaboration"
                    and payload.get("name") == "send_message"
                ):
                    arguments = payload.get("arguments")
                    try:
                        parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        target = parsed.get("target")
                        value = parsed.get("message")
                        encrypted = isinstance(value, str) and value.startswith("gAAAAA")
                        messages.append(
                            _message(
                                record.get("timestamp"),
                                ordinal,
                                kind="send_message",
                                sender=agent_path,
                                recipient=target if isinstance(target, str) else None,
                                text=(
                                    _trim_text(value)
                                    if isinstance(value, str) and value and not encrypted
                                    else None
                                ),
                                content_state="provider_encrypted" if encrypted else "plaintext",
                                phase=None,
                                task_name=None,
                            )
                        )
    except (OSError, RuntimeError, UnicodeError):
        return []
    truncated = len(messages) > _MAX_PREVIEW_MESSAGES
    if truncated:
        messages = messages[:10] + messages[-(_MAX_PREVIEW_MESSAGES - 10) :]
    owner = {
        "thread_id": identity.get("thread_id"),
        # Codex publishes this on rollout session_meta, so it is the agent's own id.
        "thread_id_source": THREAD_ID_PROVIDER_NATIVE,
        "parent_thread_id": identity.get("parent_thread_id"),
        "agent_path": agent_path,
        "agent_path_source": agent_path_source,
        "agent_nickname": identity.get("agent_nickname"),
        "message_count": len(messages),
        "messages_truncated": truncated,
        "messages": messages,
    }
    return [owner, *derived.previews()]

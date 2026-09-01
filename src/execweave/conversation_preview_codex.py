from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_topology import (
    COMPLETENESS_PROVIDER_TRANSCRIPT,
    COMPLETENESS_ROUTING_ONLY,
    EVIDENCE_CROSS_AGENT_ROUTING,
    PATH_EXECWEAVE_DERIVED,
    PATH_PROVIDER_DECLARED,
    ROOT_PATH,
    THREAD_ID_PROVIDER_NATIVE,
    TOPOLOGY_OBSERVED,
    TOPOLOGY_PROVIDER_REPORTED,
)
from .codex_conversation import codex_rollout_previews
from .conversation_preview_common import _agent_identity, _provider_label


def _codex_preview(
    preview: dict[str, Any],
    identity: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    """Wrap one agent-local Codex thread in the shared dashboard conversation schema.

    Codex is the one provider that publishes agent paths itself, on rollout
    ``session_meta`` and on ``SubAgentActivity``. Those paths are marked
    provider-declared; a thread carried only by the parent's routing records is marked
    routing-only so it cannot be read as the child's own transcript.
    """
    agent_path = preview.get("agent_path")
    routing_only = preview.get("evidence_scope") == EVIDENCE_CROSS_AGENT_ROUTING
    result = {
        **identity,
        **preview,
        "provider_label": _provider_label(provider),
        "agent_label": preview.get("agent_nickname") or identity["agent_label"],
    }
    if preview.get("thread_id_source") is None and preview.get("thread_id"):
        result["thread_id_source"] = THREAD_ID_PROVIDER_NATIVE

    # Codex's rollout/routing preview is closer to the provider than the graph source
    # used to open it. A parent rollout can materialize a routing-only child, so the
    # source identity may still name the parent. Prefer a provider-native rollout/thread
    # id when one is present, and explicitly clear inherited parent identity when a
    # routing-only child has no provider-native id of its own.
    thread_id = result.get("thread_id")
    if (
        result.get("thread_id_source") == THREAD_ID_PROVIDER_NATIVE
        and isinstance(thread_id, str)
        and thread_id
    ):
        result["provider_native_id"] = thread_id
    elif routing_only:
        agent_id = preview.get("agent_id")
        result["provider_native_id"] = (
            agent_id if isinstance(agent_id, str) and agent_id else None
        )

    if isinstance(agent_path, str) and agent_path:
        is_root = agent_path == ROOT_PATH
        result["agent_path"] = agent_path
        result["is_root"] = is_root
        # Codex publishes child paths on session_meta and SubAgentActivity. The root
        # rollout does not name itself, so "/root" there stays ExecWeave's rendering.
        result["agent_path_source"] = (
            PATH_EXECWEAVE_DERIVED if is_root else PATH_PROVIDER_DECLARED
        )
        result["topology_state"] = (
            TOPOLOGY_PROVIDER_REPORTED if is_root else TOPOLOGY_OBSERVED
        )
        result["parent_agent_path"] = None if is_root else ROOT_PATH
        result["parent_relation_source"] = (
            None if is_root else preview.get("evidence_scope") or identity.get("topology_evidence")
        )
        if not is_root:
            result["agent_label"] = (
                preview.get("agent_nickname") or agent_path.rsplit("/", 1)[-1] or agent_path
            )
    result["conversation_completeness"] = (
        COMPLETENESS_ROUTING_ONLY if routing_only else COMPLETENESS_PROVIDER_TRANSCRIPT
    )
    result["message_count"] = len(result.get("messages") or [])
    return result


def conversation_preview(
    path: str | Path,
    *,
    content_kind: str,
    provider: str,
    source: dict[str, Any] | None,
    timestamp: object = None,
    ordinal: object = None,
) -> dict[str, Any] | None:
    del content_kind, timestamp, ordinal
    source_path = Path(path).expanduser().resolve(strict=False)
    previews = codex_rollout_previews(source_path)
    if not previews:
        return None
    identity = _agent_identity(provider, source)
    result = _codex_preview(previews[0], identity, provider)
    derived = [_codex_preview(preview, identity, provider) for preview in previews[1:]]
    if derived:
        result["derived_agent_previews"] = derived
    return result

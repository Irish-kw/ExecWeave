from __future__ import annotations

from typing import Any

from .content_store import ContentReference

_TRANSPORT_CREDENTIAL_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "client_secret",
        "password",
    }
)


def filter_transport_credentials(metadata: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Remove transport credentials from provider metadata only.

    Do not apply this to prompts, completions, tool input/output, or file content.
    Those are full-fidelity evidence and remain unredacted.
    """

    removed: list[str] = []

    def walk(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if key_text.lower() in _TRANSPORT_CREDENTIAL_KEYS:
                    removed.append(child_path)
                    continue
                result[key_text] = walk(child, child_path)
            return result
        if isinstance(value, list):
            return [walk(item, f"{path}[{index}]") for index, item in enumerate(value)]
        return value

    return walk(metadata, ""), sorted(removed)


def content_entity(reference: ContentReference) -> dict[str, Any]:
    kind = reference.content_kind.replace(" ", "_")
    return {
        "type": "observed_content",
        "id": f"observed-content:{kind}:sha256:{reference.sha256}",
        "name": reference.content_kind,
        "attributes": reference.to_dict(),
    }


def content_observation_event(
    *,
    timestamp: str,
    provider: str,
    source: dict[str, Any],
    reference: ContentReference,
    relation: str,
    observed_field: str,
    evidence_source: str,
    attribution: str,
    event_type: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a graph-ready content edge without inflating evidence strength."""

    merged: dict[str, Any] = {
        "backend": "semantic",
        "provider": provider,
        "evidence_source": evidence_source,
        "attribution": attribution,
        "observed_field": observed_field,
        "content_sha256": reference.sha256,
        "content_path": reference.path,
        "content_size_bytes": reference.size_bytes,
        "content_media_type": reference.media_type,
        "content_representation": reference.representation,
        "content_complete_from_source": reference.complete_from_source,
        "causal": False,
        "inferred": False,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type or f"semantic.{provider}.content.observed",
        "relation": relation,
        "source": source,
        "target": content_entity(reference),
        "attributes": merged,
    }

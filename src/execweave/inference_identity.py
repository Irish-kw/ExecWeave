from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _required(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def gateway_runtime_identity_event(
    *,
    gateway: str,
    gateway_request_id: str,
    runtime: str,
    runtime_request_id: str,
    shared_request_id: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    gateway = _required(gateway, field="gateway")
    gateway_request_id = _required(gateway_request_id, field="gateway_request_id")
    runtime = _required(runtime, field="runtime")
    runtime_request_id = _required(runtime_request_id, field="runtime_request_id")
    shared_request_id = _required(shared_request_id, field="shared_request_id")

    shared_hash = hashlib.sha256(
        shared_request_id.encode("utf-8", errors="replace")
    ).hexdigest()[:32]
    source = _entity(
        "inference_request",
        f"inference-request:{gateway}:{gateway_request_id}",
        name=gateway_request_id,
        attributes={"gateway": gateway},
    )
    target = _entity(
        "inference_request",
        f"inference-request:{runtime}:{runtime_request_id}",
        name=runtime_request_id,
        attributes={"provider": runtime},
    )
    return {
        "timestamp": timestamp or _now(),
        "event_type": "inference_identity.gateway_runtime.exact",
        "relation": "SAME_INFERENCE_REQUEST",
        "source": source,
        "target": target,
        "attributes": {
            "backend": "cross_layer_identity",
            "attribution": "explicit_shared_request_id",
            "evidence_source": "caller_supplied_shared_request_id",
            "gateway": gateway,
            "runtime": runtime,
            "causal": False,
            "inferred": False,
            "identity_exact": True,
            "identity_method": "shared_request_id",
            "shared_request_id_hash": shared_hash,
        },
    }

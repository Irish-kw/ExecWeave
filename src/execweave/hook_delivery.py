"""Bounded, content-free delivery diagnostics for configured provider hooks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def sidecar_delivery(path: str | None) -> dict[str, Any]:
    if not path:
        return {"state": "not_configured"}
    try:
        with Path(path).open("rb") as handle:
            for _ in range(10000):
                line = handle.readline(1024 * 1024 + 1)
                if not line:
                    return {"state": "no_records"}
                if len(line) > 1024 * 1024:
                    return {"state": "inspection_limit"}
                if not line.strip():
                    continue
                record = json.loads(line)
                if (isinstance(record, dict) and isinstance(record.get("event_type"), str)
                        and record["event_type"] and isinstance(record.get("relation"), str)
                        and record["relation"]):
                    return {"state": "records_present", "semantic_validity": "not_verified"}
                return {"state": "invalid_record"}
    except FileNotFoundError:
        return {"state": "not_produced"}
    except (OSError, ValueError, UnicodeError):
        return {"state": "unreadable_or_invalid"}
    return {"state": "inspection_limit"}

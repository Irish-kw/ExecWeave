from __future__ import annotations

import argparse
import json
from pathlib import Path

from execweave.provider_capability import (
    CAPABILITY_INVENTORY,
    CapabilityInventoryEntry,
    inventory_as_dict,
    matrix_as_dict,
    probe_artifact,
)

_DECRYPTOR_MARKERS = (
    "cryptography.fernet",
    "fernet(",
    ".decrypt(",
)


def _entry(client: str) -> CapabilityInventoryEntry:
    normalized = client.strip().lower()
    matches = [entry for entry in CAPABILITY_INVENTORY if entry.client == normalized]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous client: {client}")
    return matches[0]


def _artifact_spec(raw: str) -> tuple[CapabilityInventoryEntry, str, str, Path]:
    if "=" not in raw:
        raise ValueError("artifact must use CLIENT[:AUTH_MODE][:SURFACE]=PATH")
    selector, raw_path = raw.split("=", 1)
    parts = selector.split(":")
    entry = _entry(parts[0])
    if len(parts) > 3:
        raise ValueError("artifact selector has too many ':' components")

    if len(parts) >= 2 and parts[1]:
        auth_mode = parts[1]
    elif len(entry.auth_modes) == 1:
        auth_mode = entry.auth_modes[0]
    else:
        raise ValueError(f"{entry.client} requires an explicit auth mode")

    if len(parts) >= 3 and parts[2]:
        surface = parts[2]
    elif len(entry.surfaces) == 1:
        surface = entry.surfaces[0]
    else:
        raise ValueError(f"{entry.client} requires an explicit surface")

    if auth_mode not in entry.auth_modes:
        raise ValueError(f"unsupported auth mode for {entry.client}: {auth_mode}")
    if surface not in entry.surfaces:
        raise ValueError(f"unsupported surface for {entry.client}: {surface}")
    if not raw_path:
        raise ValueError("artifact path must not be empty")
    return entry, auth_mode, surface, Path(raw_path).expanduser()


def _codex_decryptor_audit(repo_root: Path) -> bool | None:
    """Return False when no Codex-local decryptor marker is observed.

    This is deliberately an absence observation, not proof that a provider-side
    decryptor exists. If source cannot be inspected, return None rather than guess.
    """

    source_root = repo_root / "src" / "execweave"
    if not source_root.is_dir():
        return None
    codex_files = sorted(source_root.glob("codex*.py"))
    if not codex_files:
        return None
    for path in codex_files:
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (OSError, UnicodeDecodeError):
            return None
        if any(marker in text for marker in _DECRYPTOR_MARKERS):
            return True
    return False


def _matrix(artifact_specs: list[str], repo_root: Path) -> dict[str, object]:
    supplied: dict[tuple[str, str, str], Path] = {}
    for raw in artifact_specs:
        entry, auth_mode, surface, path = _artifact_spec(raw)
        key = (entry.client, auth_mode, surface)
        if key in supplied:
            raise ValueError(f"duplicate artifact selector: {entry.client}:{auth_mode}:{surface}")
        supplied[key] = path

    decryptor_audit = _codex_decryptor_audit(repo_root)
    observations = []
    for entry in CAPABILITY_INVENTORY:
        for auth_mode in entry.auth_modes:
            for surface in entry.surfaces:
                artifact = supplied.get((entry.client, auth_mode, surface))
                observations.extend(
                    probe_artifact(
                        entry,
                        artifact,
                        auth_mode=auth_mode,
                        surface=surface,
                        codex_no_local_decryptor_observed=(
                            entry.client == "codex-cli" and decryptor_audit is False
                        ),
                    )
                )
    result = matrix_as_dict(observations)
    result["probe"] = {
        "network_used": False,
        "codex_local_decryptor_audit": (
            "marker_observed"
            if decryptor_audit is True
            else "no_marker_observed"
            if decryptor_audit is False
            else "not_observed"
        ),
    }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe existing local provider artifacts without network capture."
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="CLIENT[:AUTH_MODE][:SURFACE]=PATH",
        help="attach one existing JSON/JSONL artifact to an inventory row",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="print the Required/Optional Capability Inventory and exit",
    )
    parser.add_argument("--output", type=Path, help="write JSON to this path instead of stdout")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root used only for the Codex local-decryptor source audit",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        payload = inventory_as_dict() if args.inventory_only else _matrix(args.artifact, args.repo_root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

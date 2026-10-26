"""Safe output placement for workloads launched inside an active recording."""
from __future__ import annotations

import os
from pathlib import Path


def prepare_acceptance_output(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    sidecar = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
    shared = bool(sidecar and Path(sidecar).expanduser().resolve().parent == output
                  and os.environ.get("EXECWEAVE_SESSION_ID"))
    if output.exists():
        if not output.is_dir():
            raise FileExistsError(f"Acceptance output is not a directory: {output}")
        if (output / "summary.json").exists() or (any(output.iterdir()) and not shared):
            raise FileExistsError(f"Acceptance output contains a previous run: {output}")
    output.mkdir(parents=True, exist_ok=True)
    return output

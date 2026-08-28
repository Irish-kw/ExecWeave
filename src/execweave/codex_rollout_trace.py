from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from . import codex_rollout_trace_base as _base

CODEX_ROLLOUT_TRACE_ROOT_ENV = _base.CODEX_ROLLOUT_TRACE_ROOT_ENV
CodexRolloutImportResult = _base.CodexRolloutImportResult
codex_rollout_trace_environment = _base.codex_rollout_trace_environment


def _reducer_command_prefix(codex_executable: str | Sequence[str]) -> list[str]:
    if isinstance(codex_executable, str):
        prefix = [codex_executable]
    else:
        prefix = list(codex_executable)
    if not prefix or any(not isinstance(value, str) or not value for value in prefix):
        raise ValueError("Codex reducer command prefix must contain non-empty argv strings")
    return prefix


def _reduce_bundle(
    codex_executable: str | Sequence[str],
    bundle: Path,
    state_path: Path,
) -> str | None:
    prefix = _reducer_command_prefix(codex_executable)
    try:
        completed = subprocess.run(
            [
                *prefix,
                "debug",
                "trace-reduce",
                str(bundle),
                "--output",
                str(state_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    if completed.returncode == 0 and state_path.is_file():
        return None
    detail = (completed.stderr or completed.stdout or "").strip()
    if len(detail) > 500:
        detail = detail[:497] + "..."
    return detail or f"trace-reduce exited {completed.returncode}"


_base._reduce_bundle = _reduce_bundle
import_codex_rollout_traces = _base.import_codex_rollout_traces

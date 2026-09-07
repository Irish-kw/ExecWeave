#!/usr/bin/env python3
"""Formal offline dashboard acceptance with fail-closed interrupt persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import _dashboard_acceptance_impl as _impl

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

from acceptance.interrupt_guard import run_guarded_main  # noqa: E402

_ORIGINAL_RUN_OFFLINE = _impl._run_offline


def _run_offline(output_root: Path, headed: bool):
    """Preserve the public dependency-injection seam used by diagnostics tests."""
    original_diagnostics = _impl.BrowserDiagnostics
    _impl.BrowserDiagnostics = globals()["BrowserDiagnostics"]
    try:
        return _ORIGINAL_RUN_OFFLINE(output_root, headed)
    finally:
        _impl.BrowserDiagnostics = original_diagnostics


_impl._run_offline = _run_offline


def _required(args: Any) -> set[str]:
    return set(args.require) if args.require else {_impl._PROVIDER}


def main() -> int:
    return run_guarded_main(
        main_fn=_impl.main,
        parse_args=_impl._parse_args,
        provider=_impl._PROVIDER,
        mode="offline",
        required_from_args=_required,
        artifact_prefix="offline",
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Formal G6 native Python acceptance with owned-evidence hardening."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import _python_native_acceptance_impl as _impl

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

from acceptance.g6_runner import run_native as _hardened_run_native  # noqa: E402
from acceptance.interrupt_guard import run_guarded_main  # noqa: E402


def _run_native(*, output_root: Path, execweave_bin: str, timeout: float):
    """Preserve the public diagnostics injection seam around the hardened journey."""
    original_diagnostics = _impl.BrowserDiagnostics
    _impl.BrowserDiagnostics = globals()["BrowserDiagnostics"]
    try:
        return _hardened_run_native(
            output_root=output_root,
            execweave_bin=execweave_bin,
            timeout=timeout,
        )
    finally:
        _impl.BrowserDiagnostics = original_diagnostics


_impl._run_native = _run_native


def _required(args: Any) -> set[str]:
    return {str(value).strip().lower() for value in args.require if str(value).strip()}


def main() -> int:
    return run_guarded_main(
        main_fn=_impl.main,
        parse_args=_impl._parse_args,
        provider=_impl._PROVIDER,
        mode=_impl._MODE,
        required_from_args=_required,
        artifact_prefix="python-native",
    )


if __name__ == "__main__":
    raise SystemExit(main())

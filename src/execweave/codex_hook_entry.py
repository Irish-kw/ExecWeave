from __future__ import annotations

import os
import sys
from collections.abc import Sequence

_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"
_AUTO_FLAG = "--auto"
_STRICT_FLAG = "--strict"


def _arguments(argv: Sequence[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _load_capture_main():
    # Keep the globally installed passive hook cheap and isolated from the capture
    # stack. Inactive Codex sessions must not import telemetry code at all.
    from .codex_hook_cli import main as capture_main

    return capture_main


def _automatic_capture_enabled() -> bool:
    configured = os.environ.get(_SEMANTIC_ENV, "")
    return bool(configured.strip())


def main(argv: Sequence[str] | None = None) -> int:
    """Fail-open boundary for the globally installed Codex hook command.

    ExecWeave intentionally leaves the Codex hook configuration installed so a run
    launched through ExecWeave can inherit its semantic sidecar automatically. A
    normal Codex session has no run-bound sidecar, so ``--auto`` must be a completely
    inert success path. When capture is active, the passive global hook must still
    never break Codex because of telemetry failures; ``--strict`` remains available
    for explicit diagnostics outside the installed passive configuration.
    """

    args = _arguments(argv)
    automatic = _AUTO_FLAG in args
    strict = _STRICT_FLAG in args

    if automatic and not _automatic_capture_enabled():
        return 0

    if not automatic or strict:
        return _load_capture_main()(args)

    try:
        _load_capture_main()(args)
    except BaseException:  # noqa: BLE001 - the passive hook must never block Codex
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

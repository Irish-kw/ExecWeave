"""Fail-closed entry guard for formal acceptance runners interrupted by Ctrl+C."""

from __future__ import annotations

import json
import platform
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from acceptance.reporting import Result, write_report


def _snapshot_directories(root: Path) -> set[Path]:
    try:
        return {path.resolve() for path in root.iterdir() if path.is_dir()}
    except OSError:
        return set()


def _interrupted_root(root: Path, before: set[Path], prefix: str) -> Path:
    after = _snapshot_directories(root)
    created = sorted(after - before)
    if len(created) == 1:
        return created[0]
    target = root / f"{prefix}-interrupted-{uuid4().hex[:8]}"
    target.mkdir(parents=True, exist_ok=False)
    return target


def run_guarded_main(
    *,
    main_fn: Callable[[], int],
    parse_args: Callable[[], Any],
    provider: str,
    mode: str,
    required_from_args: Callable[[Any], set[str]],
    artifact_prefix: str,
) -> int:
    """Run a formal CLI and persist an explicit FAIL if Ctrl+C escapes its journey.

    Scenario implementations retain their own bounded ``finally`` cleanup. This
    outer boundary exists only so a user interrupt can never leave the acceptance
    invocation without ``summary.json``/``report.html`` evidence. It deliberately
    does not convert the interrupt into a successful cleanup or unavailable result.
    """

    args = parse_args()
    output_root = Path(args.output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    before = _snapshot_directories(output_root)
    try:
        return int(main_fn())
    except KeyboardInterrupt:
        run_root = _interrupted_root(output_root, before, artifact_prefix)
        marker = "EW-INTERRUPTED-" + uuid4().hex[:10].upper()
        result = Result(
            provider=provider,
            mode=mode,
            marker=marker,
            platform=platform.system().lower(),
            artifacts=str(run_root),
        )
        result.check(
            "Launch",
            False,
            "KeyboardInterrupt escaped the formal journey; acceptance is incomplete",
            "INTERRUPTED.txt",
        )
        result.check(
            "Cleanup",
            False,
            "Runner cleanup may have executed, but completion could not be verified after interrupt",
        )
        (run_root / "INTERRUPTED.txt").write_text(
            "Formal acceptance was interrupted by the user. This run is FAIL and must not be used as PASS evidence.\n",
            encoding="utf-8",
        )
        summary = write_report(run_root, [result], required_from_args(args))
        print(
            json.dumps(
                {"output": str(run_root), **summary},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1

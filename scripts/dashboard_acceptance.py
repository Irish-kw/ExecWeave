#!/usr/bin/env python3
"""Formal offline dashboard acceptance with fail-closed interrupt persistence."""

from __future__ import annotations

from typing import Any

import _dashboard_acceptance_impl as _impl

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

from acceptance.interrupt_guard import run_guarded_main  # noqa: E402


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

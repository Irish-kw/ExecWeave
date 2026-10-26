from __future__ import annotations

from contextlib import nullcontext

from execweave.collector import _safe_process_snapshot


class _ProtectedProcess:
    pid = 4242

    def oneshot(self):
        return nullcontext()

    def exe(self) -> str:
        return "/usr/bin/python3"

    def ppid(self) -> int:
        return 1

    def name(self) -> str:
        return "protected"

    def cmdline(self) -> list[str]:
        raise SystemError("protected process command line")

    def create_time(self) -> float:
        return 1.0


def test_protected_process_cmdline_failure_is_not_a_collector_failure() -> None:
    assert _safe_process_snapshot(_ProtectedProcess()) is None

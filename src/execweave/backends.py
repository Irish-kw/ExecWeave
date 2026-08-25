from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from .collector import RuntimeCollector
from .scope import protect_filesystem_scope
from .sink import JsonlSink
from .strace_backend import StraceRuntimeCollector, strace_available

BackendName = Literal["auto", "portable", "strace"]


def resolve_backend(requested: BackendName) -> str:
    if requested == "portable":
        return "portable"
    if requested == "strace":
        if not strace_available():
            raise RuntimeError("strace backend requested, but Linux strace is not available")
        return "strace"
    if requested != "auto":
        raise ValueError(f"unknown backend: {requested}")
    return "strace" if strace_available() else "portable"


def create_collector(
    *,
    backend: BackendName,
    session_id: str,
    sink: JsonlSink,
    watch_root: Path,
    poll_interval: float,
    collect_filesystem: bool,
    collect_network: bool,
    keep_raw_trace: bool = False,
    allow_broad_filesystem_scope: bool = False,
):
    scope = protect_filesystem_scope(
        watch_root,
        collect_filesystem=collect_filesystem,
        allow_broad_scope=allow_broad_filesystem_scope,
    )
    resolved = resolve_backend(backend)
    if resolved == "strace":
        return StraceRuntimeCollector(
            session_id=session_id,
            sink=sink,
            watch_root=scope.watch_root,
            collect_filesystem=scope.collect_filesystem,
            collect_network=collect_network,
            keep_raw_trace=keep_raw_trace,
        )
    return RuntimeCollector(
        session_id=session_id,
        sink=sink,
        watch_root=scope.watch_root,
        poll_interval=poll_interval,
        collect_filesystem=scope.collect_filesystem,
        collect_network=collect_network,
    )


def backend_diagnostics() -> dict[str, object]:
    return {
        "platform": sys.platform,
        "portable": True,
        "strace": strace_available(),
        "auto_selected": resolve_backend("auto"),
    }

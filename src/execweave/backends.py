from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Literal

from .collector import RuntimeCollector
from .schema import RuntimeEvent
from .scope import protect_filesystem_scope
from .sink import JsonlSink
from .strace_backend import StraceRuntimeCollector, strace_available

BackendName = Literal["auto", "portable", "strace"]


class _FidelityContextSink:
    """Decorate the canonical session start with facts known at collector creation.

    The context is injected before the existing JsonlSink assigns a sequence number,
    so it remains part of the canonical event stream instead of living only in a
    derived report. The wrapper never suppresses or rewrites non-session events.
    """

    def __init__(self, sink: JsonlSink, context: dict[str, object]) -> None:
        self._sink = sink
        self._context = context
        self.path = sink.path

    def emit(self, event: RuntimeEvent) -> None:
        if event.event_type == "session.started":
            event = replace(event, attributes={**event.attributes, **self._context})
        self._sink.emit(event)


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
    context: dict[str, object] = {
        "platform": sys.platform,
        "filesystem_requested": collect_filesystem,
        "filesystem_collected": scope.collect_filesystem,
        "filesystem_scope_downgraded": collect_filesystem and not scope.collect_filesystem,
        "network_requested": collect_network,
        "network_collected": collect_network,
    }
    contextual_sink = _FidelityContextSink(sink, context)
    if resolved == "strace":
        return StraceRuntimeCollector(
            session_id=session_id,
            sink=contextual_sink,
            watch_root=scope.watch_root,
            collect_filesystem=scope.collect_filesystem,
            collect_network=collect_network,
            keep_raw_trace=keep_raw_trace,
        )
    collector = RuntimeCollector(
        session_id=session_id,
        sink=contextual_sink,
        watch_root=scope.watch_root,
        poll_interval=poll_interval,
        collect_filesystem=scope.collect_filesystem,
        collect_network=collect_network,
    )
    context["configured_process_poll_interval_ms"] = round(collector.poll_interval * 1000, 3)
    return collector


def backend_diagnostics() -> dict[str, object]:
    return {
        "platform": sys.platform,
        "portable": True,
        "strace": strace_available(),
        "auto_selected": resolve_backend("auto"),
    }

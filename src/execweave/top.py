from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import psutil

from .collector import infer_agent_name
from .live import LiveResult, run_live


@dataclass
class TerminalState:
    event_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    sequence: int = -1
    finished: bool = False
    compact: bool = False
    connection_status: str = "CONNECTING"
    nodes: dict[str, dict[str, object]] = field(default_factory=dict)
    edges: dict[str, dict[str, object]] = field(default_factory=dict)
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=8))

    @staticmethod
    def _edge_id(edge: dict[str, object]) -> str:
        value = edge.get("id")
        if isinstance(value, str) and value:
            return value
        return f"{edge.get('source')}:{edge.get('relation')}:{edge.get('target')}"

    def apply_snapshot(self, payload: dict[str, object], sequence: int) -> None:
        self.sequence = sequence
        self.event_count = int(payload.get("event_count", 0) or 0)
        self.node_count = int(payload.get("node_count", 0) or 0)
        self.edge_count = int(payload.get("edge_count", 0) or 0)
        self.compact = bool(payload.get("live_payload_compact"))
        self.nodes = {
            str(node.get("id")): node
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and node.get("id")
        }
        self.edges = {
            self._edge_id(edge): edge
            for edge in payload.get("edges", [])
            if isinstance(edge, dict)
        }
        self.connection_status = "LIVE"

    def apply_update(self, update: dict[str, object]) -> None:
        self.sequence = int(update.get("sequence", self.sequence) or self.sequence)
        self.event_count = int(update.get("event_count", self.event_count) or 0)
        self.node_count = int(update.get("node_count", self.node_count) or 0)
        self.edge_count = int(update.get("edge_count", self.edge_count) or 0)
        if update.get("live_payload_compact"):
            self.compact = True
        for key in ("nodes_added", "nodes_updated"):
            for node in update.get(key, []):
                if not isinstance(node, dict) or not node.get("id"):
                    continue
                self.nodes[str(node["id"])] = node
                self._remember_node(node)
        for key in ("edges_added", "edges_updated"):
            for edge in update.get(key, []):
                if not isinstance(edge, dict):
                    continue
                self.edges[self._edge_id(edge)] = edge
                self._remember_edge(edge)

    def _remember_node(self, node: dict[str, object]) -> None:
        node_type = str(node.get("type") or "node")
        name = str(node.get("name") or node.get("id") or "")
        self.recent.append(f"{node_type:<18} {name}")

    def _remember_edge(self, edge: dict[str, object]) -> None:
        relation = str(edge.get("relation") or "edge")
        target = str(edge.get("target") or "")
        count = int(edge.get("count", 1) or 1)
        suffix = f" x{count}" if count > 1 else ""
        self.recent.append(f"{relation:<18} {target}{suffix}")

    def apply_response(self, response: dict[str, object]) -> None:
        kind = response.get("kind")
        if kind == "snapshot":
            graph = response.get("graph")
            if isinstance(graph, dict):
                self.apply_snapshot(graph, int(response.get("sequence", 0) or 0))
        elif kind == "delta":
            base = int(response.get("base_sequence", self.sequence) or 0)
            if self.sequence >= 0 and base != self.sequence:
                self.sequence = -1
                self.connection_status = "RESYNCING"
                return
            for update in response.get("updates", []):
                if isinstance(update, dict):
                    expected = self.sequence + 1
                    sequence = int(update.get("sequence", expected) or expected)
                    if self.sequence >= 0 and sequence != expected:
                        self.sequence = -1
                        self.connection_status = "RESYNCING"
                        return
                    self.apply_update(update)
            self.connection_status = "LIVE"
        elif kind == "noop":
            self.sequence = int(response.get("sequence", self.sequence) or self.sequence)
            self.event_count = int(response.get("event_count", self.event_count) or 0)
            self.node_count = int(response.get("node_count", self.node_count) or 0)
            self.edge_count = int(response.get("edge_count", self.edge_count) or 0)
            self.connection_status = "LIVE"
        self.finished = bool(response.get("live_finished"))
        if self.finished:
            self.connection_status = "FINISHED"


def _entity_type_count(state: TerminalState, *types: str) -> int | None:
    if state.compact and not state.nodes:
        return None
    wanted = set(types)
    return sum(1 for node in state.nodes.values() if str(node.get("type")) in wanted)


def _model_summary(state: TerminalState) -> str:
    names: list[str] = []
    for node in state.nodes.values():
        node_type = str(node.get("type") or "")
        attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        if node_type == "model":
            value = node.get("name") or node.get("id")
            if value:
                names.append(str(value))
        for key in ("resolved_model", "requested_model"):
            value = attributes.get(key)
            if isinstance(value, str) and value:
                names.append(value)
    unique = list(dict.fromkeys(names))
    if not unique:
        return "-"
    if len(unique) == 1:
        return unique[0]
    return f"{unique[0]} +{len(unique) - 1}"


def _process_metrics(state: TerminalState, cache: dict[int, psutil.Process]) -> tuple[str, str]:
    pids: set[int] = set()
    for node in state.nodes.values():
        if node.get("type") != "process":
            continue
        attributes = node.get("attributes")
        if not isinstance(attributes, dict):
            continue
        pid = attributes.get("pid")
        if isinstance(pid, int) and pid > 0:
            pids.add(pid)
    if not pids:
        return "-", "-"
    cpu = 0.0
    rss = 0
    measured = 0
    for pid in pids:
        try:
            process = cache.get(pid)
            if process is None:
                process = psutil.Process(pid)
                process.cpu_percent(interval=None)
                cache[pid] = process
            cpu += process.cpu_percent(interval=None)
            rss += process.memory_info().rss
            measured += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            cache.pop(pid, None)
    if not measured:
        return "-", "-"
    rss_mb = rss / (1024 * 1024)
    return f"{cpu:.1f}%", f"{rss_mb:.0f}M"


def _format_count(value: int | None) -> str:
    return "-" if value is None else str(value)


def _evidence_summary(state: TerminalState) -> str:
    types = {str(node.get("type") or "") for node in state.nodes.values()}
    semantic = bool(types & {"agent", "tool", "tool_call", "mcp_server", "model", "command"})
    return "runtime+semantic" if semantic else "runtime"


def format_dashboard(
    state: TerminalState,
    *,
    command: list[str],
    process_cache: dict[int, psutil.Process] | None = None,
    width: int | None = None,
) -> str:
    cache = process_cache if process_cache is not None else {}
    width = width or shutil.get_terminal_size((120, 30)).columns
    width = max(80, width)
    agent = infer_agent_name(command)
    cpu, rss = _process_metrics(state, cache)
    procs = _entity_type_count(state, "process")
    tools = _entity_type_count(state, "tool_call")
    files = _entity_type_count(state, "file")
    network = _entity_type_count(state, "network_endpoint")
    infer = sum(
        1
        for node in state.nodes.values()
        if "inference" in str(node.get("type") or "").lower()
    )
    if state.compact and not state.nodes:
        infer_value: str = "-"
    else:
        infer_value = str(infer)
    model = _model_summary(state)
    command_text = " ".join(command) or "-"
    max_command = max(12, width - 94)
    if len(command_text) > max_command:
        command_text = command_text[: max(1, max_command - 1)] + "…"
    header = (
        "AGENT           CPU    RSS   PROCS TOOLS FILES NET INFER MODEL                 "
        "EVENTS TRACE             COMMAND"
    )
    row = (
        f"{agent[:15]:<15} {cpu:>6} {rss:>6} {_format_count(procs):>5} "
        f"{_format_count(tools):>5} {_format_count(files):>5} {_format_count(network):>3} "
        f"{infer_value:>5} {model[:21]:<21} {state.event_count:>6} "
        f"{_evidence_summary(state):<17} {command_text}"
    )
    title = f"ExecWeave Top  [{state.connection_status}]  seq={state.sequence}  nodes={state.node_count}  edges={state.edge_count}"
    lines = [title[:width], "─" * min(width, max(len(title), 80)), header[:width], row[:width]]
    if state.compact:
        lines.extend(
            [
                "",
                "Large-graph protective mode: category details are bounded; collection and the Web Viewer remain available.",
            ]
        )
    if state.recent:
        lines.extend(["", "Recent activity"])
        lines.extend(f"  {item}"[:width] for item in reversed(state.recent))
    lines.extend(["", "Web Viewer: use `execweave top --open -- ...` to display both Terminal and Browser views."])
    return "\n".join(lines)


class TerminalTopClient:
    def __init__(
        self,
        *,
        live_url: str,
        command: list[str],
        refresh_seconds: float,
        stream: TextIO,
        stop_event: threading.Event,
    ) -> None:
        self.live_url = live_url.rstrip("/")
        self.command = list(command)
        self.refresh_seconds = max(0.1, refresh_seconds)
        self.stream = stream
        self.stop_event = stop_event
        self.state = TerminalState()
        self.process_cache: dict[int, psutil.Process] = {}
        self._interactive = bool(getattr(stream, "isatty", lambda: False)())
        self._last_noninteractive_render = 0.0

    def _fetch(self) -> dict[str, object]:
        url = f"{self.live_url}/live.json?after={self.state.sequence}"
        with urlopen(url, timeout=max(1.0, self.refresh_seconds * 4)) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("live endpoint returned a non-object payload")
        return payload

    def _render(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not self._interactive and not force and now - self._last_noninteractive_render < 5.0:
            return
        self._last_noninteractive_render = now
        dashboard = format_dashboard(
            self.state,
            command=self.command,
            process_cache=self.process_cache,
        )
        if self._interactive:
            self.stream.write("\x1b[2J\x1b[H")
        self.stream.write(dashboard + "\n")
        self.stream.flush()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                response = self._fetch()
                self.state.apply_response(response)
                self._render(force=self.state.finished)
                if self.state.finished:
                    return
            except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
                self.state.connection_status = "RECONNECTING"
                self._render()
            self.stop_event.wait(self.refresh_seconds)


def run_top(
    command: list[str],
    *,
    watch_root: str | Path,
    output_dir: str | Path | None = None,
    poll_interval: float = 0.10,
    refresh_seconds: float = 0.50,
    collect_filesystem: bool = True,
    collect_network: bool = True,
    port: int = 0,
    open_browser: bool = False,
    linger_seconds: float = 2.0,
    stream: TextIO | None = None,
) -> LiveResult:
    if not command:
        raise ValueError("command must not be empty")
    output = stream or sys.stdout
    stop_event = threading.Event()
    terminal_thread: threading.Thread | None = None

    def announce(live_url: str) -> None:
        nonlocal terminal_thread
        client = TerminalTopClient(
            live_url=live_url,
            command=command,
            refresh_seconds=refresh_seconds,
            stream=output,
            stop_event=stop_event,
        )
        terminal_thread = threading.Thread(
            target=client.run,
            name="execweave-top",
            daemon=True,
        )
        terminal_thread.start()

    try:
        return run_live(
            command,
            watch_root=watch_root,
            output_dir=output_dir,
            poll_interval=poll_interval,
            collect_filesystem=collect_filesystem,
            collect_network=collect_network,
            port=port,
            open_browser=open_browser,
            linger_seconds=max(linger_seconds, refresh_seconds * 2),
            announce=announce,
        )
    finally:
        stop_event.set()
        if terminal_thread is not None:
            terminal_thread.join(timeout=3)

"""Post-validate G6 with exact ownership, cleanup, and live/finished parity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _python_native_acceptance_impl as impl
from acceptance.reporting import Result, Status, redact
from execweave.viewer_projection import project_viewer_graph

_ORIGINAL_RUN_NATIVE = impl._run_native
_ORIGINAL_CHILD_PROGRAM = impl._child_program
_ORIGINAL_LIVE_GRAPH = impl._live_graph
_NETWORK_RELATIONS = frozenset({"CONNECTED_TO", "NETWORK_CONNECTED_TO"})
_RELEVANT_TYPES = frozenset({"process", "file", "network_endpoint"})


def _identity_prefix() -> str:
    return r'''
import json as _ew_json
import os as _ew_os
import psutil as _ew_psutil
from pathlib import Path as _EWPath
_ew_proc = _ew_psutil.Process(_ew_os.getpid())
_EWPath("owned-identity.json").write_text(
    _ew_json.dumps({"pid": _ew_proc.pid, "create_time": _ew_proc.create_time()}),
    encoding="utf-8",
)
'''


def _child_program(marker: str) -> str:
    return _identity_prefix() + "\n" + _ORIGINAL_CHILD_PROGRAM(marker)


def _node_id(node: dict[str, Any]) -> str | None:
    value = node.get("id")
    return value if isinstance(value, str) and value else None


def _owned_process_id(graph: dict[str, Any], identity: dict[str, Any]) -> str | None:
    try:
        wanted_pid = int(identity["pid"])
        wanted_ct = int(float(identity["create_time"]) * 1_000_000)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    matches: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "process":
            continue
        attrs = node.get("attributes")
        node_id = _node_id(node)
        if not isinstance(attrs, dict) or node_id is None:
            continue
        try:
            observed = (
                int(attrs.get("pid")),
                int(float(attrs.get("create_time")) * 1_000_000),
            )
        except (TypeError, ValueError, OverflowError):
            continue
        if observed == (wanted_pid, wanted_ct):
            matches.append(node_id)
    return matches[0] if len(matches) == 1 else None


def _has_owned_network_edge(graph: dict[str, Any], process_id: str) -> bool:
    endpoints = {
        node_id
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
        and node.get("type") == "network_endpoint"
        and (node_id := _node_id(node)) is not None
    }
    return any(
        isinstance(edge, dict)
        and str(edge.get("relation") or "").upper() in _NETWORK_RELATIONS
        and edge.get("source") == process_id
        and edge.get("target") in endpoints
        for edge in graph.get("edges", [])
    )


def _relevant_node_ids(graph: dict[str, Any]) -> set[str]:
    return {
        node_id
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
        and node.get("type") in _RELEVANT_TYPES
        and (node_id := _node_id(node)) is not None
    }


def validate_owned_evidence(
    *,
    graph: dict[str, Any],
    live_graph: dict[str, Any],
    identity: dict[str, Any],
) -> tuple[bool, bool, bool, str]:
    """Validate raw ownership and viewer parity without mixing identity domains.

    ``graph`` is the finalized raw execution graph. ``live_graph`` is the graph carried
    by the live dashboard; live.py intentionally projects that graph before it reaches
    the browser. Raw PID/create-time ownership and the owned network edge therefore stay
    validated against ``graph``, while Finished-viewer parity compares the browser's
    projected live identities with the same projection of the finalized raw graph.
    """

    process_id = _owned_process_id(graph, identity)
    process_ok = process_id is not None
    network_ok = bool(process_id) and _has_owned_network_edge(graph, str(process_id))

    finished_view_graph = project_viewer_graph(graph)
    live_ids = _relevant_node_ids(live_graph)
    finished_view_ids = _relevant_node_ids(finished_view_graph)
    live_only = sorted(live_ids - finished_view_ids)
    finished_only = sorted(finished_view_ids - live_ids)
    parity_ok = bool(live_ids) and not live_only
    detail = (
        f"owned_process={process_id or 'missing'}; "
        f"live_view_relevant={len(live_ids)}; "
        f"finished_view_relevant={len(finished_view_ids)}; "
        f"live_only={live_only}; finished_only={finished_only}"
    )
    return process_ok, network_ok, parity_ok, detail


def apply_cleanup_failures(result: Result, errors: list[str]) -> None:
    if errors:
        result.check(
            "Cleanup",
            False,
            "G6 cleanup or transcript reader failed",
            *errors,
        )


def run_native(
    *,
    output_root: Path,
    execweave_bin: str,
    timeout: float,
):
    """Run the existing journey, then fail closed on weak ownership/parity evidence."""

    captured_live: list[dict[str, Any]] = []
    cleanup_errors: list[str] = []

    def capture_live(page: Any) -> dict[str, Any]:
        graph = _ORIGINAL_LIVE_GRAPH(page)
        captured_live.append(graph)
        return graph

    original_join = impl._LineCapture.join

    def tracked_join(capture: Any) -> None:
        try:
            original_join(capture)
        except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001
            cleanup_errors.append(redact(f"transcript reader join failed: {exc}"))
            return
        thread = getattr(capture, "_thread", None)
        if thread is not None and thread.is_alive():
            cleanup_errors.append("transcript reader thread did not stop within bound")

    browser_cls: Any = None
    playwright_cls: Any = None
    original_browser_close: Any = None
    original_playwright_stop: Any = None
    try:
        from playwright.sync_api import Browser, Playwright

        browser_cls = Browser
        playwright_cls = Playwright
        original_browser_close = Browser.close
        original_playwright_stop = Playwright.stop

        def tracked_browser_close(browser: Any, *args: Any, **kwargs: Any):
            try:
                return original_browser_close(browser, *args, **kwargs)
            except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001
                cleanup_errors.append(redact(f"browser close failed: {exc}"))
                raise

        def tracked_playwright_stop(playwright: Any, *args: Any, **kwargs: Any):
            try:
                return original_playwright_stop(playwright, *args, **kwargs)
            except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001
                cleanup_errors.append(redact(f"Playwright stop failed: {exc}"))
                raise

        Browser.close = tracked_browser_close
        Playwright.stop = tracked_playwright_stop
    except ImportError:
        pass

    impl._child_program = _child_program
    impl._live_graph = capture_live
    impl._LineCapture.join = tracked_join
    try:
        result = _ORIGINAL_RUN_NATIVE(
            output_root=output_root,
            execweave_bin=execweave_bin,
            timeout=timeout,
        )
    finally:
        impl._child_program = _ORIGINAL_CHILD_PROGRAM
        impl._live_graph = _ORIGINAL_LIVE_GRAPH
        impl._LineCapture.join = original_join
        if browser_cls is not None and original_browser_close is not None:
            browser_cls.close = original_browser_close
        if playwright_cls is not None and original_playwright_stop is not None:
            playwright_cls.stop = original_playwright_stop

    apply_cleanup_failures(result, cleanup_errors)
    if result.status == Status.SKIP_UNAVAILABLE:
        return result

    run_root = Path(result.artifacts)
    identity_path = run_root / "workspace" / "owned-identity.json"
    graph_path = run_root / "session" / "graph.json"
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        live_graph = captured_live[-1]
        if not isinstance(identity, dict) or not isinstance(graph, dict):
            raise ValueError("owned identity or finished graph is not an object")
        process_ok, network_ok, parity_ok, detail = validate_owned_evidence(
            graph=graph,
            live_graph=live_graph,
            identity=identity,
        )
    except (OSError, ValueError, json.JSONDecodeError, IndexError) as exc:
        process_ok = network_ok = parity_ok = False
        detail = f"post-validation unavailable: {type(exc).__name__}: {exc}"

    result.check(
        "Process",
        process_ok,
        "Finished raw graph contains exactly one process matching the child PID/create-time identity",
        detail,
    )
    result.check(
        "Network",
        network_ok,
        "Finished raw graph contains a network edge sourced by the exact child PID/create-time process",
        detail,
    )
    result.check(
        "Finished viewer",
        parity_ok,
        "All live projected Process/File/Network identities remain present in the finished viewer projection after the browser clickability check",
        detail,
    )
    return result

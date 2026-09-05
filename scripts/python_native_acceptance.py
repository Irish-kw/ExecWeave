#!/usr/bin/env python3
"""Formal G6 native plain-Python OS-only acceptance.

This scenario deliberately has no provider semantic integration. It proves native
Process/File/Network observation and browser interaction while requiring Prompt,
Final, and Tool-call semantic evidence to remain absent. Passing this scenario must
never be described as framework-independent semantic support.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acceptance.browser_diagnostics import BrowserDiagnostics  # noqa: E402
from acceptance.processes import CleanupReport, OwnedProcessTracker  # noqa: E402
from acceptance.reporting import FEATURES, Result, Status, write_report  # noqa: E402

_PROVIDER = "python"
_MODE = "native-os-only"
_SEMANTIC_PREFIXES = (
    "OBSERVED_",
    "DECLARED_AGENT_",
    "ROUTED_TO_",
)


class _LineCapture:
    def __init__(self, stream: Any, artifact: Path) -> None:
        self._stream = stream
        self._artifact = artifact
        self._lines: list[str] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._artifact.parent.mkdir(parents=True, exist_ok=True)
        with self._artifact.open("w", encoding="utf-8") as output:
            for line in self._stream:
                with self._lock:
                    self._lines.append(line)
                output.write(line)
                output.flush()

    def text(self) -> str:
        with self._lock:
            return "".join(self._lines)

    def wait_for(self, pattern: str, *, timeout: float) -> re.Match[str] | None:
        compiled = re.compile(pattern)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            match = compiled.search(self.text())
            if match:
                return match
            time.sleep(0.05)
        return compiled.search(self.text())

    def join(self) -> None:
        self._thread.join(timeout=3)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            result.append(value)
    return result


def _semantic_relations(path: Path) -> set[str]:
    return {
        str(record.get("relation") or "")
        for record in _read_jsonl(path)
        if str(record.get("relation") or "").startswith(_SEMANTIC_PREFIXES)
    }


def _nodes_of_type(graph: dict[str, Any], node_type: str) -> list[dict[str, Any]]:
    return [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("type") == node_type
    ]


def _skip_result(output_root: Path, reason: str) -> Result:
    marker = "EW-PY-NATIVE-" + uuid4().hex[:10].upper()
    run_root = output_root / f"python-native-{platform.system().lower()}-{uuid4().hex[:8]}"
    run_root.mkdir(parents=True, exist_ok=False)
    result = Result(
        provider=_PROVIDER,
        mode=_MODE,
        marker=marker,
        platform=platform.system().lower(),
        artifacts=str(run_root),
    )
    for feature in FEATURES:
        result.skip(feature, reason)
    return result


def _record_cleanup(
    result: Result,
    cleanup: CleanupReport,
    *,
    unavailable_reason: str | None,
) -> None:
    if cleanup.remaining:
        result.check(
            "Cleanup",
            False,
            "Owned process identities remained after bounded cleanup",
            *(f"{item.pid}:{item.create_time}" for item in cleanup.remaining),
        )
    elif unavailable_reason:
        result.skip("Cleanup", unavailable_reason)
    else:
        result.check(
            "Cleanup",
            True,
            "All explicitly owned process identities exited or were cleaned within bounds",
        )


def _check(result: Result, feature: str, passed: bool, reason: str, *evidence: str) -> bool:
    result.check(feature, passed, reason, *evidence)
    check = result.checks[feature]
    print(f"G6 Python {feature}: {check.status.value} — {check.reason}", flush=True)
    return check.status == Status.PASS


def _skip(result: Result, feature: str, reason: str) -> None:
    result.skip(feature, reason)
    check = result.checks[feature]
    print(f"G6 Python {feature}: {check.status.value} — {check.reason}", flush=True)


def _mark_unavailable(result: Result, reason: str) -> None:
    for feature in FEATURES:
        if feature not in result.checks:
            _skip(result, feature, reason)


def _child_program(marker: str) -> str:
    return f"""
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

MARKER = {marker!r}
print("READY", flush=True)
while not Path("continue.signal").exists():
    time.sleep(0.05)

path = Path("acceptance.txt")
path.write_text(MARKER, encoding="utf-8")
assert path.read_text(encoding="utf-8") == MARKER

child = subprocess.Popen([
    sys.executable,
    "-c",
    "import time; print('CHILD-READY', flush=True); time.sleep(3)",
])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
    server.bind(("127.0.0.1", 0))
    server.listen()
    endpoint = server.getsockname()

    def receive():
        peer, _ = server.accept()
        with peer:
            assert peer.recv(4096).decode("utf-8") == MARKER
            time.sleep(2.5)
            peer.sendall(b"OK")

    worker = threading.Thread(target=receive)
    worker.start()
    with socket.create_connection(endpoint) as client:
        client.sendall(MARKER.encode("utf-8"))
        assert client.recv(2) == b"OK"
    worker.join()

assert child.wait(timeout=8) == 0
print(MARKER + "-DONE", flush=True)
time.sleep(3)
"""


def _live_graph(page: Any) -> dict[str, Any]:
    value = page.evaluate("()=>window.__execweaveCore?.getGraph?.()||{}")
    return value if isinstance(value, dict) else {}


def _locator_for_id(page: Any, node_id: str) -> Any:
    return page.locator(".node[data-id=" + json.dumps(node_id, ensure_ascii=False) + "]")


def _click_type(page: Any, graph: dict[str, Any], node_type: str, *, timeout: float) -> str:
    candidates = _nodes_of_type(graph, node_type)
    if not candidates:
        raise AssertionError(f"missing {node_type} evidence")
    for candidate in candidates:
        node_id = str(candidate.get("id") or "")
        locator = _locator_for_id(page, node_id)
        if locator.count():
            locator.click(timeout=int(timeout * 1000))
            if not page.locator("#details").inner_text().strip():
                raise AssertionError(f"{node_type} inspector is empty")
            return node_id
    raise AssertionError(f"{node_type} evidence exists but none is rendered")


def _run_native(
    *,
    output_root: Path,
    execweave_bin: str,
    timeout: float,
) -> Result:
    marker = "EW-PY-NATIVE-" + uuid4().hex[:10].upper()
    run_root = output_root / f"python-native-{platform.system().lower()}-{uuid4().hex[:8]}"
    workspace = run_root / "workspace"
    session_root = run_root / "session"
    run_root.mkdir(parents=True, exist_ok=False)
    workspace.mkdir()
    result = Result(
        provider=_PROVIDER,
        mode=_MODE,
        marker=marker,
        platform=platform.system().lower(),
        artifacts=str(run_root),
    )
    _skip(result, "/root", "Plain Python has no provider conversation root by design")
    _skip(result, "Multi-agent", "Plain Python OS-only scenario has no provider agents")
    _skip(result, "Fold state", "No semantic conversation history exists in this OS-only scenario")

    tracker = OwnedProcessTracker(poll_interval=0.02)
    process: subprocess.Popen[str] | None = None
    capture: _LineCapture | None = None
    browser = None
    playwright = None
    page = None
    diagnostics: BrowserDiagnostics | None = None
    unavailable_reason: str | None = None
    started_at = time.monotonic()

    try:
        argv = [
            execweave_bin,
            "live",
            "--watch-root",
            str(workspace),
            "--output-dir",
            str(session_root),
            "--interval",
            "0.05",
            "--linger",
            "3",
            "--",
            sys.executable,
            "-u",
            "-c",
            _child_program(marker),
        ]
        print("G6 Python command:", " ".join(argv[:9] + ["<python-program>"]), flush=True)
        process = subprocess.Popen(
            argv,
            cwd=workspace,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        tracker.track_pid(process.pid)
        tracker.start()
        assert process.stdout is not None
        capture = _LineCapture(process.stdout, run_root / "execweave-python-native.log")
        url_match = capture.wait_for(r"ExecWeave live: (http://\S+)", timeout=min(timeout, 15))
        ready = capture.wait_for(r"(?m)^READY\s*$", timeout=min(timeout, 15))
        if not url_match or not ready:
            raise AssertionError("ExecWeave live URL or Python readiness was not observed")
        live_url = url_match.group(1)

        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            unavailable_reason = f"Playwright unavailable: {exc}"
            _mark_unavailable(result, unavailable_reason)
            return result
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(headless=False)
        except PlaywrightError as exc:
            unavailable_reason = f"Headed Chromium unavailable: {exc}"
            _mark_unavailable(result, unavailable_reason)
            return result

        page = browser.new_page(viewport={"width": 1366, "height": 768})
        diagnostics = BrowserDiagnostics(page)
        page.goto(live_url)
        page.wait_for_selector(".node", timeout=int(timeout * 1000))
        page.evaluate("window.__execweaveG6Document=document")
        initial_nodes = page.locator(".node").count()

        (workspace / "continue.signal").touch()
        page.wait_for_function(
            "n=>document.querySelectorAll('.node').length>n",
            arg=initial_nodes,
            timeout=int(timeout * 1000),
        )
        page.wait_for_function(
            """()=> {
              const g=window.__execweaveCore?.getGraph?.()||{};
              const types=new Set((g.nodes||[]).map(n=>n.type));
              return types.has('file') && types.has('process') && types.has('network_endpoint');
            }""",
            timeout=int(timeout * 1000),
        )
        page.wait_for_function(
            "()=>window.__execweaveG6Document===document",
            timeout=int(timeout * 1000),
        )
        live_graph = _live_graph(page)
        _click_type(page, live_graph, "process", timeout=timeout)
        _click_type(page, live_graph, "file", timeout=timeout)
        _click_type(page, live_graph, "network_endpoint", timeout=timeout)
        _check(
            result,
            "Live update",
            page.locator(".node").count() > initial_nodes,
            "Process/file/network evidence grew in the same live document without reload",
        )
        page.screenshot(path=str(run_root / "01-native-live.png"), full_page=True)

        exit_code = process.wait(timeout=max(timeout, 30))
        if exit_code != 0:
            raise AssertionError(f"plain Python live command exited {exit_code}")

        graph_path = session_root / "graph.json"
        viewer_path = session_root / "viewer.html"
        if not graph_path.is_file() or not viewer_path.is_file():
            raise AssertionError("native Python run did not materialize graph.json and viewer.html")
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        file_nodes = _nodes_of_type(graph, "file")
        process_nodes = _nodes_of_type(graph, "process")
        network_nodes = _nodes_of_type(graph, "network_endpoint")
        acceptance_files = [
            node
            for node in file_nodes
            if "acceptance.txt" in str(node.get("id") or "")
            or "acceptance.txt" in str(node.get("name") or "")
        ]
        _check(
            result,
            "File activity",
            bool(acceptance_files)
            and (workspace / "acceptance.txt").read_text(encoding="utf-8") == marker,
            "Native file observation includes the marker file with correct on-disk content",
        )
        _check(
            result,
            "Process",
            len(process_nodes) >= 2,
            "Native run recorded the launched Python process and at least one child process",
        )
        _check(
            result,
            "Network",
            bool(network_nodes),
            "Native run recorded a loopback network endpoint while the connection was held open",
        )

        sidecar = session_root / "semantic.jsonl"
        semantic_relations = _semantic_relations(sidecar)
        semantic_absent = not semantic_relations
        _check(
            result,
            "Prompt",
            semantic_absent,
            "Plain Python produced no observed provider prompt semantics, as required",
            *sorted(semantic_relations),
        )
        _check(
            result,
            "Final",
            semantic_absent,
            "Plain Python produced no observed provider assistant-final semantics, as required",
            *sorted(semantic_relations),
        )
        _check(
            result,
            "Tool call",
            semantic_absent,
            "Plain Python child/process activity was not mislabeled as a semantic tool call",
            *sorted(semantic_relations),
        )
        _check(
            result,
            "Launch",
            True,
            "Real native plain-Python process completed through execweave live",
        )

        page.goto(viewer_path.resolve().as_uri())
        page.wait_for_selector(".node", timeout=int(timeout * 1000))
        _click_type(page, graph, "process", timeout=timeout)
        _click_type(page, graph, "file", timeout=timeout)
        _click_type(page, graph, "network_endpoint", timeout=timeout)
        _check(
            result,
            "Finished viewer",
            True,
            "Finished viewer rendered and actual Process/File/Network inspectors were clickable",
        )
        assert diagnostics is not None
        console_ok = diagnostics.finish(page, run_root)
        _check(
            result,
            "JS console",
            console_ok,
            "No browser console errors or uncaught JavaScript failures were observed"
            if console_ok
            else "; ".join(diagnostics.errors),
            "browser-console.log",
            *("FAILURE.png",) if not console_ok else (),
        )
        page.screenshot(path=str(run_root / "02-native-finished.png"), full_page=True)
    except Exception as exc:  # noqa: BLE001 - formal report preserves exact failure
        if diagnostics is not None and page is not None:
            diagnostics.failure(page, run_root)
        _check(result, "Launch", False, f"{type(exc).__name__}: {exc}")
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:  # noqa: BLE001
                pass
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        if capture is not None:
            capture.join()
        cleanup = tracker.cleanup(
            grace_seconds=0.05,
            terminate_timeout=2.0,
            kill_timeout=2.0,
        )
        _record_cleanup(result, cleanup, unavailable_reason=unavailable_reason)
        result.runtime_seconds = time.monotonic() - started_at

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--require", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_root = args.output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    required = {str(value).strip().lower() for value in args.require if str(value).strip()}
    execweave_bin = shutil.which("execweave")
    if not execweave_bin:
        result = _skip_result(output_root, "execweave executable not found")
    else:
        result = _run_native(
            output_root=output_root,
            execweave_bin=execweave_bin,
            timeout=max(10.0, float(args.timeout)),
        )
    summary = write_report(Path(result.artifacts), [result], required)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if summary["status"] != Status.FAIL.value else 1


if __name__ == "__main__":
    raise SystemExit(main())

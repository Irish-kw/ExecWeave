#!/usr/bin/env python3
"""Formal G5 interactive visible acceptance for a real local Ollama PTY/ConPTY session.

This scenario builds on the G4 owned-server rules but drives ``ollama run`` through a
real pseudo-terminal. POSIX uses the standard-library ``pty`` module. Windows uses
pywinpty/ConPTY when available; it never treats ordinary pipes as an interactive
terminal substitute.

Unavailable provider/model/browser/terminal prerequisites are SKIP_UNAVAILABLE unless
``--require ollama`` is supplied. Any owned-process cleanup failure remains FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ollama_visible_acceptance as visible  # noqa: E402
from acceptance.processes import CleanupReport, OwnedProcessTracker  # noqa: E402
from acceptance.reporting import FEATURES, Result, Status, write_report  # noqa: E402
from acceptance.terminal_output import TerminalTranscript  # noqa: E402
from execweave.conversation_records import conversation_index_payload  # noqa: E402

_PROVIDER = "ollama"
_MODE = "interactive-visible"
_RESPONSE_RELATION = "OBSERVED_INFERENCE_RESPONSE"
_REQUEST_RELATIONS = frozenset(
    {
        "OBSERVED_INFERENCE_REQUEST_MESSAGES",
        "OBSERVED_INFERENCE_REQUEST_PROMPT",
        "OBSERVED_INFERENCE_REQUEST_INPUT",
    }
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return visible._read_jsonl(path)


def _content_contains_marker(run_root: Path, record: dict[str, Any], marker: str) -> bool:
    attributes = record.get("attributes")
    if not isinstance(attributes, dict):
        return False
    content_path = attributes.get("content_path")
    if not isinstance(content_path, str) or not content_path:
        return False
    root = run_root.resolve()
    candidate = (root / content_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    try:
        return marker in candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _source_id(record: dict[str, Any]) -> str | None:
    source = record.get("source")
    if not isinstance(source, dict):
        return None
    source_id = source.get("id")
    return source_id if isinstance(source_id, str) and source_id else None


def _marker_exchange_state(
    sidecar: Path,
    run_root: Path,
    marker: str,
) -> tuple[str | None, bool]:
    records = _read_jsonl(sidecar)
    request_sources = {
        source_id
        for record in records
        if record.get("relation") in _REQUEST_RELATIONS
        and _content_contains_marker(run_root, record, marker)
        and (source_id := _source_id(record)) is not None
    }
    if len(request_sources) > 1:
        raise AssertionError(
            "interactive marker appeared in multiple inference-request identities: "
            f"{sorted(request_sources)}"
        )
    if not request_sources:
        return None, False
    source_id = next(iter(request_sources))
    response_seen = any(
        record.get("relation") == _RESPONSE_RELATION and _source_id(record) == source_id
        for record in records
    )
    return source_id, response_seen


def _wait_marker_exchange(
    sidecar: Path,
    run_root: Path,
    marker: str,
    *,
    timeout: float,
) -> tuple[str | None, bool]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _marker_exchange_state(sidecar, run_root, marker)
        if state[0] is not None and state[1]:
            return state
        time.sleep(0.10)
    return _marker_exchange_state(sidecar, run_root, marker)


class _TerminalBase:
    pid: int
    backend: str

    def write(self, text: str) -> None:
        raise NotImplementedError

    def interrupt(self) -> None:
        raise NotImplementedError

    def is_alive(self) -> bool:
        raise NotImplementedError

    def wait(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_alive():
                return True
            time.sleep(0.05)
        return not self.is_alive()

    def close(self) -> None:
        raise NotImplementedError


class _PosixTerminal(_TerminalBase):
    backend = "posix-pty"

    def __init__(self, argv: list[str], *, cwd: Path, env: dict[str, str], artifact: Path) -> None:
        import pty

        master_fd, slave_fd = pty.openpty()
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            os.close(slave_fd)
        self.pid = process.pid
        self._process = process
        self._master_fd = master_fd
        self._artifact = artifact
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._capture, daemon=True)
        self._thread.start()

    def _capture(self) -> None:
        self._artifact.parent.mkdir(parents=True, exist_ok=True)
        with self._artifact.open("w", encoding="utf-8") as output:
            transcript = TerminalTranscript(output)
            while not self._stop.is_set():
                try:
                    readable, _, _ = select.select([self._master_fd], [], [], 0.20)
                except (OSError, ValueError):
                    break
                if not readable:
                    if self._process.poll() is not None:
                        break
                    continue
                try:
                    chunk = os.read(self._master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                transcript.feed(chunk)
            transcript.close()

    def write(self, text: str) -> None:
        os.write(self._master_fd, text.encode("utf-8"))

    def interrupt(self) -> None:
        if self._process.poll() is not None:
            return
        self.write("\x03")

    def is_alive(self) -> bool:
        return self._process.poll() is None

    def close(self) -> None:
        if not self.is_alive():
            self._thread.join(timeout=1)
        self._stop.set()
        if self.is_alive():
            try:
                os.killpg(self._process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self._process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        try:
            os.close(self._master_fd)
        except OSError:
            pass
        self._thread.join(timeout=2)


class _WinPtyTerminal(_TerminalBase):
    backend = "windows-conpty"

    def __init__(self, argv: list[str], *, cwd: Path, env: dict[str, str], artifact: Path) -> None:
        try:
            from winpty import PtyProcess
            from winpty.enums import Backend
        except ImportError as exc:
            raise RuntimeError("pywinpty/ConPTY is unavailable") from exc
        self._process = PtyProcess.spawn(
            argv,
            cwd=str(cwd),
            env=env,
            dimensions=(30, 120),
            # pywinpty treats integer 0 as falsy and consults PYWINPTY_BACKEND.
            # A nonempty "0" pins ConPTY without changing the user's environment.
            backend=str(Backend.ConPTY),
        )
        self.pid = int(self._process.pid)
        self._artifact = artifact
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._capture, daemon=True)
        self._thread.start()

    def _capture(self) -> None:
        self._artifact.parent.mkdir(parents=True, exist_ok=True)
        with self._artifact.open("w", encoding="utf-8") as output:
            transcript = TerminalTranscript(output)
            while not self._stop.is_set():
                try:
                    chunk = self._process.read(4096)
                except (EOFError, OSError):
                    break
                except Exception:  # noqa: BLE001 - pywinpty raises backend-specific errors
                    if not self._process.isalive():
                        break
                    time.sleep(0.05)
                    continue
                if chunk:
                    transcript.feed(str(chunk))
                elif not self._process.isalive():
                    break
            transcript.close()

    def write(self, text: str) -> None:
        self._process.write(text)

    def interrupt(self) -> None:
        if self.is_alive():
            self._process.write("\x03")

    def is_alive(self) -> bool:
        try:
            return bool(self._process.isalive())
        except Exception:  # noqa: BLE001 - backend status read must fail closed
            return False

    def close(self) -> None:
        if not self.is_alive():
            self._thread.join(timeout=1)
        self._stop.set()
        if self.is_alive():
            try:
                self._process.terminate()
            except Exception:  # noqa: BLE001 - cleanup is best effort before owned tracker
                pass
        self._thread.join(timeout=2)


def _terminal_backend_reason() -> str | None:
    if os.name != "nt":
        try:
            import pty  # noqa: F401
        except ImportError:
            return "POSIX pty module is unavailable"
        return None
    try:
        from winpty import PtyProcess  # noqa: F401
    except ImportError:
        return "pywinpty/ConPTY is unavailable"
    return None


def _spawn_terminal(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    artifact: Path,
) -> _TerminalBase:
    if os.name == "nt":
        return _WinPtyTerminal(argv, cwd=cwd, env=env, artifact=artifact)
    return _PosixTerminal(argv, cwd=cwd, env=env, artifact=artifact)


def _skip_result(output_root: Path, reason: str) -> Result:
    marker = "EW-INTERACTIVE-" + uuid4().hex[:10].upper()
    run_root = output_root / f"ollama-interactive-{platform.system().lower()}-{uuid4().hex[:8]}"
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
    visible._record_cleanup(result, cleanup, unavailable_reason=unavailable_reason)


def _root_preview(graph: dict[str, Any], run_root: Path) -> dict[str, Any]:
    payload = conversation_index_payload(graph, run_root)
    matches = []
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        preview = entry.get("conversation_preview")
        if (
            isinstance(preview, dict)
            and str(entry.get("provider") or "").lower() == _PROVIDER
            and preview.get("is_root") is True
            and preview.get("agent_path") == "/root"
        ):
            matches.append(preview)
    if len(matches) != 1:
        raise AssertionError(f"expected one Ollama /root conversation, got {len(matches)}")
    return matches[0]


def _prompt_and_final_texts(preview: dict[str, Any]) -> tuple[list[str], list[str]]:
    prompts: list[str] = []
    finals: list[str] = []
    for item in preview.get("messages", []):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        if item.get("sender") == "user" and item.get("recipient") == "/root":
            prompts.append(str(item["text"]))
        if item.get("sender") == "/root" and item.get("recipient") in {None, ""}:
            finals.append(str(item["text"]))
    return prompts, finals


def _check(result: Result, feature: str, passed: bool, reason: str, *evidence: str) -> bool:
    result.check(feature, passed, reason, *evidence)
    check = result.checks[feature]
    print(f"G5 {feature}: {check.status.value} — {check.reason}", flush=True)
    return check.status == Status.PASS


def _skip(result: Result, feature: str, reason: str) -> None:
    result.skip(feature, reason)
    check = result.checks.get(feature)
    if check is not None:
        print(f"G5 {feature}: {check.status.value} — {check.reason}", flush=True)


def _mark_unavailable(result: Result, reason: str) -> None:
    for feature in FEATURES:
        if feature not in result.checks:
            _skip(result, feature, reason)


def _click_root(page: Any, timeout: float) -> None:
    node = page.locator('.node[data-id="agent:Ollama"]')
    node.wait_for(state="visible", timeout=int(timeout * 1000))
    node.click(timeout=int(timeout * 1000))


def _run_interactive(
    *,
    output_root: Path,
    model: str,
    execweave_bin: str,
    ollama_bin: str,
    timeout: float,
) -> Result:
    marker = "EW-INTERACTIVE-" + uuid4().hex[:10].upper()
    prompt_one = f"{marker}-ROUND1 What is 2+3? Answer briefly."
    prompt_two = f"{marker}-ROUND2 What is 3+4? Answer briefly."
    run_root = output_root / f"ollama-interactive-{platform.system().lower()}-{uuid4().hex[:8]}"
    session_root = run_root / "session"
    watch_root = run_root / "workspace"
    run_root.mkdir(parents=True, exist_ok=False)
    watch_root.mkdir()
    result = Result(
        provider=_PROVIDER,
        mode=_MODE,
        marker=marker,
        platform=platform.system().lower(),
        artifacts=str(run_root),
    )
    _skip(result, "Tool call", "Plain interactive ollama run has no tool schema in this scenario")
    _skip(
        result,
        "Multi-agent",
        "Single real Ollama root conversation; multi-agent is validated in provider-specific matrix",
    )
    _skip(
        result,
        "File activity",
        "Interactive Ollama does not intentionally mutate the harness workspace; native file evidence belongs to G6",
    )

    terminal_reason = _terminal_backend_reason()
    if terminal_reason:
        _mark_unavailable(result, terminal_reason)
        return result

    public_port = visible._free_loopback_port()
    public_endpoint = f"http://127.0.0.1:{public_port}"
    if visible._json_get(f"{public_endpoint}/api/ps") is not None:
        raise AssertionError("fresh G5 Ollama endpoint was already occupied")

    environment = dict(os.environ)
    environment.update(
        {
            "OLLAMA_HOST": public_endpoint,
            "OLLAMA_NOHISTORY": "1",
            "OLLAMA_NOPRUNE": "1",
            "OLLAMA_NO_CLOUD": "1",
        }
    )
    tracker = OwnedProcessTracker(poll_interval=0.02)
    live_process: subprocess.Popen[str] | None = None
    live_stdout: visible._PipeCapture | None = None
    live_stderr: visible._PipeCapture | None = None
    terminal: _TerminalBase | None = None
    browser = None
    playwright = None
    page_errors: list[str] = []
    unavailable_reason: str | None = None
    started_at = time.monotonic()
    live_details = ""

    try:
        live_command = [
            execweave_bin,
            "live",
            "--watch-root",
            str(watch_root),
            "--output-dir",
            str(session_root),
            "--interval",
            "0.05",
            "--linger",
            "4",
            "--",
            ollama_bin,
            "serve",
        ]
        print("G5 command:", " ".join(live_command), flush=True)
        print("G5 terminal backend:", "windows-conpty" if os.name == "nt" else "posix-pty", flush=True)
        live_process = subprocess.Popen(
            live_command,
            cwd=watch_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **visible._process_group_kwargs(),
        )
        tracker.track_pid(live_process.pid)
        tracker.start()
        assert live_process.stdout is not None
        assert live_process.stderr is not None
        live_stdout = visible._PipeCapture(live_process.stdout, run_root / "execweave.stdout.txt")
        live_stderr = visible._PipeCapture(live_process.stderr, run_root / "execweave.stderr.txt")
        live_url = live_stdout.wait_for_live_url(timeout=min(timeout, 15.0))
        if not live_url:
            raise AssertionError("ExecWeave live URL was not announced")

        tags = visible._wait_json(f"{public_endpoint}/api/tags", timeout=min(timeout, 20.0))
        if tags is None:
            raise AssertionError("owned Ollama serve relay never became reachable")
        if not visible._local_model_present(tags, model):
            unavailable_reason = f"Local Ollama model is unavailable: {model}"
            _mark_unavailable(result, unavailable_reason)
            return result

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

        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(live_url)
        page.evaluate("window.__execweaveG5Document=document")
        initial_nodes = page.locator(".node").count()

        terminal = _spawn_terminal(
            [ollama_bin, "run", model],
            cwd=watch_root,
            env=environment,
            artifact=run_root / "ollama-interactive-terminal.txt",
        )
        tracker.track_pid(terminal.pid)
        print(f"G5 interactive client PID={terminal.pid}", flush=True)
        sidecar = session_root / "semantic.jsonl"

        terminal.write(prompt_one + "\r")
        print("G5 prompt 1:", prompt_one, flush=True)
        source_one, response_one = _wait_marker_exchange(
            sidecar,
            session_root,
            prompt_one,
            timeout=timeout,
        )
        if source_one is None:
            raise AssertionError("first interactive prompt request was not captured")
        if not response_one:
            raise AssertionError(
                "first interactive prompt never produced a response on its request identity"
            )

        _click_root(page, timeout)
        page.wait_for_function(
            "value=>(document.getElementById('details')?.innerText||'').includes(value)",
            arg=prompt_one,
            timeout=int(timeout * 1000),
        )
        first_details = page.locator("#details").inner_text()
        if "FINAL RESPONSE" not in first_details.upper():
            raise AssertionError("first interactive round has no visible Final response")

        terminal.write(prompt_two + "\r")
        print("G5 prompt 2:", prompt_two, flush=True)
        source_two, response_two = _wait_marker_exchange(
            sidecar,
            session_root,
            prompt_two,
            timeout=timeout,
        )
        if source_two is None:
            raise AssertionError("second interactive prompt request was not captured")
        if source_two == source_one:
            raise AssertionError("two interactive rounds reused one inference-request identity")
        if not response_two:
            raise AssertionError(
                "second interactive prompt never produced a response on its request identity"
            )

        page.wait_for_function(
            "value=>(document.getElementById('details')?.innerText||'').includes(value)",
            arg=prompt_two,
            timeout=int(timeout * 1000),
        )
        page.wait_for_function(
            "()=>window.__execweaveG5Document===document",
            timeout=int(timeout * 1000),
        )
        current_nodes = page.locator(".node").count()
        _check(
            result,
            "Live update",
            current_nodes >= initial_nodes,
            "Two interactive rounds appeared without replacing the live document",
        )
        live_details = page.locator("#details").inner_text()

        older = page.locator("#details .execweave-agent-older")
        older.wait_for(state="visible", timeout=int(timeout * 1000))
        if older.count() != 1:
            raise AssertionError(f"expected one Older history disclosure, got {older.count()}")
        summary = older.locator("summary")
        summary.click()
        page.wait_for_function(
            "value=>(document.getElementById('details')?.innerText||'').includes(value)",
            arg=prompt_one,
            timeout=int(timeout * 1000),
        )
        if not older.evaluate("element=>element.open"):
            raise AssertionError("Older history did not stay open after user click")
        page.wait_for_timeout(800)
        if not older.evaluate("element=>element.open"):
            raise AssertionError("Older history auto-collapsed during live polling")

        process_nodes = page.locator('.node[data-id^="process:"]')
        if process_nodes.count() < 1:
            raise AssertionError("interactive run exposed no process node for selection switching")
        process_nodes.first.click()
        _click_root(page, timeout)
        older = page.locator("#details .execweave-agent-older")
        older.wait_for(state="visible", timeout=int(timeout * 1000))
        if not older.evaluate("element=>element.open"):
            raise AssertionError("Older history did not persist across selection switch")
        older.locator("summary").click()
        page.wait_for_timeout(800)
        if older.evaluate("element=>element.open"):
            raise AssertionError("Older history reopened after explicit user collapse")
        _check(
            result,
            "Fold state",
            True,
            "Older history open/closed state persisted through polling and selection switches",
        )

        page.screenshot(path=str(run_root / "01-interactive-live.png"), full_page=True)
        terminal.interrupt()
        if not terminal.wait(min(timeout, 8.0)):
            raise AssertionError("interactive ollama client did not exit after terminal Ctrl+C and /bye")
        _check(result, "Launch", True, f"Real interactive client used terminal backend {terminal.backend}")

        if not visible._interrupt(live_process):
            raise AssertionError("failed to interrupt owned ExecWeave live process")
        try:
            live_process.wait(timeout=min(timeout, 15.0))
        except subprocess.TimeoutExpired as exc:
            raise AssertionError("ExecWeave live did not finalize after interrupt") from exc

        viewer = session_root / "viewer.html"
        graph_path = session_root / "graph.json"
        if not viewer.is_file() or not graph_path.is_file():
            raise AssertionError("interactive run did not materialize graph.json and viewer.html")
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        preview = _root_preview(graph, session_root)
        prompts, finals = _prompt_and_final_texts(preview)
        _check(
            result,
            "/root",
            prompt_one in prompts and prompt_two in prompts,
            "Both PTY/ConPTY prompts belong to one Ollama /root conversation",
        )
        _check(
            result,
            "Prompt",
            prompt_one in prompts and prompt_two in prompts,
            "Both interactive prompts are preserved in the finished conversation",
        )
        _check(
            result,
            "Final",
            len([value for value in finals if value.strip()]) >= 2,
            "Both interactive rounds have non-empty assistant final evidence",
        )

        page.goto(viewer.resolve().as_uri())
        _click_root(page, timeout)
        page.wait_for_function(
            "value=>(document.getElementById('details')?.innerText||'').includes(value)",
            arg=prompt_two,
            timeout=int(timeout * 1000),
        )
        finished_details = page.locator("#details").inner_text()
        _check(
            result,
            "Finished viewer",
            finished_details == live_details,
            "Finished viewer details equal the final live root details",
        )
        _check(result, "JS console", not page_errors, "No browser page errors", *page_errors)

        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        _check(
            result,
            "Process",
            any(isinstance(node, dict) and node.get("type") == "process" for node in nodes),
            "Interactive native run recorded process evidence",
        )
        _check(
            result,
            "Network",
            any(
                isinstance(edge, dict)
                and str(edge.get("relation") or "").upper() in {"CONNECTED_TO", "NETWORK_CONNECTED_TO"}
                for edge in edges
            ),
            "Interactive native run recorded network evidence",
        )
        page.screenshot(path=str(run_root / "02-interactive-finished.png"), full_page=True)
    except Exception as exc:  # noqa: BLE001 - formal report must preserve the exact failure
        _check(result, "Launch", False, f"{type(exc).__name__}: {exc}")
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:  # noqa: BLE001 - cleanup report below remains authoritative
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:  # noqa: BLE001
                pass
        if terminal is not None:
            terminal.close()
        if live_process is not None and live_process.poll() is None:
            visible._interrupt(live_process)
            try:
                live_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        if live_stdout is not None:
            live_stdout.join()
        if live_stderr is not None:
            live_stderr.join()
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
    parser.add_argument("--model", default=os.environ.get("EXECWEAVE_OLLAMA_MODEL", "deepseek-r1:1.5b"))
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--require", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_root = args.output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    required = {str(value).strip().lower() for value in args.require if str(value).strip()}

    execweave_bin = shutil.which("execweave")
    ollama_bin = shutil.which("ollama")
    if not execweave_bin:
        result = _skip_result(output_root, "execweave executable not found")
    elif not ollama_bin:
        result = _skip_result(output_root, "ollama executable not found")
    else:
        result = _run_interactive(
            output_root=output_root,
            model=args.model,
            execweave_bin=execweave_bin,
            ollama_bin=ollama_bin,
            timeout=max(10.0, float(args.timeout)),
        )

    summary = write_report(Path(result.artifacts), [result], required)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if summary["status"] != Status.FAIL.value else 1


if __name__ == "__main__":
    raise SystemExit(main())

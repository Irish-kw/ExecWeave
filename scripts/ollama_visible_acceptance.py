#!/usr/bin/env python3
"""Formal G4 visible-live acceptance for a real local Ollama client/server path.

This scenario deliberately does not use the offline semantic fixture. It starts an
ExecWeave-owned ``ollama serve`` on a fresh loopback endpoint, sends one independent
real ``ollama run`` client request through the public relay, observes the live
dashboard in headed Chromium, interrupts the owned live/server process, then checks
the finished viewer and bounded cleanup.

Unavailable binaries, a missing local model, or an unavailable headed browser are
reported as SKIP_UNAVAILABLE unless ``--require ollama`` is supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acceptance.processes import CleanupReport, OwnedProcessTracker  # noqa: E402
from acceptance.reporting import FEATURES, Result, Status, redact, write_report  # noqa: E402
from execweave.conversation_records import conversation_index_payload  # noqa: E402

_PROVIDER = "ollama"
_MODE = "visible-live"
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LIVE_URL_RE = re.compile(r"ExecWeave live:\s+(http://127\.0\.0\.1:\d+/\?t=[^\s]+)")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _clean_output(value: str) -> str:
    value = _ANSI_RE.sub("", value).replace("\r", "")
    return "\n".join(line.rstrip() for line in value.splitlines()).strip()


def _process_group_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _interrupt(process: subprocess.Popen[str]) -> bool:
    if process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
        return True
    except (AttributeError, OSError, ProcessLookupError):
        return False


def _json_get(url: str, timeout: float = 0.5) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _wait_json(url: str, *, timeout: float) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = _json_get(url)
        if payload is not None:
            return payload
        time.sleep(0.10)
    return _json_get(url)


def _local_model_present(tags: dict[str, Any], model: str) -> bool:
    wanted = model.strip()
    if not wanted:
        return False
    names: set[str] = set()
    for item in tags.get("models", []):
        if not isinstance(item, dict):
            continue
        for key in ("name", "model"):
            value = item.get(key)
            if isinstance(value, str) and value:
                names.add(value)
    if wanted in names:
        return True
    if ":" not in wanted and f"{wanted}:latest" in names:
        return True
    return False


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _root_preview(graph: dict[str, Any], run_root: Path) -> dict[str, Any]:
    payload = conversation_index_payload(graph, run_root)
    candidates: list[dict[str, Any]] = []
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        preview = entry.get("conversation_preview")
        if (
            isinstance(preview, dict)
            and str(entry.get("provider") or "").lower() == "ollama"
            and preview.get("is_root") is True
            and preview.get("agent_path") == "/root"
        ):
            candidates.append(preview)
    if len(candidates) != 1:
        raise AssertionError(f"expected one Ollama /root conversation, got {len(candidates)}")
    return candidates[0]


def _conversation_text(preview: dict[str, Any]) -> tuple[str, str]:
    prompts: list[str] = []
    finals: list[str] = []
    for item in preview.get("messages", []):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        if item.get("sender") == "user" and item.get("recipient") == "/root":
            prompts.append(str(item["text"]))
        if item.get("sender") == "/root" and item.get("recipient") in {None, ""}:
            finals.append(str(item["text"]))
    if not prompts or not finals:
        raise AssertionError("root conversation is missing prompt or final response")
    return prompts[-1], finals[-1]


class _PipeCapture:
    def __init__(self, handle, artifact: Path) -> None:
        self._handle = handle
        self._artifact = artifact
        self.lines: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._artifact.parent.mkdir(parents=True, exist_ok=True)
        with self._artifact.open("w", encoding="utf-8") as output:
            for line in iter(self._handle.readline, ""):
                self.lines.put(line)
                output.write(redact(line))
                output.flush()

    def wait_for_live_url(self, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            match = _LIVE_URL_RE.search(line)
            if match:
                return match.group(1)
        return None

    def join(self, timeout: float = 2.0) -> None:
        self._thread.join(timeout)


def _check(
    result: Result,
    feature: str,
    passed: bool,
    reason: str,
    *evidence: str,
) -> bool:
    result.check(feature, passed, reason, *evidence)
    check = result.checks[feature]
    print(f"G4 {feature}: {check.status.value} — {check.reason}", flush=True)
    return check.status == Status.PASS


def _skip(result: Result, feature: str, reason: str) -> None:
    before = result.checks.get(feature)
    result.skip(feature, reason)
    after = result.checks.get(feature)
    if before is None and after is not None:
        print(f"G4 {feature}: {after.status.value} — {after.reason}", flush=True)


def _mark_unavailable(result: Result, reason: str) -> None:
    for feature in FEATURES:
        if feature not in result.checks:
            _skip(result, feature, reason)


def _record_cleanup(
    result: Result,
    cleanup: CleanupReport,
    *,
    unavailable_reason: str | None,
) -> None:
    if cleanup.remaining:
        _check(
            result,
            "Cleanup",
            False,
            f"Remaining owned identities: {cleanup.remaining}",
        )
        return
    if unavailable_reason is None:
        _check(result, "Cleanup", True, "No harness-owned process identity remains")
        return
    _skip(result, "Cleanup", unavailable_reason)


def _skip_result(output_root: Path, reason: str) -> Result:
    marker = "EW-VISIBLE-" + uuid4().hex[:10].upper()
    run_root = output_root / f"ollama-visible-{platform.system().lower()}-{uuid4().hex[:8]}"
    run_root.mkdir(parents=True, exist_ok=False)
    result = Result(
        provider=_PROVIDER,
        mode=_MODE,
        marker=marker,
        platform=platform.system().lower(),
        artifacts=str(run_root),
    )
    _mark_unavailable(result, reason)
    return result


def _run_visible(
    *,
    output_root: Path,
    model: str,
    execweave_bin: str,
    ollama_bin: str,
    timeout: float,
) -> Result:
    marker = "EW-VISIBLE-" + uuid4().hex[:10].upper()
    foreign = "EW-FOREIGN-" + uuid4().hex[:10].upper()
    prompt = f"Reply briefly without repeating this marker: {marker}. What is 2+2?"
    run_root = output_root / f"ollama-visible-{platform.system().lower()}-{uuid4().hex[:8]}"
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
    _skip(result, "Tool call", "Plain ollama run does not define or execute a tool in this scenario")
    _skip(
        result,
        "File activity",
        "G4 visible Ollama scenario does not require a provider-owned workspace file write",
    )
    _skip(
        result,
        "Multi-agent",
        "Single real Ollama root conversation; multi-agent belongs to provider-specific later gates",
    )
    _skip(
        result,
        "Fold state",
        "Single-round visible G4 scenario; interactive fold persistence belongs to G5",
    )

    public_port = _free_loopback_port()
    public_endpoint = f"http://127.0.0.1:{public_port}"
    if _json_get(f"{public_endpoint}/api/ps") is not None:
        raise AssertionError("fresh G4 Ollama endpoint was already occupied")

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
    client_process: subprocess.Popen[str] | None = None
    live_stdout: _PipeCapture | None = None
    live_stderr: _PipeCapture | None = None
    page_errors: list[str] = []
    browser = None
    playwright = None
    started_at = time.monotonic()
    live_details = ""
    client_stdout = ""
    client_stderr = ""
    unavailable_reason: str | None = None

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
        print("G4 command:", " ".join(live_command), flush=True)
        print("G4 prompt:", prompt, flush=True)
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
            **_process_group_kwargs(),
        )
        tracker.track_pid(live_process.pid)
        tracker.start()
        assert live_process.stdout is not None
        assert live_process.stderr is not None
        live_stdout = _PipeCapture(live_process.stdout, run_root / "execweave.stdout.txt")
        live_stderr = _PipeCapture(live_process.stderr, run_root / "execweave.stderr.txt")
        live_url = live_stdout.wait_for_live_url(timeout=min(timeout, 15.0))
        if not live_url:
            raise AssertionError("ExecWeave live URL was not announced")
        print("G4 collector: authenticated live dashboard announced", flush=True)

        tags = _wait_json(f"{public_endpoint}/api/tags", timeout=min(timeout, 20.0))
        if tags is None:
            raise AssertionError("owned Ollama serve relay never became reachable")
        if not _local_model_present(tags, model):
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
        page.evaluate("window.__execweaveG4Document=document")
        initial_nodes = page.locator(".node").count()

        client_process = subprocess.Popen(
            [ollama_bin, "run", model, prompt],
            cwd=watch_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        tracker.track_pid(client_process.pid)
        try:
            raw_stdout, raw_stderr = client_process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AssertionError("independent ollama run client timed out")
        client_stdout = _clean_output(raw_stdout)
        client_stderr = _clean_output(raw_stderr)
        (run_root / "ollama-client.stdout.txt").write_text(redact(client_stdout), encoding="utf-8")
        (run_root / "ollama-client.stderr.txt").write_text(redact(client_stderr), encoding="utf-8")
        if client_process.returncode != 0:
            raise AssertionError(
                f"independent ollama run failed rc={client_process.returncode}: {client_stderr[-400:]}"
            )
        if not client_stdout:
            raise AssertionError("independent ollama run returned no visible response")
        print(f"G4 provider output: {redact(client_stdout[-1200:])}", flush=True)

        node = page.locator('.node[data-id="agent:Ollama"]')
        node.wait_for(state="visible", timeout=int(timeout * 1000))
        node.click(timeout=int(timeout * 1000))
        page.wait_for_function(
            "marker=>document.querySelector('#details').innerText.includes(marker)",
            arg=marker,
            timeout=int(timeout * 1000),
        )
        page.wait_for_function(
            "()=>document.querySelector('#details').innerText.split('FINAL RESPONSE\\n')[1]?.trim().length>0",
            timeout=int(timeout * 1000),
        )
        live_details = page.locator("#details").inner_text()
        live_final = live_details.partition("FINAL RESPONSE\n")[2].strip()
        _check(
            result,
            "Launch",
            True,
            "Owned Ollama serve relay, independent client and headed Chromium started",
        )
        _check(
            result,
            "Prompt",
            prompt in live_details,
            "Unique real-client prompt is visible in the live root details",
        )
        _check(
            result,
            "Final",
            bool(live_final) and live_final != prompt and foreign not in live_final,
            "Live root has a non-prompt assistant final and no foreign marker",
            "02-live-final.png",
        )
        _check(result, "/root", True, "Clicked real Ollama agent root at agent_path=/root")
        same_document = page.evaluate("window.__execweaveG4Document===document")
        final_nodes = page.locator(".node").count()
        _check(
            result,
            "Live update",
            same_document and final_nodes > initial_nodes,
            f"Same document updated without reload; nodes {initial_nodes}->{final_nodes}",
        )
        page.screenshot(path=str(run_root / "02-live-final.png"))

        if not _interrupt(live_process):
            raise AssertionError("could not send bounded interrupt to owned ExecWeave live process")
        try:
            live_process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AssertionError("ExecWeave live did not finalize after interrupt")
        print(f"G4 collector: finalized rc={live_process.returncode}", flush=True)

        for required in (
            "events.jsonl",
            "semantic.jsonl",
            "events.semantic.jsonl",
            "graph.json",
            "viewer.html",
        ):
            target = session_root / required
            if not target.is_file() or target.stat().st_size == 0:
                raise AssertionError(f"missing finalized artifact: {required}")

        graph = json.loads((session_root / "graph.json").read_text(encoding="utf-8"))
        if not isinstance(graph, dict):
            raise AssertionError("graph.json is not an object")
        preview = _root_preview(graph, session_root)
        finished_prompt, finished_final = _conversation_text(preview)
        _check(
            result,
            "Prompt",
            finished_prompt == prompt,
            "Finished /root prompt exactly matches the independent Ollama client prompt",
        )
        _check(
            result,
            "Final",
            finished_final == live_final and bool(finished_final),
            "Finished /root final exactly matches the completed live root final",
        )

        nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
        _check(
            result,
            "Process",
            any(node.get("type") == "process" for node in nodes),
            "Real process node observed",
        )
        if any(node.get("type") == "endpoint" for node in nodes):
            _check(result, "Network", True, "Real endpoint node observed in the finished graph")
        else:
            _skip(
                result,
                "Network",
                "Portable network sampling did not observe a stable endpoint in this short run",
            )

        page.goto((session_root / "viewer.html").as_uri())
        finished_node = page.locator('.node[data-id="agent:Ollama"]')
        finished_node.click(timeout=int(timeout * 1000))
        finished_details = page.locator("#details").inner_text()
        _check(
            result,
            "Finished viewer",
            finished_details == live_details
            and prompt in finished_details
            and finished_final in finished_details,
            "Finished viewer details equal the completed live details for the same real conversation",
            "03-finished.png",
        )
        page.screenshot(path=str(run_root / "03-finished.png"))
        _check(
            result,
            "JS console",
            not page_errors,
            "No browser page errors observed" if not page_errors else "; ".join(page_errors),
        )
        sidecar_events = _read_jsonl(session_root / "semantic.jsonl")
        result.observed_requests = sum(
            1 for event in sidecar_events if event.get("relation") == "OBSERVED_INFERENCE_RESPONSE"
        )
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        for feature in (
            "Launch",
            "Prompt",
            "Final",
            "/root",
            "Live update",
            "Process",
            "Finished viewer",
            "JS console",
        ):
            if feature not in result.checks:
                _check(result, feature, False, failure)
                break
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        if client_process is not None and client_process.poll() is None:
            client_process.terminate()
        if live_process is not None and live_process.poll() is None:
            _interrupt(live_process)
        if client_process is not None:
            try:
                client_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                client_process.kill()
        if live_process is not None:
            try:
                live_process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                pass
        tracker.scan_once()
        cleanup = tracker.cleanup(
            grace_seconds=0.10,
            terminate_timeout=2.0,
            kill_timeout=2.0,
        )
        _record_cleanup(result, cleanup, unavailable_reason=unavailable_reason)
        if live_stdout is not None:
            live_stdout.join()
        if live_stderr is not None:
            live_stderr.join()
        result.runtime_seconds = time.monotonic() - started_at
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real Ollama visible-live acceptance")
    parser.add_argument(
        "--model",
        default=os.environ.get("EXECWEAVE_ACCEPTANCE_OLLAMA_MODEL", ""),
        help="Existing local Ollama model. Missing model is SKIP_UNAVAILABLE.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/dashboard-acceptance"),
    )
    parser.add_argument("--execweave-bin", default="")
    parser.add_argument("--ollama-bin", default="")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="Provider that must PASS; use --require ollama to make unavailable fail overall.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_root = args.output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    execweave_bin = args.execweave_bin or shutil.which("execweave") or ""
    ollama_bin = args.ollama_bin or shutil.which("ollama") or ""
    unavailable: list[str] = []
    if not execweave_bin:
        unavailable.append("execweave executable not found")
    if not ollama_bin:
        unavailable.append("ollama executable not found")
    if not args.model.strip():
        unavailable.append("no local Ollama model specified")
    if unavailable:
        result = _skip_result(output_root, "; ".join(unavailable))
    else:
        result = _run_visible(
            output_root=output_root,
            model=args.model.strip(),
            execweave_bin=execweave_bin,
            ollama_bin=ollama_bin,
            timeout=max(10.0, float(args.timeout)),
        )
    run_root = Path(result.artifacts)
    required = set(args.require)
    summary = write_report(run_root, [result], required)
    print(
        json.dumps(
            {"output": str(run_root), **summary},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 1 if summary["status"] == Status.FAIL.value else 0


if __name__ == "__main__":
    raise SystemExit(main())

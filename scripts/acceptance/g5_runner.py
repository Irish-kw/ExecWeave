"""Hardened G5 real-provider journey.

This module intentionally reuses the stable PTY/ConPTY, conversation, and process
helpers from ``_ollama_interactive_acceptance_impl`` while owning the formal journey
itself. Keeping the runner separate avoids another compatibility shim inside the
terminal primitives and makes browser/cleanup failures first-class evidence.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import _ollama_interactive_acceptance_impl as impl
from acceptance.browser_diagnostics import BrowserDiagnostics
from acceptance.processes import OwnedProcessTracker
from acceptance.reporting import Result, redact


def run_interactive(
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
    run_root = (
        output_root
        / f"ollama-interactive-{platform.system().lower()}-{uuid4().hex[:8]}"
    )
    session_root = run_root / "session"
    watch_root = run_root / "workspace"
    run_root.mkdir(parents=True, exist_ok=False)
    watch_root.mkdir()

    result = Result(
        provider=impl._PROVIDER,
        mode=impl._MODE,
        marker=marker,
        platform=platform.system().lower(),
        artifacts=str(run_root),
    )
    impl._skip(
        result,
        "Tool call",
        "Plain interactive ollama run has no tool schema in this scenario",
    )
    impl._skip(
        result,
        "Multi-agent",
        "Single real Ollama root conversation; multi-agent is validated separately",
    )
    impl._skip(
        result,
        "File activity",
        "Interactive Ollama does not intentionally mutate the harness workspace; "
        "native file evidence belongs to G6",
    )

    tracker = OwnedProcessTracker(poll_interval=0.02)
    live_process: subprocess.Popen[str] | None = None
    live_stdout: Any = None
    live_stderr: Any = None
    terminal: Any = None
    browser: Any = None
    playwright: Any = None
    page: Any = None
    diagnostics: BrowserDiagnostics | None = None
    unavailable_reason: str | None = None
    cleanup_errors: list[str] = []
    started_at = time.monotonic()
    completed_live_details = ""

    try:
        terminal_reason = impl._terminal_backend_reason()
        if terminal_reason:
            unavailable_reason = terminal_reason
            impl._mark_unavailable(result, terminal_reason)
            return result

        public_port = impl.visible._free_loopback_port()
        public_endpoint = f"http://127.0.0.1:{public_port}"
        if impl.visible._json_get(f"{public_endpoint}/api/ps") is not None:
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
        print(
            "G5 terminal backend:",
            "windows-conpty" if os.name == "nt" else "posix-pty",
            flush=True,
        )
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
            **impl.visible._process_group_kwargs(),
        )
        tracker.track_pid(live_process.pid)
        tracker.start()
        assert live_process.stdout is not None
        assert live_process.stderr is not None
        live_stdout = impl.visible._PipeCapture(
            live_process.stdout,
            run_root / "execweave.stdout.txt",
        )
        live_stderr = impl.visible._PipeCapture(
            live_process.stderr,
            run_root / "execweave.stderr.txt",
        )
        live_url = live_stdout.wait_for_live_url(timeout=min(timeout, 15.0))
        if not live_url:
            raise AssertionError("ExecWeave live URL was not announced")

        tags = impl.visible._wait_json(
            f"{public_endpoint}/api/tags",
            timeout=min(timeout, 20.0),
        )
        if tags is None:
            raise AssertionError("owned Ollama serve relay never became reachable")
        if not impl.visible._local_model_present(tags, model):
            unavailable_reason = f"Local Ollama model is unavailable: {model}"
            impl._mark_unavailable(result, unavailable_reason)
            return result

        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            unavailable_reason = f"Playwright unavailable: {exc}"
            impl._mark_unavailable(result, unavailable_reason)
            return result

        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(headless=False)
        except PlaywrightError as exc:
            unavailable_reason = f"Headed Chromium unavailable: {exc}"
            impl._mark_unavailable(result, unavailable_reason)
            return result

        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        diagnostics = BrowserDiagnostics(page)
        page.goto(live_url)
        page.evaluate("window.__execweaveG5Document=document")
        initial_nodes = page.locator(".node").count()

        terminal = impl._spawn_terminal(
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
        source_one, response_one = impl._wait_marker_exchange(
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

        impl._click_root(page, timeout)
        page.wait_for_function(
            "value=>(document.getElementById('details')?.innerText||'').includes(value)",
            arg=prompt_one,
            timeout=int(timeout * 1000),
        )
        impl.visible._wait_agent_card_observed(page, "Final response", timeout=timeout)
        first_details = page.locator("#details").inner_text()
        if "FINAL RESPONSE" not in first_details.upper():
            raise AssertionError("first interactive round has no visible Final response")

        terminal.write(prompt_two + "\r")
        print("G5 prompt 2:", prompt_two, flush=True)
        source_two, response_two = impl._wait_marker_exchange(
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
        impl.visible._wait_agent_card_observed(page, "Final response", timeout=timeout)
        page.wait_for_function(
            "()=>window.__execweaveG5Document===document",
            timeout=int(timeout * 1000),
        )
        current_nodes = page.locator(".node").count()
        impl._check(
            result,
            "Live update",
            current_nodes >= initial_nodes,
            "Two interactive rounds appeared without replacing the live document",
        )

        older = page.locator("#details .execweave-agent-older")
        older.wait_for(state="visible", timeout=int(timeout * 1000))
        if older.count() != 1:
            raise AssertionError(
                f"expected one Older history disclosure, got {older.count()}"
            )
        older.locator("summary").click()
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
            raise AssertionError(
                "interactive run exposed no process node for selection switching"
            )
        process_nodes.first.click()
        impl._click_root(page, timeout)
        older = page.locator("#details .execweave-agent-older")
        older.wait_for(state="visible", timeout=int(timeout * 1000))
        if not older.evaluate("element=>element.open"):
            raise AssertionError("Older history did not persist across selection switch")
        older.locator("summary").click()
        page.wait_for_timeout(800)
        if older.evaluate("element=>element.open"):
            raise AssertionError("Older history reopened after explicit user collapse")
        impl._check(
            result,
            "Fold state",
            True,
            "Older history open/closed state persisted through polling and selection switches",
        )

        page.screenshot(
            path=str(run_root / "01-interactive-live.png"),
            full_page=True,
        )
        terminal.interrupt()
        if not terminal.wait(min(timeout, 8.0)):
            raise AssertionError(
                "interactive ollama client did not exit after terminal Ctrl+C and /bye"
            )
        impl._check(
            result,
            "Launch",
            True,
            f"Real interactive client used terminal backend {terminal.backend}",
        )

        if not impl.visible._interrupt(live_process):
            raise AssertionError("failed to interrupt owned ExecWeave live process")
        try:
            live_process.wait(timeout=min(timeout, 15.0))
        except subprocess.TimeoutExpired as exc:
            raise AssertionError("ExecWeave live did not finalize after interrupt") from exc

        impl.visible._wait_agent_panel_finished(page, timeout=min(timeout, 8.0))
        completed_live_details = page.locator("#details").inner_text()

        viewer = session_root / "viewer.html"
        graph_path = session_root / "graph.json"
        if not viewer.is_file() or not graph_path.is_file():
            raise AssertionError(
                "interactive run did not materialize graph.json and viewer.html"
            )
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        preview = impl._root_preview(graph, session_root)
        prompts, finals = impl._prompt_and_final_texts(preview)
        impl._check(
            result,
            "/root",
            prompt_one in prompts and prompt_two in prompts,
            "Both PTY/ConPTY prompts belong to one Ollama /root conversation",
        )
        impl._check(
            result,
            "Prompt",
            prompt_one in prompts and prompt_two in prompts,
            "Both interactive prompts are preserved in the finished conversation",
        )
        impl._check(
            result,
            "Final",
            len([value for value in finals if value.strip()]) >= 2,
            "Both interactive rounds have non-empty assistant final evidence",
        )

        owned = tracker.identities()
        impl._check(
            result,
            "Process",
            bool(impl.visible._owned_process_node_ids(graph, owned)),
            "Interactive native run recorded a process node owned by PID/create-time identity",
        )
        impl._check(
            result,
            "Network",
            impl.visible._has_owned_network_evidence(graph, owned),
            "Interactive native run recorded a network edge from a harness-owned "
            "PID/create-time identity",
        )

        page.goto(viewer.resolve().as_uri())
        impl._click_root(page, timeout)
        page.wait_for_function(
            "value=>(document.getElementById('details')?.innerText||'').includes(value)",
            arg=prompt_two,
            timeout=int(timeout * 1000),
        )
        finished_details = page.locator("#details").inner_text()
        impl._check(
            result,
            "Finished viewer",
            finished_details == completed_live_details,
            "Finished viewer details equal the synchronized terminal live root details",
        )
        assert diagnostics is not None
        console_ok = diagnostics.finish(page, run_root)
        impl._check(
            result,
            "JS console",
            console_ok,
            "No browser console errors or uncaught JavaScript failures were observed"
            if console_ok
            else "; ".join(diagnostics.errors),
            "browser-console.log",
            *("FAILURE.png",) if not console_ok else (),
        )

        sidecar_events = impl._read_jsonl(sidecar)
        result.observed_requests = sum(
            1
            for event in sidecar_events
            if event.get("relation") == impl._RESPONSE_RELATION
        )
        page.screenshot(
            path=str(run_root / "02-interactive-finished.png"),
            full_page=True,
        )
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001
        if diagnostics is not None and page is not None:
            diagnostics.failure(page, run_root)
        failure = f"{type(exc).__name__}: {exc}"
        for feature in (
            "Launch",
            "Prompt",
            "Final",
            "/root",
            "Fold state",
            "Live update",
            "Process",
            "Network",
            "Finished viewer",
            "JS console",
        ):
            if feature not in result.checks:
                impl._check(result, feature, False, failure)
                break
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(redact(f"browser close failed: {exc}"))
        if playwright is not None:
            try:
                playwright.stop()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(redact(f"Playwright stop failed: {exc}"))
        if terminal is not None:
            try:
                terminal.close()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(redact(f"terminal close failed: {exc}"))
        if live_process is not None and live_process.poll() is None:
            if not impl.visible._interrupt(live_process):
                cleanup_errors.append("failed to request live-process finalization")
            try:
                live_process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                cleanup_errors.append("ExecWeave live process did not stop within cleanup bound")
        tracker.scan_once()
        cleanup = tracker.cleanup(
            grace_seconds=0.10,
            terminate_timeout=2.0,
            kill_timeout=2.0,
        )
        impl._record_cleanup(
            result,
            cleanup,
            unavailable_reason=unavailable_reason,
        )
        for label, capture in (
            ("ExecWeave stdout", live_stdout),
            ("ExecWeave stderr", live_stderr),
        ):
            if capture is not None and not capture.join():
                cleanup_errors.append(f"{label} transcript reader did not stop cleanly")
        if cleanup_errors:
            impl._check(result, "Cleanup", False, "; ".join(cleanup_errors))
        result.runtime_seconds = time.monotonic() - started_at

    return result

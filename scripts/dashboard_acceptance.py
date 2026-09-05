#!/usr/bin/env python3
"""ExecWeave dashboard acceptance runner.

The offline scenario is a real loopback relay -> semantic sidecar -> live dashboard
-> merged graph -> finished viewer journey. It does not claim a real provider is
installed or usable on the current host.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from acceptance.contracts import ConversationSnapshot, same_conversation, verify_conversation
from acceptance.reporting import Result, Status, write_report
from execweave import live
from execweave.conversation_records import conversation_index_payload
from execweave.graph import build_execution_graph, write_execution_graph
from execweave.http_proxy import ProxyConfig, create_proxy_server
from execweave.schema import SCHEMA_VERSION
from execweave.semantic import merge_semantic_sidecar
from execweave.viewer_projection import write_graph_html
from playwright.sync_api import sync_playwright

_PROVIDER = "offline-ollama-fixture"


def _iso(base: datetime, seconds: int) -> str:
    return (base + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _runtime_events(session_id: str) -> list[dict[str, object]]:
    base = datetime.now(timezone.utc)
    agent = {
        "type": "agent",
        "id": "agent:Ollama",
        "name": "Ollama",
        "attributes": {"provider": "ollama"},
    }
    session = {
        "type": "session",
        "id": f"session:{session_id}",
        "name": session_id,
        "attributes": {},
    }
    process = {
        "type": "process",
        "id": f"process:4242:{int(base.timestamp() * 1_000_000)}",
        "name": "offline-fixture",
        "attributes": {
            "pid": 4242,
            "ppid": 1,
            "create_time": base.timestamp(),
        },
    }
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": "runtime-start",
            "session_id": session_id,
            "timestamp": _iso(base, 0),
            "event_type": "session.started",
            "relation": "STARTED_SESSION",
            "source": agent,
            "target": session,
            "sequence": 1,
            "attributes": {"backend": "acceptance_fixture"},
        },
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": "runtime-process",
            "session_id": session_id,
            "timestamp": _iso(base, 1),
            "event_type": "process.started",
            "relation": "LAUNCHED",
            "source": session,
            "target": process,
            "sequence": 2,
            "attributes": {
                "backend": "acceptance_fixture",
                "attribution": "offline_fixture",
                "causal": True,
            },
        },
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": "runtime-finish",
            "session_id": session_id,
            "timestamp": _iso(base, 10),
            "event_type": "session.finished",
            "relation": "FINISHED_SESSION",
            "source": session,
            "target": None,
            "sequence": 3,
            "attributes": {"backend": "acceptance_fixture", "return_code": 0},
        },
    ]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _content_value(root: Path, event: dict[str, object]) -> object:
    attrs = event.get("attributes")
    if not isinstance(attrs, dict):
        return None
    relative = attrs.get("content_path")
    if not isinstance(relative, str) or not relative:
        return None
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if target.suffix.lower() == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _all_content_referenced(root: Path, events: list[dict[str, object]]) -> bool:
    referenced: set[str] = set()
    for event in events:
        attrs = event.get("attributes")
        if isinstance(attrs, dict) and isinstance(attrs.get("content_path"), str):
            referenced.add(str(attrs["content_path"]).replace("\\", "/"))
    content_root = root / "content"
    actual = (
        {
            path.relative_to(root).as_posix()
            for path in content_root.rglob("*")
            if path.is_file()
        }
        if content_root.exists()
        else set()
    )
    return actual == referenced


def _tool_call_observed(root: Path, events: list[dict[str, object]]) -> bool:
    for event in events:
        if event.get("relation") != "OBSERVED_ASSISTANT_TOOL_CALLS":
            continue
        value = _content_value(root, event)
        if "echo" in json.dumps(value, ensure_ascii=False, sort_keys=True):
            return True
    return False


def _root_snapshot_from_payload(payload: dict[str, object]) -> ConversationSnapshot:
    candidates: list[dict[str, object]] = []
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        if str(entry.get("provider") or "").lower() != "ollama":
            continue
        if preview.get("is_root") is True and preview.get("agent_path") == "/root":
            candidates.append(preview)
    if len(candidates) != 1:
        raise AssertionError(f"expected one Ollama /root conversation, got {len(candidates)}")

    preview = candidates[0]
    messages = [item for item in preview.get("messages", []) if isinstance(item, dict)]
    prompts = [
        str(item.get("text"))
        for item in messages
        if item.get("sender") == "user"
        and item.get("recipient") == "/root"
        and isinstance(item.get("text"), str)
    ]
    finals = [
        str(item.get("text"))
        for item in messages
        if item.get("sender") == "/root"
        and item.get("recipient") in {None, ""}
        and isinstance(item.get("text"), str)
    ]
    if not prompts or not finals:
        raise AssertionError("root conversation is missing a projected prompt or final response")
    return ConversationSnapshot(
        owner=str(preview["agent_path"]),
        prompt=prompts[-1],
        final=finals[-1],
    )


def _root_snapshot(graph: dict[str, object], root: Path) -> ConversationSnapshot:
    return _root_snapshot_from_payload(conversation_index_payload(graph, root))


def _materialize(runtime: Path, sidecar: Path, output: Path) -> dict[str, object]:
    merge_semantic_sidecar(runtime, sidecar, output)
    return build_execution_graph(output).to_dict()


def _start_server(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _run_offline(output_root: Path, headed: bool) -> Result:
    marker = "EW-OFFLINE-" + uuid4().hex[:10].upper()
    done = marker + "-DONE"
    foreign = "EW-FOREIGN-" + uuid4().hex[:10].upper()
    prompt = f"{marker} Reply exactly {done}"
    session_id = "acceptance-" + uuid4().hex[:10]
    run_root = output_root / f"offline-{platform.system().lower()}-{uuid4().hex[:8]}"
    run_root.mkdir(parents=True, exist_ok=False)

    result = Result(
        provider=_PROVIDER,
        mode="offline",
        marker=marker,
        platform=platform.system().lower(),
        artifacts=str(run_root),
    )
    for feature, reason in (
        ("File activity", "Offline semantic fixture does not claim native file observation"),
        ("Process", "Offline semantic fixture does not claim native process observation"),
        ("Network", "Offline semantic fixture does not claim native network observation"),
        ("Multi-agent", "Single-root offline scenario; multi-agent is exercised separately"),
        ("Fold state", "Single-round offline scenario; fold-state suites are separate"),
    ):
        result.skip(feature, reason)

    runtime = run_root / "events.jsonl"
    sidecar = run_root / "semantic.jsonl"
    records = _runtime_events(session_id)
    _write_jsonl(runtime, records[:2])

    release = threading.Event()
    received = threading.Event()
    completed = threading.Event()
    client_errors: list[str] = []
    console_errors: list[str] = []
    servers: list[ThreadingHTTPServer] = []
    threads: list[threading.Thread] = []
    client_thread: threading.Thread | None = None
    started_at = time.monotonic()

    class SlowModel(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["messages"][-1]["content"] == prompt
            received.set()
            if not release.wait(30):
                return
            payload = (
                json.dumps(
                    {
                        "model": "offline-fixture",
                        "message": {
                            "role": "assistant",
                            "content": done,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "echo",
                                        "arguments": {"text": marker},
                                    }
                                }
                            ],
                        },
                        "done": True,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()

    try:
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), SlowModel)
        proxy = create_proxy_server(
            listen_host="127.0.0.1",
            listen_port=0,
            config=ProxyConfig(
                upstream=f"http://127.0.0.1:{upstream.server_port}",
                sidecar=sidecar,
                mode="ollama",
            ),
        )
        state = live._LiveState(session_id, runtime, sidecar)
        token = uuid4().hex
        live_server = live._LocalThreadingHTTPServer(
            ("127.0.0.1", 0), live._handler_factory(state, token)
        )
        servers.extend((upstream, proxy, live_server))
        threads.extend(_start_server(server) for server in servers)

        def request() -> None:
            connection = http.client.HTTPConnection(
                "127.0.0.1", proxy.server_port, timeout=40
            )
            try:
                connection.request(
                    "POST",
                    "/api/chat",
                    body=json.dumps(
                        {
                            "model": "offline-fixture",
                            "stream": True,
                            "messages": [{"role": "user", "content": prompt}],
                            "tools": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "echo",
                                        "description": "Offline acceptance fixture",
                                    },
                                }
                            ],
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse().read().decode(
                    "utf-8", errors="replace"
                )
                if done not in response:
                    raise AssertionError(
                        "relay client did not receive the exact final marker"
                    )
            except Exception as exc:
                client_errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                connection.close()
                completed.set()

        client_thread = threading.Thread(target=request, daemon=True)
        client_thread.start()
        if not received.wait(5):
            raise AssertionError("offline model did not receive the request")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: console_errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{live_server.server_port}/?t={token}")
                node = page.locator('.node[data-id="agent:Ollama"]')
                node.click(timeout=10000)
                page.evaluate("window.__execweaveAcceptanceDocument=document")
                page.wait_for_function(
                    "marker=>document.querySelector('#details').innerText.includes(marker)",
                    arg=marker,
                    timeout=10000,
                )
                early = page.locator("#details").inner_text()
                early_final = early.partition("FINAL RESPONSE\n")[2].strip()
                early_events = _read_jsonl(sidecar)
                early_ok = (
                    prompt in early
                    and early_final != done
                    and not completed.is_set()
                    and not release.is_set()
                    and not any(
                        event.get("relation") == "OBSERVED_INFERENCE_RESPONSE"
                        for event in early_events
                    )
                )
                result.check(
                    "Launch",
                    True,
                    "Loopback model, ExecWeave proxy, live server and Chromium started",
                )
                if not early_ok:
                    raise AssertionError("prompt was not independently visible before response")
                page.screenshot(path=str(run_root / "01-prompt-before-response.png"))

                release.set()
                if not completed.wait(8):
                    raise AssertionError("relay client did not complete after response release")
                if client_errors:
                    raise AssertionError("; ".join(client_errors))
                page.wait_for_function(
                    "done=>document.querySelector('#details').innerText"
                    ".split('FINAL RESPONSE\\n')[1]?.trim()===done",
                    arg=done,
                    timeout=10000,
                )
                live_details = page.locator("#details").inner_text()
                same_document = page.evaluate(
                    "window.__execweaveAcceptanceDocument===document"
                )
                live_update_ok = same_document and live_details.count(prompt) == 1
                result.check(
                    "Live update",
                    live_update_ok,
                    "Prompt appeared before response and final updated in the same document",
                    "01-prompt-before-response.png",
                )
                page.screenshot(path=str(run_root / "02-live-final.png"))

                # The live snapshot comes from the live state's real projection.
                # Do not materialize an intentionally unfinished runtime stream.
                live_snapshot = _root_snapshot_from_payload(
                    state.conversation_index(run_root)
                )

                # Only after the completed live snapshot is captured do we record
                # session.finished and invoke the strict finished-stream validator.
                records[-1]["timestamp"] = datetime.now(timezone.utc).isoformat().replace(
                    "+00:00", "Z"
                )
                _write_jsonl(runtime, records)
                merged = run_root / "events.semantic.jsonl"
                graph = _materialize(runtime, sidecar, merged)
                write_execution_graph(
                    build_execution_graph(merged), run_root / "graph.json"
                )
                write_graph_html(graph, run_root / "viewer.html")
                finished_snapshot = _root_snapshot(graph, run_root)
                checked = verify_conversation(
                    finished_snapshot,
                    marker=marker,
                    done=done,
                    foreign_markers=(foreign,),
                )
                result.check(
                    "Prompt",
                    checked["Prompt"],
                    "Projected /root prompt contains the unique user marker",
                )
                result.check(
                    "Final",
                    checked["Final"],
                    "Projected assistant final equals the exact DONE marker",
                )
                result.check(
                    "/root",
                    checked["/root"] and checked["Isolation"],
                    "Ownership comes from conversation agent_path=/root; foreign marker absent",
                )

                sidecar_events = _read_jsonl(sidecar)
                source_ids = {
                    str((event.get("source") or {}).get("id"))
                    for event in sidecar_events
                    if isinstance(event.get("source"), dict)
                }
                tool_ok = _tool_call_observed(run_root, sidecar_events)
                result.check(
                    "Tool call",
                    tool_ok and len(source_ids) == 1,
                    "Assistant echo tool call observed on the same staged exchange identity",
                )

                page.goto((run_root / "viewer.html").as_uri())
                page.locator('.node[data-id="agent:Ollama"]').click(timeout=10000)
                finished_details = page.locator("#details").inner_text()
                parity = (
                    finished_details == live_details
                    and same_conversation(live_snapshot, finished_snapshot)
                    and _all_content_referenced(run_root, sidecar_events)
                )
                result.check(
                    "Finished viewer",
                    parity,
                    "Finished DOM equals completed live DOM and conversation/content parity holds",
                    "03-finished.png",
                )
                page.screenshot(path=str(run_root / "03-finished.png"))
                result.check(
                    "JS console",
                    not console_errors,
                    "No browser page errors were observed"
                    if not console_errors
                    else "; ".join(console_errors),
                )
                result.observed_requests = 1
            finally:
                browser.close()
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        for feature in (
            "Launch",
            "Prompt",
            "Final",
            "Tool call",
            "/root",
            "Live update",
            "Finished viewer",
            "JS console",
        ):
            if feature not in result.checks:
                result.check(feature, False, failure)
                break
    finally:
        release.set()
        if client_thread is not None:
            client_thread.join(5)
        for server in reversed(servers):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(5)
        cleanup_ok = all(not thread.is_alive() for thread in threads)
        if client_thread is not None:
            cleanup_ok = cleanup_ok and not client_thread.is_alive()
        result.check(
            "Cleanup",
            cleanup_ok,
            "All harness-owned server/client threads stopped; no child process was spawned",
        )
        result.runtime_seconds = time.monotonic() - started_at
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ExecWeave dashboard acceptance runner")
    parser.add_argument("--mode", choices=("offline",), default="offline")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/dashboard-acceptance"),
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="Provider result name that must PASS; may be repeated",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    headed = args.headed or os.environ.get("EXECWEAVE_ACCEPTANCE_HEADED") == "1"
    result = _run_offline(args.output_dir, headed)
    run_root = Path(result.artifacts)
    required = set(args.require) if args.require else {_PROVIDER}
    summary = write_report(run_root, [result], required)
    print(
        json.dumps(
            {"output": str(run_root), **summary},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0 if summary["status"] == Status.PASS.value else 1


if __name__ == "__main__":
    raise SystemExit(main())


"""Validate live and finished Dashboard materialization for real adapter sidecars."""
from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from execweave import live
from execweave.graph import build_execution_graph, write_execution_graph
from execweave.schema import Entity, RuntimeEvent
from execweave.semantic import merge_semantic_sidecar
from execweave.viewer_projection import write_graph_html
from playwright.sync_api import sync_playwright


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _entity(value: dict) -> Entity:
    return Entity(
        type=str(value["type"]),
        id=str(value["id"]),
        name=value.get("name"),
        attributes=dict(value.get("attributes") or {}),
    )


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _runtime_for_sidecar(sidecar: Path, runtime: Path) -> tuple[str, str]:
    records = _read_jsonl(sidecar)
    if not records:
        raise RuntimeError(f"sidecar is empty: {sidecar}")
    session_id = str(records[0]["attributes"]["session_id"])
    timestamps = [_ts(str(record["timestamp"])) for record in records]
    start = min(timestamps) - timedelta(seconds=2)
    finish = max(timestamps) + timedelta(seconds=2)
    agent_value = next(
        (record.get("source") for record in records if (record.get("source") or {}).get("type") == "agent"),
        None,
    )
    if not isinstance(agent_value, dict):
        raise RuntimeError(f"sidecar has no agent source: {sidecar}")
    process_value = None
    for record in records:
        for value in (record.get("source"), record.get("target")):
            if isinstance(value, dict) and value.get("type") == "process_reference":
                process_value = value
                break
        if process_value:
            break
    if process_value is None:
        raise RuntimeError(f"sidecar has no process reference: {sidecar}")
    process_attributes = dict(process_value.get("attributes") or {})
    pid = int(process_attributes["pid"])
    create_time = process_attributes.get("create_time")
    process = Entity(
        "process",
        f"framework-process:{session_id}:{pid}",
        str(process_attributes.get("executable") or f"pid {pid}"),
        {
            "pid": pid,
            "create_time": create_time,
            "ppid": 1,
            "executable": process_attributes.get("executable"),
        },
    )
    session = Entity("session", f"session:{session_id}", session_id, {})
    anchor_agent = _entity(agent_value)
    events = [
        RuntimeEvent.create(
            session_id=session_id,
            event_type="session.started",
            relation="STARTED_SESSION",
            timestamp=start.isoformat().replace("+00:00", "Z"),
            source=anchor_agent,
            target=session,
            attributes={"backend": "framework-dashboard-anchor"},
        ).to_dict(),
        RuntimeEvent.create(
            session_id=session_id,
            event_type="process.started",
            relation="LAUNCHED",
            timestamp=(start + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            source=session,
            target=process,
            attributes={"backend": "framework-dashboard-anchor", "causal": False},
        ).to_dict(),
        RuntimeEvent.create(
            session_id=session_id,
            event_type="session.finished",
            relation="FINISHED_SESSION",
            timestamp=finish.isoformat().replace("+00:00", "Z"),
            source=session,
            target=None,
            attributes={"backend": "framework-dashboard-anchor", "return_code": 0},
        ).to_dict(),
    ]
    for sequence, event in enumerate(events, start=1):
        event["sequence"] = sequence
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(
        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    return session_id, str(anchor_agent.id)


def _framework_signature(graph: dict) -> set[tuple[str, str, str, str]]:
    values: set[tuple[str, str, str, str]] = set()
    for node in graph.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type", ""))
        if node_type in {"agent", "task", "message", "model", "model_call", "tool", "tool_call", "process"}:
            values.add(("node", node_type, str(node.get("id")), ""))
    for edge in graph.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        values.add((
            "edge",
            str(edge.get("relation")),
            str(edge.get("source")),
            str(edge.get("target")),
        ))
    return values


def _start(server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _browser_check(
    *,
    state,
    session_id: str,
    token: str,
    server,
    final_graph: dict,
    final_html: str,
    output: Path,
    agent_id: str,
) -> dict:
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("console", lambda message: errors.append(f"console:{message.type}:{message.text}") if message.type == "error" else None)
            page.on("pageerror", lambda error: errors.append(f"pageerror:{error}"))
            url = f"http://127.0.0.1:{server.server_port}/?t={token}"
            page.goto(url)
            page.wait_for_function("document.querySelectorAll('.node').length > 0", timeout=15000)
            selector = f'.node[data-id="{agent_id}"]'
            page.locator(selector).click(timeout=10000)
            page.wait_for_function("document.querySelector('#details') && document.querySelector('#details').innerText.trim().length > 0", timeout=10000)
            live_details = page.locator("#details").inner_text()
            page.screenshot(path=str(output / "live.png"))
            state.finish(final_graph, final_html=final_html)
            page.goto(f"http://127.0.0.1:{server.server_port}/final?t={token}")
            page.locator(selector).click(timeout=10000)
            page.wait_for_function("document.querySelector('#details') && document.querySelector('#details').innerText.trim().length > 0", timeout=10000)
            finished_details = page.locator("#details").inner_text()
            page.screenshot(path=str(output / "finished.png"))
            browser_parity = live_details == finished_details and not errors
            return {
                "live_node_count": int(page.locator(".node").count()),
                "live_details_nonempty": bool(live_details.strip()),
                "finished_details_nonempty": bool(finished_details.strip()),
                "same_details": live_details == finished_details,
                "browser_console_errors": errors,
                "browser_parity": browser_parity,
            }
        finally:
            browser.close()


def validate_one(sidecar: Path) -> dict:
    output = sidecar.parent / "dashboard-real"
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "events.jsonl"
    merged = output / "events.semantic.jsonl"
    graph_path = output / "graph.semantic.json"
    viewer_path = output / "viewer.semantic.html"
    session_id, agent_id = _runtime_for_sidecar(sidecar, runtime)
    merge_result = merge_semantic_sidecar(runtime, sidecar, merged)
    final_graph_obj = build_execution_graph(merged)
    final_graph = final_graph_obj.to_dict()
    write_execution_graph(final_graph_obj, graph_path)
    write_graph_html(final_graph, viewer_path)

    state = live._LiveState(session_id, runtime, sidecar)
    provisional = state.snapshot()
    final_signature = _framework_signature(final_graph)
    live_signature = _framework_signature(provisional)
    token = uuid4().hex
    server = live._LocalThreadingHTTPServer(
        ("127.0.0.1", 0),
        live._handler_factory(state, token),
    )
    thread = _start(server)
    try:
        browser = _browser_check(
            state=state,
            session_id=session_id,
            token=token,
            server=server,
            final_graph=final_graph,
            final_html=viewer_path.read_text(encoding="utf-8"),
            output=output,
            agent_id=agent_id,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    report = {
        "sidecar": str(sidecar),
        "runtime": str(runtime),
        "merged": str(merged),
        "graph": str(graph_path),
        "viewer": str(viewer_path),
        "merge": merge_result.to_dict(),
        "live_framework_signature_count": len(live_signature),
        "finished_framework_signature_count": len(final_signature),
        "live_finished_framework_signature_parity": live_signature == final_signature,
        "unresolved_process_references": merge_result.unresolved_process_references,
        "browser": browser,
        "pass": (
            merge_result.unresolved_process_references == 0
            and live_signature == final_signature
            and browser["browser_parity"]
        ),
    }
    (output / "parity.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if not report["pass"]:
        raise RuntimeError(json.dumps(report, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sidecar", type=Path, nargs="+")
    args = parser.parse_args()
    reports = [validate_one(path.resolve()) for path in args.sidecar]
    print(json.dumps({"frameworks": reports}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

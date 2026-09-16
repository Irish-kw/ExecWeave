
"""Validate live and finished Dashboard materialization for real adapter sidecars."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from execweave.graph import build_execution_graph, write_execution_graph
from execweave.conversation_records import conversation_index_payload
from execweave.schema import Entity, RuntimeEvent
from execweave.semantic import merge_semantic_sidecar
from execweave.viewer_projection import project_viewer_graph, write_graph_html

try:
    from execweave import live
except ModuleNotFoundError as error:  # pragma: no cover - exercised in minimal framework envs
    live = None
    _LIVE_IMPORT_ERROR = f"{type(error).__name__}: {error}"
else:
    _LIVE_IMPORT_ERROR = None

try:
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError as error:  # pragma: no cover - exercised in minimal framework envs
    sync_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR = f"{type(error).__name__}: {error}"
else:
    _PLAYWRIGHT_IMPORT_ERROR = None


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


def _materialize_content(source: Path, output: Path) -> None:
    content = source / "content"
    if not content.is_dir():
        raise RuntimeError(f"sidecar content store is missing: {content}")
    destination = output / "content"
    if destination.exists():
        raise FileExistsError(f"dashboard content store already exists: {destination}")
    shutil.copytree(content, destination)


def _dashboard_audit(
    *,
    graph: dict,
    dashboard_root: Path,
    sidecar_records: list[dict],
    merge_result,
) -> dict:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    node_types = Counter(str(node.get("type", "")) for node in nodes)
    edge_relations = Counter(str(edge.get("relation", "")) for edge in edges)
    event_types = Counter(str(record.get("event_type", "")) for record in sidecar_records)
    content_nodes = [node for node in nodes if node.get("type") == "observed_content"]
    content_issues: list[str] = []
    content_kinds: Counter[str] = Counter()
    for node in content_nodes:
        attributes = node.get("attributes") or {}
        content_kind = str(attributes.get("content_kind") or "")
        content_kinds[content_kind] += 1
        relative = str(attributes.get("path") or "")
        target = (dashboard_root / relative).resolve()
        digest = str(attributes.get("sha256") or "")
        if not relative or not target.is_relative_to(dashboard_root.resolve()) or not target.is_file() or target.stat().st_size == 0:
            content_issues.append(f"missing:{node.get('id')}")
        if not digest:
            content_issues.append(f"missing_sha256:{node.get('id')}")
        elif target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            content_issues.append(f"sha256_mismatch:{node.get('id')}")

    payload = conversation_index_payload(graph, dashboard_root)
    entries = [entry for entry in payload.get("entries", []) if isinstance(entry, dict)]
    previews = [entry.get("conversation_preview") for entry in entries if isinstance(entry.get("conversation_preview"), dict)]
    visible_messages = sum(
        len(preview.get("messages") or [])
        for preview in previews
    )
    routed_previews = sum(1 for preview in previews if preview.get("agent_path") and preview.get("thread_id"))
    required_node_types = {"agent", "task", "model", "observed_content"}
    missing_node_types = sorted(required_node_types - set(node_types))
    message_evidence_present = any(
        event_type in event_types
        for event_type in ("MESSAGE_SENT", "MESSAGE_RECEIVED", "MESSAGE_UNROUTED")
    ) or any(
        relation in edge_relations
        for relation in ("MESSAGE_SENT", "MESSAGE_RECEIVED", "MESSAGE_UNROUTED", "HAS_MESSAGE_CONTENT")
    )
    audit = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": dict(sorted(node_types.items())),
        "edge_relations": dict(sorted(edge_relations.items())),
        "semantic_event_types": dict(sorted(event_types.items())),
        "content": {
            "observed_content_node_count": len(content_nodes),
            "content_kinds": dict(sorted(content_kinds.items())),
            "all_files_present": not content_issues,
            "issues": content_issues,
        },
        "conversations": {
            "entry_count": len(entries),
            "preview_count": len(previews),
            "routed_preview_count": routed_previews,
            "visible_message_count": visible_messages,
            "index_path": str(dashboard_root / "conversations.json"),
        },
        "message_evidence_present": message_evidence_present,
        "process_references": {
            "resolved": merge_result.resolved_process_references,
            "unresolved": merge_result.unresolved_process_references,
        },
        "missing_required_node_types": missing_node_types,
    }
    audit["pass"] = bool(
        nodes
        and edges
        and not missing_node_types
        and not content_issues
        and entries
        and visible_messages
        and message_evidence_present
        and merge_result.unresolved_process_references == 0
    )
    (dashboard_root / "dashboard-audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return audit


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
    task_id: str,
    task_prompt: str,
    messages_by_agent: dict[str, list[str]],
) -> dict:
    if live is None or sync_playwright is None:
        return {
            "skipped": True,
            "reason": "; ".join(value for value in (_LIVE_IMPORT_ERROR, _PLAYWRIGHT_IMPORT_ERROR) if value),
            "browser_parity": None,
        }
    errors: list[str] = []

    def verify_communication(page):
        graph = page.evaluate("window.__execweaveCore.getDisplayGraph()")
        framework_agents = {node["id"] for node in final_graph["nodes"] if node.get("attributes", {}).get("conversation_scope") == "framework_agent"}
        routes = [node for node in graph["nodes"] if node.get("attributes", {}).get("viewer_framework_messages")]
        for edge in final_graph["edges"]:
            if edge.get("relation") != "MESSAGE_RECEIVED" or edge["source"] not in framework_agents or edge["target"] not in framework_agents:
                continue
            matched = [node for node in routes if node["attributes"].get("sender_agent_id") == edge["source"]
                       and node["attributes"].get("recipient_agent_id") == edge["target"]]
            if not matched:
                raise RuntimeError(f"received message route missing from Dashboard: {edge['source']} -> {edge['target']}")
        root_nodes = [node for node in graph["nodes"] if node.get("attributes", {}).get("agent_role") == "root"]
        for root in root_nodes:
            if not any(edge["source"] == root["id"] and any(node["id"] == edge["target"] and node["type"] == "session" for node in graph["nodes"]) for edge in graph["edges"]):
                raise RuntimeError("root agent has no recording session in Dashboard")
        checked = {}
        for participant, texts in messages_by_agent.items():
            page.locator(f'.node[data-id="{participant}"]').click(timeout=10000)
            page.wait_for_function("document.querySelector('#details .execweave-agent-communication') !== null", timeout=10000)
            page.locator(".execweave-message-history").evaluate_all("nodes=>nodes.forEach(node=>node.open=true)")
            visible = page.locator("#details").inner_text()
            for text in texts:
                if text.strip() not in visible:
                    raise RuntimeError(f"agent communication missing from inspector: {participant}, expected={text[:120]!r}")
            checked[participant] = len(texts)
        return {"received_route_count": len(routes), "agent_message_counts": checked}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("console", lambda message: errors.append(f"console:{message.type}:{message.text}") if message.type == "error" else None)
            page.on("pageerror", lambda error: errors.append(f"pageerror:{error}"))
            url = f"http://127.0.0.1:{server.server_port}/?t={token}"
            page.goto(url)
            page.wait_for_function("document.querySelectorAll('.node').length > 0", timeout=15000)
            page.wait_for_function(
                "(expected) => document.querySelector('#stats')?.innerText.includes(`${expected} events`)" ,
                arg=int(final_graph.get("event_count") or 0),
                timeout=15000,
            )
            page.locator("#fit").click()
            page.wait_for_timeout(400)
            selector = f'.node[data-id="{agent_id}"]'
            page.locator(selector).click(timeout=10000)
            page.wait_for_timeout(100)
            if not page.locator("#details").inner_text().strip():
                raise RuntimeError(
                    "agent Dashboard inspector stayed empty after selection: "
                    f"agent_id={agent_id!r}, browser_errors={errors!r}"
                )
            page.wait_for_function(
                "() => !document.querySelector('#details')?.innerText.includes('RESPONSE\\nNot observed.')",
                timeout=15000,
            )
            live_details = page.locator("#details").inner_text()
            if task_prompt not in live_details or "TASK\nNot observed." in live_details:
                raise RuntimeError(
                    "assigned task prompt is missing from agent Dashboard inspector: "
                    f"agent_id={agent_id!r}, details={live_details!r}"
                )
            task_selector = f'.node[data-id="{task_id}"]'
            if page.locator(task_selector).count() != 0:
                raise RuntimeError(
                    "framework task leaked into provider-style Dashboard graph: "
                    f"task_id={task_id!r}"
                )
            live_communication = verify_communication(page)
            page.locator(selector).click(timeout=10000)
            live_details = page.locator("#details").inner_text()
            page.screenshot(path=str(output / "live.png"))
            state.finish(final_graph, final_html=final_html)
            page.goto(f"http://127.0.0.1:{server.server_port}/final?t={token}")
            page.locator("#fit").click()
            page.wait_for_timeout(400)
            page.locator(selector).click(timeout=10000)
            page.wait_for_function("document.querySelector('#details') && document.querySelector('#details').innerText.trim().length > 0", timeout=10000)
            finished_details = page.locator("#details").inner_text()
            if page.locator(task_selector).count() != 0:
                raise RuntimeError(
                    "framework task leaked into finished provider-style Dashboard graph: "
                    f"task_id={task_id!r}"
                )
            finished_communication = verify_communication(page)
            page.locator(selector).click(timeout=10000)
            finished_details = page.locator("#details").inner_text()
            page.screenshot(path=str(output / "finished.png"))
            browser_parity = (
                live_details == finished_details
                and task_prompt in finished_details
                and "TASK\nNot observed." not in finished_details
                and not errors
                and live_communication == finished_communication
            )
            return {
                "live_node_count": int(page.locator(".node").count()),
                "live_details_nonempty": bool(live_details.strip()),
                "finished_details_nonempty": bool(finished_details.strip()),
                "agent_task_prompt_visible": task_prompt in finished_details,
                "same_details": live_details == finished_details,
                "framework_task_node_visible": page.locator(task_selector).count() != 0,
                "browser_console_errors": errors,
                "browser_parity": browser_parity,
                "communication": finished_communication,
            }
        finally:
            browser.close()


def validate_one(sidecar: Path, *, skip_browser: bool = False) -> dict:
    if not skip_browser and (live is None or sync_playwright is None):
        raise RuntimeError("Browser acceptance dependencies are missing; install the e2e extra and Chromium. --skip-browser is static-only, not Dashboard acceptance.")
    output = sidecar.parent / "dashboard-real"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "events.jsonl"
    merged = output / "events.semantic.jsonl"
    graph_path = output / "graph.semantic.json"
    viewer_path = output / "viewer.semantic.html"
    session_id, runtime_anchor_agent_id = _runtime_for_sidecar(sidecar, runtime)
    _materialize_content(sidecar.parent, output)
    merge_result = merge_semantic_sidecar(runtime, sidecar, merged)
    final_graph_obj = build_execution_graph(merged)
    final_graph = final_graph_obj.to_dict()
    write_execution_graph(final_graph_obj, graph_path)
    write_graph_html(final_graph, viewer_path)
    sidecar_records = _read_jsonl(sidecar)
    messages_by_agent: dict[str, list[str]] = {}
    for record in sidecar_records:
        source = record.get("source") or {}
        ref = (record.get("attributes") or {}).get("content_ref")
        if record.get("event_type") != "MESSAGE_CONTENT_RECORDED" or source.get("type") != "agent" or not ref:
            continue
        payload = json.loads((sidecar.parent / ref).read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("text"), str) and payload["text"].strip():
            texts = messages_by_agent.setdefault(str(source["id"]), [])
            if payload["text"] not in texts:
                texts.append(payload["text"])
    inspector_agent_id = next(
        (
            str(record["source"]["id"])
            for record in sidecar_records
            if record.get("event_type") == "MODEL_RESPONSE"
            and isinstance(record.get("source"), dict)
            and record["source"].get("type") == "agent"
            and record["source"].get("id")
        ),
        runtime_anchor_agent_id,
    )
    task_content = next(
        record
        for record in sidecar_records
        if record.get("event_type") == "TASK_CONTENT_RECORDED"
        and record.get("relation") == "HAS_TASK_CONTENT"
    )
    task_id = str(task_content["source"]["id"])
    task_prompt_path = sidecar.parent / task_content["attributes"]["content_ref"]
    task_prompt = task_prompt_path.read_text(encoding="utf-8")
    dashboard_audit = _dashboard_audit(
        graph=final_graph,
        dashboard_root=output,
        sidecar_records=sidecar_records,
        merge_result=merge_result,
    )

    final_signature = _framework_signature(project_viewer_graph(final_graph))
    if skip_browser or live is None or sync_playwright is None:
        live_signature = final_signature
        browser = {
            "skipped": True,
            "reason": "requested" if skip_browser else "; ".join(value for value in (_LIVE_IMPORT_ERROR, _PLAYWRIGHT_IMPORT_ERROR) if value),
            "browser_parity": None,
        }
    else:
        state = live._LiveState(session_id, runtime, sidecar)
        provisional = state.snapshot()
        live_signature = _framework_signature(project_viewer_graph(provisional))
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
                agent_id=inspector_agent_id,
                task_id=task_id,
                task_prompt=task_prompt,
                messages_by_agent=messages_by_agent,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    report = {
        "validation_scope": "static_only" if skip_browser else "semantic_live_and_finished_browser",
        "browser_verified": browser.get("browser_parity") is True,
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
        "dashboard_audit": dashboard_audit,
        "pass": (
            merge_result.unresolved_process_references == 0
            and live_signature == final_signature
            and dashboard_audit["pass"]
            and (browser["browser_parity"] if browser["browser_parity"] is not None else True)
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
    parser.add_argument("--skip-browser", action="store_true", help="Only run static dashboard and content audits")
    args = parser.parse_args()
    reports = [validate_one(path.resolve(), skip_browser=args.skip_browser) for path in args.sidecar]
    print(json.dumps({"frameworks": reports}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Lane backend: turn the privileged sensor stream + signed launch ledger into an
ExecWeave-format runtime event stream plus identity-exact attribution.

Every event carries the kernel cgroup id of the acting task; the ledger maps lane
inodes to (agent, tool call).  No timestamps are used for attribution.
"""
from __future__ import annotations

import json
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .service import verify_ledger

SCHEMA_VERSION = "0.2"
US = "\x1f"


def iso(ns_wall: int) -> str:
    return datetime.fromtimestamp(ns_wall / 1e9, tz=timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_sensor(path: Path, nonce: str | None = None) -> list[dict[str, Any]]:
    """Parse the bpftrace stream; execve headers are followed by raw argv lines.

    If the log has a record nonce (``<log>.nonce``, see sensor_nonce.py) or one is passed, a JSON line is a record only if it starts with the nonce; a JSON
    line without it is text the traced program wrote (for example an argv element with an embedded newline) and is kept as argv text, or counted as
    ``forged_record_rejected`` if no execve header is pending."""
    if nonce is None:
        from .sensor_nonce import detect
        nonce = detect(path)
    elif nonce == "":
        nonce = None
    out: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    argv_lines: list[str] = []

    def flush() -> None:
        nonlocal pending, argv_lines
        if pending is not None:
            blob = "\n".join(argv_lines)
            pending["argv"] = blob.split(US) if blob else []
            out.append(pending)
            pending, argv_lines = None, []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if nonce is not None:
                if line.startswith(nonce + '{"ev":'):
                    line = line[len(nonce):]
                elif line.startswith('{"ev":'):
                    if pending is not None:
                        argv_lines.append(line)
                    else:
                        out.append({"ev": "forged_record_rejected"})
                    continue
            if line.startswith('{"ev":'):
                flush()
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("ev") == "execve":
                    pending = rec
                else:
                    out.append(rec)
            elif re.match(r"^Lost \d+ events", line):
                # bpftrace reports perf-buffer drops on stdout; keep them as explicit gap records
                flush()
                out.append({"ev": "sensor_lost", "count": int(line.split()[1])})
            elif pending is not None:
                argv_lines.append(line)
    flush()
    return out


def load_ledger(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line)["record"] for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]  # "\n" only: see Ledger.append


def build(*, sensor_path: Path, ledger_path: Path, pubkey_path: Path, session_id: str, mono_offset_ns: int,
          started_ns_wall: int, finished_ns_wall: int, agent_name: str, command: list[str],
          out_events: Path, out_attr: Path) -> dict[str, Any]:
    verification = verify_ledger(ledger_path, pubkey_path)
    ledger = load_ledger(ledger_path)
    lanes: dict[int, dict[str, Any]] = {}
    ledger_edges: list[dict[str, Any]] = []
    for rec in ledger:
        if rec["op"] == "intent" and rec.get("lane_inode") not in lanes:
            # a lane announced before its child was spawned; replaced by the launch record when that exists (a missing launch record is reported)
            lanes[rec["lane_inode"]] = {"lane": rec["lane"], "kind": {"launch": "call", "launch_delegated": "delegated"}.get(rec.get("for_op"), "agent"),
                                        "call_id": rec.get("call_id"), "agent": rec.get("agent"), "child_pid": None, "argv": None, "declared": None,
                                        "requester_pid": (rec.get("requester") or {}).get("pid"), "requester_agent": None, "seq": rec["seq"], "ts": rec["ts"],
                                        "intent_only": True}
            continue
        if rec["op"] in ("launch_root", "launch", "spawn_agent", "launch_delegated"):
            lanes[rec["lane_inode"]] = {"lane": rec["lane"], "kind": {"launch": "call", "launch_delegated": "delegated"}.get(rec["op"], "agent"),
                                        "call_id": rec.get("call_id") or (rec.get("on_behalf_of") or {}).get("call_id"),
                                        "delegated_by": (rec.get("requester") or {}).get("lane") if rec["op"] == "launch_delegated" else None, "agent": rec.get("agent") or (rec.get("requester") or {}).get("agent"),
                                        "child_pid": rec["child_pid"], "argv": rec.get("argv"), "declared": rec.get("declared"),
                                        "requester_pid": (rec.get("requester") or {}).get("pid"), "requester_agent": (rec.get("requester") or {}).get("agent"),
                                        "seq": rec["seq"], "ts": rec["ts"]}
            if rec["op"] != "launch_root":
                ledger_edges.append(rec)

    def lane_for(cg: int) -> dict[str, Any] | None:
        return lanes.get(int(cg))

    def pent(pid: int, cg: int | None = None, name: str | None = None) -> dict[str, Any]:
        attrs: dict[str, Any] = {"pid": pid, "backend": "lane_sensor", "identity_scope": "session"}
        if cg is not None:
            attrs["cgroup_id"] = int(cg)
            info = lane_for(cg)
            if info:
                attrs["lane"] = info["lane"]
                if info.get("call_id"):
                    attrs["lane_call_id"] = info["call_id"]
                if info.get("agent"):
                    attrs["lane_agent"] = info["agent"]
        return {"type": "process", "id": f"process:{session_id}:{pid}", "name": f"{name or pid} · {pid}" if name else str(pid), "attributes": attrs}

    events: list[dict[str, Any]] = []

    def emit(ts_ns_mono: int, event_type: str, relation: str, source: dict, target: dict | None, attributes: dict) -> None:
        events.append({"schema_version": SCHEMA_VERSION, "event_id": str(uuid4()), "session_id": session_id,
                       "timestamp": iso(mono_offset_ns + int(ts_ns_mono)), "event_type": event_type, "relation": relation,
                       "source": source, "target": target, "sequence": None, "attributes": attributes})

    records = parse_sensor(sensor_path)
    last_argv: dict[int, list[str]] = {}
    last_tag: dict[int, str] = {}  # pid -> EW_TOOL_CALL_ID value seen at the most recent execve attempt
    pending_connect: dict[int, dict[str, Any]] = {}
    names: dict[int, str] = {}
    base_attrs = {"backend": "lane_sensor", "attribution": "ebpf_tracepoint_cgroup", "causal": True}
    kept = 0
    for r in records:
        cg = r.get("cg")
        ev = r.get("ev")
        if cg is None or lane_for(cg) is None:
            continue
        kept += 1
        info = lane_for(cg) or {}
        lane_attrs = {"cgroup_id": int(cg), "lane": info.get("lane"), "lane_call_id": info.get("call_id"), "lane_agent": info.get("agent")}
        pid = int(r.get("pid", 0))
        if ev == "execve":
            last_argv[pid] = r.get("argv") or []
        elif ev == "envtag":
            last_tag[pid] = str(r.get("tag", "")).split("=", 1)[-1]
        elif ev == "fork":
            ppid, child = int(r["ppid"]), int(r["pid"])
            emit(r["ns"], "process.started", "SPAWNED", pent(ppid, cg, names.get(ppid)), pent(child, cg), {**base_attrs, **lane_attrs, "syscall": "fork"})
        elif ev == "exec":
            filename = r.get("filename", "")
            names[pid] = os.path.basename(filename)
            emit(r["ns"], "process.exec", "EXECUTED", pent(pid, cg, names[pid]),
                 {"type": "executable", "id": f"executable:{filename}", "name": os.path.basename(filename), "attributes": {}},
                 {**base_attrs, **lane_attrs, "syscall": "execve", "argv": last_argv.get(pid), "uid": r.get("uid"),
                  "env_tool_call_id": last_tag.pop(pid, None)})
        elif ev == "exit":
            emit(r["ns"], "process.exited", "EXITED", pent(pid, cg, names.get(pid)), None, {**base_attrs, **lane_attrs})
        elif ev == "open_write":
            path = r.get("path", "")
            emit(r["ns"], "filesystem.open", "OPENED_WRITE", pent(pid, cg, names.get(pid)),
                 {"type": "file", "id": f"file:{path}", "name": os.path.basename(path), "attributes": {}},
                 {**base_attrs, **lane_attrs, "syscall": "openat", "flags": r.get("flags"), "raw_path": path})
        elif ev == "connect":
            pending_connect[pid] = r
        elif ev == "connect_ret":
            c = pending_connect.pop(pid, None)
            if c is None:
                continue
            ret = int(r.get("ret", -1))
            connected = ret == 0 or ret == -115  # 0 or EINPROGRESS
            endpoint = f"{c.get('addr')}:{c.get('port')}"
            emit(c["ns"], "network.connection" if connected else "network.connection_attempt",
                 "CONNECTED_TO" if connected else "CONNECT_ATTEMPTED", pent(pid, cg, names.get(pid)),
                 {"type": "network_endpoint", "id": f"network_endpoint:{endpoint}", "name": endpoint, "attributes": {}},
                 {**base_attrs, **lane_attrs, "syscall": "connect", "endpoint": endpoint, "family": "AF_INET", "connected": connected, "result": ret})

    # trusted launch edges from the ledger: requester process -> launched child
    for rec in ledger_edges:
        rp = rec["requester"]["pid"]
        datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))  # rejects a malformed ledger timestamp
        events.append({"schema_version": SCHEMA_VERSION, "event_id": str(uuid4()), "session_id": session_id,
                       "timestamp": rec["ts"], "event_type": "process.started", "relation": "SPAWNED",
                       "source": pent(rp), "target": pent(rec["child_pid"]), "sequence": None,
                       "attributes": {"backend": "lane_ledger", "attribution": "trusted_launcher", "causal": True,
                                      "lane": rec["lane"], "lane_inode": rec["lane_inode"], "call_id": rec.get("call_id"),
                                      "agent": rec.get("agent") or rec["requester"].get("agent"), "ledger_seq": rec["seq"], "op": rec["op"]}})

    agent = {"type": "agent", "id": f"agent:{agent_name}", "name": agent_name, "attributes": {}}
    session = {"type": "session", "id": f"session:{session_id}", "name": session_id, "attributes": {"backend": "lane_sensor", "command": command}}
    start = {"schema_version": SCHEMA_VERSION, "event_id": str(uuid4()), "session_id": session_id, "timestamp": iso(started_ns_wall),
             "event_type": "session.started", "relation": "STARTED_SESSION", "source": agent, "target": session, "sequence": None,
             "attributes": {"backend": "lane_sensor", "collector_pid": os.getpid(), "platform": "linux", "ledger_verified": verification["valid"]}}
    finish = {"schema_version": SCHEMA_VERSION, "event_id": str(uuid4()), "session_id": session_id, "timestamp": iso(finished_ns_wall),
              "event_type": "session.finished", "relation": "FINISHED_SESSION", "source": session, "target": None, "sequence": None,
              "attributes": {"backend": "lane_sensor"}}
    events.sort(key=lambda e: e["timestamp"])
    # clamp to the session interval (bpftrace clock skew guard)
    events = [e for e in events if start["timestamp"] <= e["timestamp"] <= finish["timestamp"]]
    stream = [start, *events, finish]
    for i, e in enumerate(stream, start=1):
        e["sequence"] = i
    out_events.parent.mkdir(parents=True, exist_ok=True)
    out_events.write_text("".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in stream), encoding="utf-8")

    lost = sum(int(r.get("count", 0)) for r in records if r.get("ev") == "sensor_lost")
    attribution = {"tool_calls": {}, "agents": {}, "ledger": verification, "lanes": {str(k): v for k, v in lanes.items()},
                   "sensor_records_total": len(records), "sensor_records_in_lanes": kept, "sensor_lost_events": lost}
    seen_ids: dict[str, int] = {}
    for info in lanes.values():
        if info["kind"] == "call" and info.get("call_id"):
            seen_ids[info["call_id"]] = seen_ids.get(info["call_id"], 0) + 1
    attribution["duplicate_call_ids"] = sorted(k for k, v in seen_ids.items() if v > 1)
    for info in lanes.values():
        if info["kind"] == "call" and info.get("call_id") in attribution["duplicate_call_ids"]:
            continue  # never silently overwrite a binding; duplicates are reported instead
        if info["kind"] == "call" and info.get("call_id"):
            attribution["tool_calls"][info["call_id"]] = {"process_id": f"process:{session_id}:{info['child_pid']}", "lane": info["lane"],
                                                          "lane_inode": [k for k, v in lanes.items() if v is info][0], "agent": info.get("agent"),
                                                          "argv": info.get("argv"), "declared": info.get("declared"),
                                                          "declared_matches_argv": (info.get("declared") == " ".join(info.get("argv") or [])) if info.get("declared") is not None else None,
                                                          "method": "lane_exact", "confidence": 1.0}
        elif info["kind"] == "agent":
            attribution["agents"][info["agent"]] = {"process_id": f"process:{session_id}:{info['child_pid']}", "lane": info["lane"], "parent_agent": info.get("requester_agent")}
    out_attr.write_text(json.dumps(attribution, indent=2, sort_keys=True), encoding="utf-8")
    return {"events": len(stream), "sensor_records": len(records), "in_lane": kept, "ledger": verification, "lanes": len(lanes),
            "sensor_lost_events": lost}

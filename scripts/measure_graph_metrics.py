"""Quantitative Geometry Metrics Tool for ExecWeave Graphs.

Extracts layout and geometry metrics according to Section 5:
- graph_width
- graph_height
- aspect_ratio
- fit_scale
- edge_crossings
- max_edge_length
- p95_edge_length
- secondary_component_count
- visible_node_count
- visible_edge_count

Usage:
    python scripts/measure_graph_metrics.py
    python scripts/measure_graph_metrics.py --output artifacts/before-metrics.json
    python scripts/measure_graph_metrics.py --fixture single-agent
    python scripts/measure_graph_metrics.py --input path/to/graph.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# ==============================================================================
# Layout Constants matching live_view_readability.py
# ==============================================================================
EXECWEAVE_NODE_W = 160
EXECWEAVE_NODE_H = 50
EXECWEAVE_ROW_GAP = 104
EXECWEAVE_NODE_W_MAX = 320
EXECWEAVE_LABEL_PAD = 20
EXECWEAVE_LINE_H = 14
EXECWEAVE_LANES = {
    "runtime": 0,
    "root": 1,
    "agent": 2,
    "model": 3,
    "tool": 4,
    "file": 5,
    "endpoint": 6,
    "other": 6,
}
EXECWEAVE_LANE_ORDER = ["runtime", "root", "agent", "model", "tool", "file", "endpoint"]
EXECWEAVE_LANE_GAP = {
    "runtime": 110,
    "root": 110,
    "agent": 120,
    "model": 120,
    "tool": 120,
    "file": 120,
    "endpoint": 120,
    "other": 120,
}
EXECWEAVE_BAND_GAP = 170

# Standard acceptance dashboard viewport dimensions
VIEWPORT_BOX_W = 1600 - 340  # 1260
VIEWPORT_BOX_H = 1000 - 64 - 230 - 46  # 660


# ==============================================================================
# Node Measurement & Classification
# ==============================================================================
def execweave_measure(text: str) -> float:
    value = str(text or "")
    if not value:
        return 0.0
    return len(value) * 7.1


def execweave_node_label(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("id") or node.get("type") or "node")


def execweave_node_width(node: dict[str, Any]) -> float:
    wanted = execweave_measure(execweave_node_label(node)) + EXECWEAVE_LABEL_PAD
    return max(EXECWEAVE_NODE_W, min(EXECWEAVE_NODE_W_MAX, math.ceil(wanted)))


def execweave_wrap_label(text: str, width: float) -> list[str]:
    value = str(text or "")
    room = width - EXECWEAVE_LABEL_PAD
    if execweave_measure(value) <= room:
        return [value]
    cut = 0
    for index in range(1, len(value)):
        if execweave_measure(value[:index]) > room:
            break
        if value[index - 1] in "/_-. :":
            cut = index
    if not cut:
        low = 0
        high = len(value)
        while low < high:
            mid = math.ceil((low + high) / 2)
            if execweave_measure(value[:mid]) <= room:
                low = mid
            else:
                high = mid - 1
        cut = max(1, low)
    return [value[:cut], value[cut:]]


def execweave_node_height(node: dict[str, Any], width: float) -> float:
    lines = execweave_wrap_label(execweave_node_label(node), width)
    return EXECWEAVE_NODE_H + (EXECWEAVE_LINE_H if len(lines) > 1 else 0)


def execweave_attrs(node: dict[str, Any]) -> dict[str, Any]:
    attrs = node.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def execweave_agent_path(node: dict[str, Any]) -> str:
    a = execweave_attrs(node)
    return str(
        a.get("agent_path")
        or a.get("child_agent_path")
        or a.get("root_agent_path")
        or node.get("name")
        or node.get("id")
        or ""
    )


def execweave_relation(edge: dict[str, Any]) -> str:
    return str(edge.get("relation") or "").upper()


def execweave_is_spawn(edge: dict[str, Any]) -> bool:
    val = execweave_relation(edge)
    return val == "SPAWNED_AGENT" or "SPAWNED_AGENT" in val or "SPAWN_AGENT" in val


def execweave_is_stopped(edge: dict[str, Any]) -> bool:
    val = execweave_relation(edge)
    return val == "SUBAGENT_STOPPED" or "SUBAGENT_STOPPED" in val


def execweave_is_root(node: dict[str, Any]) -> bool:
    if node.get("type") != "agent":
        return False
    a = execweave_attrs(node)
    if "viewer_root" in a:
        return a["viewer_root"] is True
    return (
        a.get("agent_role") == "root"
        or a.get("root_agent_path") == "/root"
        or a.get("agent_path") == "/root"
        or execweave_agent_path(node) == "/root"
    )


def execweave_lane(node: dict[str, Any]) -> str:
    type_str = str(node.get("type") or "").lower()
    if type_str == "agent":
        return "root" if execweave_is_root(node) else "agent"
    if any(k in type_str for k in ("model", "inference", "llm")):
        return "model"
    if "tool" in type_str:
        return "tool"
    if any(k in type_str for k in ("file", "path")):
        return "file"
    if any(k in type_str for k in ("network", "endpoint", "socket", "host")):
        return "endpoint"
    if any(k in type_str for k in ("process", "session", "runtime", "shell")):
        return "runtime"
    return "other"


def execweave_lane_x(width_by_lane: dict[str, float], occupied: set[str]) -> dict[str, float]:
    lane_x = {}
    x = 0.0
    for lane in EXECWEAVE_LANE_ORDER:
        lane_x[lane] = x
        if not occupied or lane in occupied:
            w = max(EXECWEAVE_NODE_W, width_by_lane.get(lane, EXECWEAVE_NODE_W))
            x += w + EXECWEAVE_LANE_GAP.get(lane, 120)
    lane_x["other"] = lane_x["endpoint"]
    return lane_x


def execweave_moment(edge: dict[str, Any]) -> str:
    if isinstance(edge.get("first_sequence"), int):
        return f"0:{edge['first_sequence']:012d}"
    if edge.get("first_seen"):
        return f"1:{edge['first_seen']}"
    return f"2:{edge.get('id', '')}"


def execweave_stable_node_sort_key(node: dict[str, Any]) -> tuple[str, str]:
    return (
        str(node.get("name") or node.get("id") or ""),
        str(node.get("id") or ""),
    )


def execweave_components(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    adjacent: dict[str, list[str]] = {n["id"]: [] for n in nodes if "id" in n}
    for edge in edges:
        s, t = edge.get("source"), edge.get("target")
        if s in adjacent and t in adjacent:
            adjacent[s].append(t)
            adjacent[t].append(s)

    component_of: dict[str, int] = {}
    index = 0
    sorted_nodes = sorted(nodes, key=execweave_stable_node_sort_key)
    for node in sorted_nodes:
        nid = node["id"]
        if nid in component_of:
            continue
        queue = [nid]
        component_of[nid] = index
        while queue:
            curr = queue.pop()
            for neighbor in adjacent.get(curr, []):
                if neighbor not in component_of:
                    component_of[neighbor] = index
                    queue.append(neighbor)
        index += 1
    return component_of


# ==============================================================================
# Full Topology & Layout Calculation
# ==============================================================================
class NodePlacement:
    def __init__(self, node_id: str, lane: str, rank: int, order: int, x: float, y: float):
        self.node_id = node_id
        self.lane = lane
        self.rank = rank
        self.order = order
        self.x = x
        self.y = y
        self.lane_count = 1


def execweave_build_topology(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    node_by_id = {n["id"]: n for n in nodes if "id" in n}

    spawn_for: dict[str, dict[str, Any]] = {}
    for edge in edges:
        if not execweave_is_spawn(edge):
            continue
        s = node_by_id.get(edge.get("source", ""))
        t = node_by_id.get(edge.get("target", ""))
        if s and t and s.get("type") == "agent" and t.get("type") == "agent":
            curr = spawn_for.get(t["id"])
            if not curr or execweave_moment(edge) < execweave_moment(curr):
                spawn_for[t["id"]] = edge

    roots = [n for n in nodes if execweave_is_root(n)]
    roots.sort(key=execweave_stable_node_sort_key)

    children = [n for n in nodes if n.get("type") == "agent" and not execweave_is_root(n)]

    def child_sort_key(n: dict[str, Any]):
        sp = spawn_for.get(n["id"])
        m = execweave_moment(sp) if sp else "9:"
        return (m, execweave_agent_path(n), execweave_stable_node_sort_key(n))

    children.sort(key=child_sort_key)

    child_order = {n["id"]: idx for idx, n in enumerate(children)}
    root_y = 100 + ((len(children) - 1) * EXECWEAVE_ROW_GAP) / 2 if children else 100.0

    by_lane: dict[str, list[dict[str, Any]]] = {lane: [] for lane in EXECWEAVE_LANES}
    for n in nodes:
        by_lane[execweave_lane(n)].append(n)

    def source_barycentre(node: dict[str, Any]) -> float:
        touching = [
            e for e in edges
            if e.get("target") == node["id"] and e.get("source") in child_order
        ]
        if not touching:
            return float("inf")
        return sum(child_order.get(e["source"], 0) for e in touching) / len(touching)

    by_lane["runtime"].sort(key=execweave_stable_node_sort_key)
    for lane in ["model", "file", "endpoint", "other"]:
        by_lane[lane].sort(key=lambda n: (source_barycentre(n), execweave_stable_node_sort_key(n)))

    def tool_sort_key(n: dict[str, Any]):
        collab = bool(
            re.search(
                r"spawn|send|wait|agent",
                str(n.get("name") or execweave_attrs(n).get("tool_name") or ""),
                re.IGNORECASE,
            )
        )
        return (0 if collab else 1, source_barycentre(n), execweave_stable_node_sort_key(n))

    by_lane["tool"].sort(key=tool_sort_key)

    width: dict[str, float] = {}
    height: dict[str, float] = {}
    width_by_lane: dict[str, float] = {}
    occupied: set[str] = set()

    for n in nodes:
        nid = n["id"]
        w = execweave_node_width(n)
        h = execweave_node_height(n, w)
        lane = execweave_lane(n)
        width[nid] = w
        height[nid] = h
        width_by_lane[lane] = max(width_by_lane.get(lane, EXECWEAVE_NODE_W), w)
        occupied.add("endpoint" if lane == "other" else lane)

    width_by_lane["endpoint"] = max(
        width_by_lane.get("endpoint", EXECWEAVE_NODE_W),
        width_by_lane.get("other", EXECWEAVE_NODE_W),
    )
    lane_x = execweave_lane_x(width_by_lane, occupied)

    spec: dict[str, NodePlacement] = {}

    def put(node: dict[str, Any], lane: str, order: int, y: float):
        spec[node["id"]] = NodePlacement(
            node_id=node["id"],
            lane=lane,
            rank=EXECWEAVE_LANES.get(lane, 6),
            order=order,
            x=lane_x[lane],
            y=y,
        )

    for idx, n in enumerate(roots):
        put(n, "root", idx, root_y + idx * EXECWEAVE_ROW_GAP)
    for idx, n in enumerate(children):
        put(n, "agent", idx, 100.0 + idx * EXECWEAVE_ROW_GAP)
    for idx, n in enumerate(by_lane["runtime"]):
        put(n, "runtime", idx, root_y + (idx - len(by_lane["runtime"]) // 2) * 86.0)
    for idx, n in enumerate(by_lane["model"]):
        put(n, "model", idx, root_y + (idx - len(by_lane["model"]) // 2) * 92.0)

    tools = by_lane["tool"]
    collab = [
        t for t in tools
        if re.search(
            r"spawn|send|wait|agent",
            str(t.get("name") or execweave_attrs(t).get("tool_name") or ""),
            re.IGNORECASE,
        )
    ]
    ordinary = [t for t in tools if t not in collab]
    for idx, n in enumerate(collab):
        put(n, "tool", idx, -170.0 + idx * 82.0)
    for idx, n in enumerate(ordinary):
        put(n, "tool", len(collab) + idx, 80.0 + idx * 130.0)

    for lane in ["file", "endpoint", "other"]:
        for idx, n in enumerate(by_lane[lane]):
            put(n, lane, idx, 80.0 + idx * 104.0)

    for n in nodes:
        if n["id"] not in spec:
            put(n, execweave_lane(n), 0, 100.0)

    lane_count: dict[str, int] = {}
    for s in spec.values():
        lane_count[s.lane] = lane_count.get(s.lane, 0) + 1
    for s in spec.values():
        s.lane_count = lane_count.get(s.lane, 1)

    # Secondary Component 2D Packing
    component_of = execweave_components(nodes, edges)
    secondary_count = 0
    if component_of:
        sizes: dict[int, int] = {}
        for c in component_of.values():
            sizes[c] = sizes.get(c, 0) + 1

        spine_ids = {n["id"] for n in nodes if n.get("type") == "agent"}
        primary = component_of.get(roots[0]["id"]) if roots else None
        if primary is None:
            best_size = -1
            for val, sz in sorted(sizes.items(), key=lambda item: item[0]):
                if sz > best_size:
                    best_size = sz
                    primary = val

        spine_components = {component_of[nid] for nid in spine_ids if nid in component_of}
        if primary is not None:
            spine_components.add(primary)

        secondary = [c for c in sorted(sizes.keys()) if c not in spine_components]
        secondary_count = len(secondary)

        if secondary:
            spine_floor = -float("inf")
            spine_left = float("inf")
            spine_right = -float("inf")

            for nid, c in component_of.items():
                if c in spine_components:
                    s = spec.get(nid)
                    if s:
                        spine_floor = max(spine_floor, s.y + height.get(nid, EXECWEAVE_NODE_H))
                        spine_left = min(spine_left, s.x)
                        spine_right = max(spine_right, s.x + width.get(nid, EXECWEAVE_NODE_W))

            if not math.isfinite(spine_floor):
                spine_floor = 0.0
            if not math.isfinite(spine_left):
                spine_left = 0.0
                spine_right = 800.0

            spine_width = max(600.0, spine_right - spine_left)
            comp_boxes = []
            for val in secondary:
                members = [nid for nid, c in component_of.items() if c == val]
                min_x = float("inf")
                max_x = -float("inf")
                min_y = float("inf")
                max_y = -float("inf")
                for nid in members:
                    s = spec.get(nid)
                    if s:
                        min_x = min(min_x, s.x)
                        max_x = max(max_x, s.x + width.get(nid, EXECWEAVE_NODE_W))
                        min_y = min(min_y, s.y)
                        max_y = max(max_y, s.y + height.get(nid, EXECWEAVE_NODE_H))
                if math.isfinite(min_x):
                    comp_boxes.append({
                        "value": val,
                        "members": members,
                        "min_x": min_x,
                        "min_y": min_y,
                        "w": max_x - min_x,
                        "h": max_y - min_y,
                    })

            cursor_x = spine_left
            cursor_y = spine_floor + EXECWEAVE_BAND_GAP
            row_height = 0.0
            for box in comp_boxes:
                if cursor_x > spine_left and (cursor_x + box["w"]) > (spine_left + spine_width):
                    cursor_x = spine_left
                    cursor_y += row_height + EXECWEAVE_BAND_GAP
                    row_height = 0.0
                shift_x = cursor_x - box["min_x"]
                shift_y = cursor_y - box["min_y"]
                for nid in box["members"]:
                    s = spec.get(nid)
                    if s:
                        s.x += shift_x
                        s.y += shift_y
                cursor_x += box["w"] + EXECWEAVE_BAND_GAP
                row_height = max(row_height, box["h"])

    # Bundle calculations
    bundle_groups: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        s = node_by_id.get(edge.get("source", ""))
        t = node_by_id.get(edge.get("target", ""))
        if (
            s and t
            and s.get("type") == "agent"
            and execweave_lane(t) in ["tool", "model"]
            and not execweave_is_spawn(edge)
            and not execweave_is_stopped(edge)
        ):
            key = f"{edge.get('target', '')}\0{execweave_relation(edge)}"
            bundle_groups.setdefault(key, []).append(edge)

    bundle_by_edge: dict[str, dict[str, Any]] = {}
    sorted_groups = sorted(
        bundle_groups.items(),
        key=lambda item: (spec.get(item[1][0]["target"]).y if spec.get(item[1][0]["target"]) else 0, item[0]),
    )
    for group_idx, (key, members) in enumerate(sorted_groups):
        members.sort(
            key=lambda e: (
                child_order.get(e["source"], float("inf")),
                e.get("id", ""),
            )
        )
        for idx, edge in enumerate(members):
            bundle_by_edge[edge["id"]] = {
                "key": key,
                "size": len(members),
                "index": idx,
                "representative": idx == 0,
                "groupIndex": group_idx,
            }

    # Ports
    source_edges: dict[str, list[dict[str, Any]]] = {}
    target_edges: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        source_edges.setdefault(edge["source"], []).append(edge)
        target_edges.setdefault(edge["target"], []).append(edge)

    source_port: dict[str, tuple[int, int]] = {}
    target_port: dict[str, tuple[int, int]] = {}

    for s_id, elist in source_edges.items():
        elist.sort(
            key=lambda e: (
                spec.get(e["target"]).y if spec.get(e["target"]) else 0,
                spec.get(e["target"]).rank if spec.get(e["target"]) else 0,
                e.get("id", ""),
            )
        )
        for idx, edge in enumerate(elist):
            source_port[edge["id"]] = (idx, len(elist))

    for t_id, elist in target_edges.items():
        elist.sort(
            key=lambda e: (
                spec.get(e["source"]).y if spec.get(e["source"]) else 0,
                spec.get(e["source"]).rank if spec.get(e["source"]) else 0,
                e.get("id", ""),
            )
        )
        for idx, edge in enumerate(elist):
            target_port[edge["id"]] = (idx, len(elist))

    return {
        "spec": spec,
        "width": width,
        "height": height,
        "bundle_by_edge": bundle_by_edge,
        "source_port": source_port,
        "target_port": target_port,
        "secondary_component_count": secondary_count,
        "visible_node_count": len(nodes),
        "visible_edge_count": len(edges),
    }


# ==============================================================================
# Edge Routing & Geometry
# ==============================================================================
def port_y(pos_y: float, height: float, port_info: tuple[int, int] | None) -> float:
    if not port_info or port_info[1] <= 1:
        return pos_y + height / 2.0
    idx, total = port_info
    span = height - 20.0
    return pos_y + 10.0 + (span * idx) / (total - 1)


def cubic_bezier_sample(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 24,
) -> list[tuple[float, float]]:
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        t2 = t * t
        t3 = t2 * t
        x = mt3 * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t3 * p3[0]
        y = mt3 * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t3 * p3[1]
        pts.append((x, y))
    return pts


def sample_polyline(pts: list[tuple[float, float]], steps: int = 24) -> list[tuple[float, float]]:
    if len(pts) <= 1:
        return pts
    seg_lens = [
        math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        for i in range(len(pts) - 1)
    ]
    total_len = sum(seg_lens)
    if total_len == 0:
        return [pts[0]] * (steps + 1)

    result = [pts[0]]
    seg_idx = 0
    accum = 0.0

    for i in range(1, steps):
        target_d = total_len * (i / steps)
        while seg_idx < len(seg_lens) and accum + seg_lens[seg_idx] < target_d:
            accum += seg_lens[seg_idx]
            seg_idx += 1
        if seg_idx >= len(seg_lens):
            result.append(pts[-1])
        else:
            seg_d = target_d - accum
            ratio = seg_d / seg_lens[seg_idx] if seg_lens[seg_idx] > 0 else 0.0
            x = pts[seg_idx][0] + ratio * (pts[seg_idx + 1][0] - pts[seg_idx][0])
            y = pts[seg_idx][1] + ratio * (pts[seg_idx + 1][1] - pts[seg_idx][1])
            result.append((x, y))
    result.append(pts[-1])
    return result


def route_edge(
    edge: dict[str, Any],
    topo: dict[str, Any],
) -> list[tuple[float, float]]:
    spec = topo["spec"]
    width = topo["width"]
    height = topo["height"]
    bundle_by_edge = topo["bundle_by_edge"]
    source_port = topo["source_port"]
    target_port = topo["target_port"]

    eid = edge["id"]
    s_spec = spec.get(edge["source"])
    t_spec = spec.get(edge["target"])
    if not s_spec or not t_spec:
        return [(0.0, 0.0), (0.0, 0.0)]

    sp = (s_spec.x, s_spec.y)
    tp = (t_spec.x, t_spec.y)
    sw = width.get(edge["source"], EXECWEAVE_NODE_W)
    sh = height.get(edge["source"], EXECWEAVE_NODE_H)
    tw = width.get(edge["target"], EXECWEAVE_NODE_W)
    th = height.get(edge["target"], EXECWEAVE_NODE_H)

    bundle = bundle_by_edge.get(eid)
    if bundle and bundle["size"] > 1:
        sx = sp[0] + sw
        sy = port_y(sp[1], sh, source_port.get(eid))
        tx = tp[0]
        ty = port_y(tp[1], th, target_port.get(eid))
        trunk_x = max(sx + 54.0, tx - 82.0 - (bundle["groupIndex"] % 6) * 24.0)
        return sample_polyline([(sx, sy), (trunk_x, sy), (trunk_x, ty), (tx, ty)], steps=24)

    if execweave_is_stopped(edge):
        sx = sp[0]
        sy = sp[1] + sh * 0.78
        tx = tp[0] + tw
        ty = tp[1] + th * 0.78
        order = s_spec.order
        lane_count = s_spec.lane_count
        offset = 62.0 + (order % max(1, lane_count)) * 11.0
        p0 = (sx, sy)
        p1 = (sx - offset, sy + offset)
        p2 = (tx + offset, ty + offset)
        p3 = (tx, ty)
        return cubic_bezier_sample(p0, p1, p2, p3, steps=24)

    forward = t_spec.rank >= s_spec.rank
    sx = sp[0] + sw if forward else sp[0]
    tx = tp[0] if forward else tp[0] + tw
    sy = port_y(sp[1], sh, source_port.get(eid))
    ty = port_y(tp[1], th, target_port.get(eid))
    distance = abs(tx - sx)
    bend = max(44.0, distance * 0.42)
    sign = 1.0 if forward else -1.0

    p0 = (sx, sy)
    p1 = (sx + sign * bend, sy)
    p2 = (tx - sign * bend, ty)
    p3 = (tx, ty)
    return cubic_bezier_sample(p0, p1, p2, p3, steps=24)


def poly_length(pts: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(pts) - 1):
        total += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    return total


# ==============================================================================
# Edge Crossing Counting (Exact match to test_graph_edge_routing_e2e.py)
# ==============================================================================
def side(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> int:
    val = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 1 if val > 0 else (-1 if val < 0 else 0)


def hit(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    d1 = side(p3, p4, p1)
    d2 = side(p3, p4, p2)
    d3 = side(p1, p2, p3)
    d4 = side(p1, p2, p4)
    return d1 != d2 and d3 != d4


def count_crossings(polys: list[list[tuple[float, float]]]) -> int:
    count = 0
    num_edges = len(polys)
    for a in range(num_edges):
        poly_a = polys[a]
        len_a = len(poly_a)
        for b in range(a + 1, num_edges):
            poly_b = polys[b]
            len_b = len(poly_b)
            crossed = False
            for i in range(len_a - 1):
                p1 = poly_a[i]
                p2 = poly_a[i + 1]
                for j in range(len_b - 1):
                    if hit(p1, p2, poly_b[j], poly_b[j + 1]):
                        crossed = True
                        break
                if crossed:
                    break
            if crossed:
                count += 1
    return count


# ==============================================================================
# Metrics Evaluation
# ==============================================================================
def evaluate_graph_metrics(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return {
            "graph_width": 0.0,
            "graph_height": 0.0,
            "aspect_ratio": 1.0,
            "fit_scale": 1.0,
            "edge_crossings": 0,
            "max_edge_length": 0.0,
            "p95_edge_length": 0.0,
            "secondary_component_count": 0,
            "visible_node_count": 0,
            "visible_edge_count": 0,
        }

    topo = execweave_build_topology(nodes, edges)
    spec = topo["spec"]
    width = topo["width"]
    height = topo["height"]

    min_x = min(s.x for s in spec.values())
    max_x = max(s.x + width.get(s.node_id, EXECWEAVE_NODE_W) for s in spec.values())
    min_y = min(s.y for s in spec.values())
    max_y = max(s.y + height.get(s.node_id, EXECWEAVE_NODE_H) for s in spec.values())

    graph_w = max(1.0, max_x - min_x)
    graph_h = max(1.0, max_y - min_y)
    aspect_ratio = graph_w / graph_h

    # Fit scale: container width 1260, height 660, padding 72
    scale_w = (VIEWPORT_BOX_W - 72.0) / graph_w
    scale_h = (VIEWPORT_BOX_H - 72.0) / graph_h
    fit_scale = min(1.2, max(0.07, min(scale_w, scale_h)))

    polys = [route_edge(edge, topo) for edge in edges]
    crossings = count_crossings(polys)

    lengths = [poly_length(p) for p in polys]
    if lengths:
        lengths.sort()
        max_edge_length = lengths[-1]
        p95_idx = min(len(lengths) - 1, max(0, math.ceil(0.95 * len(lengths)) - 1))
        p95_edge_length = lengths[p95_idx]
    else:
        max_edge_length = 0.0
        p95_edge_length = 0.0

    return {
        "graph_width": round(graph_w, 2),
        "graph_height": round(graph_h, 2),
        "aspect_ratio": round(aspect_ratio, 4),
        "fit_scale": round(fit_scale, 4),
        "edge_crossings": crossings,
        "max_edge_length": round(max_edge_length, 2),
        "p95_edge_length": round(p95_edge_length, 2),
        "secondary_component_count": topo["secondary_component_count"],
        "visible_node_count": topo["visible_node_count"],
        "visible_edge_count": topo["visible_edge_count"],
    }


# ==============================================================================
# Canonical Benchmark Fixtures
# ==============================================================================
def make_single_agent_fixture() -> dict[str, Any]:
    names = ["zeta.py", "alpha.py", "omega.py", "beta.py", "mid.py"]
    nodes = [
        {"id": "process:p", "type": "process", "name": "codex", "attributes": {}},
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "model:m", "type": "model", "name": "gpt-5", "attributes": {}},
        {"id": "tool:read", "type": "tool", "name": "read", "attributes": {}},
        {"id": "tool:write", "type": "tool", "name": "write", "attributes": {}},
    ]
    edges = [
        {"id": "p0", "source": "process:p", "target": "agent:/root",
         "relation": "STARTED_AGENT", "attributes": {}},
        {"id": "u0", "source": "agent:/root", "target": "model:m",
         "relation": "USED_MODEL", "attributes": {}},
        {"id": "u1", "source": "agent:/root", "target": "tool:read",
         "relation": "USES_TOOL", "attributes": {}},
        {"id": "u2", "source": "agent:/root", "target": "tool:write",
         "relation": "USES_TOOL", "attributes": {}},
    ]
    for index, name in enumerate(names):
        nodes.append({"id": f"file:f{index}", "type": "file", "name": name, "attributes": {}})
        edges.append({
            "id": f"w{index}",
            "source": "agent:/root",
            "target": f"file:f{index}",
            "relation": "WROTE_FILE",
            "first_sequence": index + 10,
            "attributes": {},
        })
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges}


def make_secondary_heavy_fixture() -> dict[str, Any]:
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "agent:/root/a", "type": "agent", "name": "worker",
         "attributes": {"agent_role": "child", "agent_path": "/root/a"}},
        {"id": "model:m", "type": "model", "name": "gpt-4", "attributes": {}},
        {"id": "tool:t", "type": "tool", "name": "fetch", "attributes": {}},
        {"id": "file:main", "type": "file", "name": "main.py", "attributes": {}},
    ]
    edges = [
        {"id": "s1", "source": "agent:/root", "target": "agent:/root/a",
         "relation": "SPAWNED_AGENT", "attributes": {}},
        {"id": "s2", "source": "agent:/root/a", "target": "model:m",
         "relation": "USED_MODEL", "attributes": {}},
        {"id": "s3", "source": "agent:/root/a", "target": "tool:t",
         "relation": "USES_TOOL", "attributes": {}},
        {"id": "s4", "source": "agent:/root/a", "target": "file:main",
         "relation": "WROTE_FILE", "attributes": {}},
    ]
    for index in range(8):
        nodes.append({
            "id": f"orphan:file:{index}",
            "type": "file",
            "name": f"stray_{index}.tmp",
            "attributes": {},
        })
    nodes.append({"id": "orphan:tool:ping", "type": "tool", "name": "ping", "attributes": {}})
    nodes.append({"id": "orphan:endpoint:dns", "type": "network_endpoint", "name": "8.8.8.8", "attributes": {}})
    edges.append({"id": "orphan:e1", "source": "orphan:tool:ping", "target": "orphan:endpoint:dns", "relation": "REACHED", "attributes": {}})

    nodes.append({"id": "orphan:file:audit", "type": "file", "name": "audit.log", "attributes": {}})
    nodes.append({"id": "orphan:file:backup", "type": "file", "name": "backup.log", "attributes": {}})
    edges.append({"id": "orphan:e2", "source": "orphan:file:audit", "target": "orphan:file:backup", "relation": "COPIED_TO", "attributes": {}})

    return {"schema_version": "1.0", "nodes": nodes, "edges": edges}


def make_multi_agent_fixture() -> dict[str, Any]:
    names = ["zeta.py", "alpha.py", "omega.py", "beta.py", "mid.py"]
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "model:m", "type": "model", "name": "gpt-5", "attributes": {}},
        {"id": "tool:read", "type": "tool", "name": "read", "attributes": {}},
        {"id": "tool:write", "type": "tool", "name": "write", "attributes": {}},
        {"id": "process:p", "type": "process", "name": "codex", "attributes": {}},
    ]
    edges = [{"id": "p0", "source": "process:p", "target": "agent:/root",
              "relation": "STARTED_AGENT", "attributes": {}}]
    for index in range(5):
        agent = f"agent:/root/a{index}"
        nodes.append({"id": agent, "type": "agent", "name": f"a{index}",
                      "attributes": {"agent_role": "child", "agent_path": f"/root/a{index}"}})
        edges.append({"id": f"s{index}", "source": "agent:/root", "target": agent,
                      "relation": "SPAWNED_AGENT", "attributes": {}})
        for target in ("model:m", "tool:read", "tool:write"):
            edges.append({"id": f"u{index}:{target}", "source": agent, "target": target,
                          "relation": "USED_MODEL" if target == "model:m" else "USES_TOOL",
                          "attributes": {}})
        nodes.append({"id": f"file:f{index}", "type": "file", "name": names[index], "attributes": {}})
        edges.append({"id": f"w{index}", "source": agent, "target": f"file:f{index}",
                      "relation": "WROTE_FILE", "attributes": {}})
        edges.append({"id": f"x{index}", "source": agent, "target": "agent:/root",
                      "relation": "SUBAGENT_STOPPED", "attributes": {}})
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges}


FIXTURE_FACTORIES = {
    "single-agent": make_single_agent_fixture,
    "secondary-heavy": make_secondary_heavy_fixture,
    "multi-agent": make_multi_agent_fixture,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract geometry layout metrics from ExecWeave graphs")
    parser.add_argument("--fixture", choices=list(FIXTURE_FACTORIES.keys()), help="Name of canonical fixture to evaluate")
    parser.add_argument("--input", type=Path, help="Path to custom graph JSON file")
    parser.add_argument("--output", type=Path, help="Save evaluation JSON to output file")
    args = parser.parse_args()

    results: dict[str, Any] = {}

    if args.input:
        graph = json.loads(args.input.read_text(encoding="utf-8"))
        results["custom"] = evaluate_graph_metrics(graph)
    elif args.fixture:
        graph = FIXTURE_FACTORIES[args.fixture]()
        results[args.fixture] = evaluate_graph_metrics(graph)
    else:
        for name, factory in FIXTURE_FACTORIES.items():
            graph = factory()
            results[name] = evaluate_graph_metrics(graph)

    formatted = json.dumps(results, indent=2)
    print(formatted)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted + "\n", encoding="utf-8")
        print(f"Metrics written to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Every provider's dashboard must draw a graph a user can follow.

For each provider-shaped recording in ``dashboard_provider_runs`` -- CLI agents
through their hook CLIs, a user's own Python script through the proxy recorder or
an SDK / runtime / gateway adapter (commercial APIs and a local Ollama alike), and
framework agents inside ``execweave record`` -- both the final viewer.html and the
live dashboard mid-run must satisfy the same contract:

- every drawn node is reachable from the one root; nothing floats on its own;
- a provider session hangs off root -> model -> session, or straight off the root
  when no model was observed; a model switched inside a session is another model
  node from the root into that same session, and a new provider session gets its
  own model node(s);
- no self-loops and no duplicate edges; an edge is drawn right to left (or within
  one column) exactly when the projection marked it as feedback, so every other
  edge flows left to right;
- neither an edge's path nor its label runs through a node or another label.

Direction is judged from where the page actually draws each node, not from any
internal layout attribute.

All violations of one page are collected and reported together.
"""

from __future__ import annotations

import json
import threading
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import pytest

from dashboard_provider_runs import CASES, ROOT, ProviderRun, build, live_inputs
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e

SURFACES = ("final", "live")

# What the page draws, read straight from the DOM and the dashboard core.
_COLLECT = r"""() => {
  const core = window.__execweaveCore;
  const display = core.getDisplayGraph();
  const attrs = item => (item && typeof item.attributes === 'object' && item.attributes) || {};
  const visible = el => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) > 0; };
  const nodes = [...document.querySelectorAll('.node[data-id]')].map(g => {
    const m = (g.getAttribute('transform') || '').match(/translate\(([-0-9.e]+)[ ,]+([-0-9.e]+)\)/);
    const rect = g.querySelector('rect');
    const box = rect ? rect.getBoundingClientRect() : g.getBoundingClientRect();
    return { id: g.dataset.id, x: m ? Number(m[1]) : null, y: m ? Number(m[2]) : null,
             box: { left: box.left, right: box.right, top: box.top, bottom: box.bottom } };
  });
  const boxes = nodes.map(n => n.box);
  const paths = [];
  for (const path of document.querySelectorAll('#svg path.edge')) {
    if (!visible(path)) continue;
    let length = 0;
    try { length = path.getTotalLength(); } catch (_) { length = 0; }
    const ctm = path.getScreenCTM();
    const hits = new Set();
    if (ctm && length > 0) {
      for (let k = 1; k < 40; k++) {
        const q = path.getPointAtLength(length * k / 40);
        const x = ctm.a * q.x + ctm.c * q.y + ctm.e, y = ctm.b * q.x + ctm.d * q.y + ctm.f;
        nodes.forEach((n, i) => { const b = boxes[i]; if (x > b.left + 2 && x < b.right - 2 && y > b.top + 2 && y < b.bottom - 2) hits.add(n.id); });
      }
    }
    paths.push({ id: path.dataset.edgeId, source: path.dataset.source, target: path.dataset.target,
                 relation: path.dataset.relation, length, hits: [...hits] });
  }
  const labels = [...document.querySelectorAll('#svg text.label')].filter(visible).map(l => {
    const b = l.getBoundingClientRect();
    return { id: l.dataset.edgeId, text: l.textContent, box: { left: b.left, right: b.right, top: b.top, bottom: b.bottom } };
  }).filter(l => l.box.right - l.box.left > 0);
  return {
    nodes,
    paths,
    labels,
    display: {
      nodes: (display.nodes || []).map(n => ({ id: n.id, type: n.type, name: n.name,
        model_context: !!attrs(n).viewer_model_context })),
      edges: (display.edges || []).map(e => ({ id: e.id, source: e.source, target: e.target,
        relation: e.relation, feedback: !!e.viewer_flow_feedback })),
    },
  };
}"""


def _overlap(a: dict[str, float], b: dict[str, float], pad: float = 0.5) -> bool:
    return (
        min(a["right"], b["right"]) - max(a["left"], b["left"]) > pad
        and min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]) > pad
    )


def _violations(run: ProviderRun, page: dict[str, Any]) -> list[str]:
    case = run.case
    problems: list[str] = []
    display = page["display"]
    nodes = {node["id"]: node for node in display["nodes"]}
    edges = display["edges"]
    position = {node["id"]: node for node in page["nodes"]}

    # What is drawn is what the dashboard says it shows.
    drawn = set(position)
    if drawn != set(nodes):
        problems.append(
            f"drawn nodes differ from the display graph: only drawn {sorted(drawn - set(nodes))}, "
            f"never drawn {sorted(set(nodes) - drawn)}"
        )
        return problems
    # A node's rank is the column it is drawn in.
    rank = {node_id: position[node_id]["x"] for node_id in nodes}
    unplaced = sorted(node_id for node_id, value in rank.items() if not isinstance(value, (int, float)))
    if unplaced:
        problems.append(f"nodes without a drawn position: {unplaced}")
        return problems

    # Edges: real endpoints, no self-loops, no duplicates, backwards only as feedback.
    seen: Counter[tuple[str, str, str]] = Counter()
    touched: set[str] = set()
    forward_in: dict[str, list[dict[str, Any]]] = defaultdict(list)
    forward_out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source, target, relation = edge["source"], edge["target"], edge["relation"]
        if source not in nodes or target not in nodes:
            problems.append(f"edge {edge['id']} points at a node that is not drawn")
            continue
        touched.update((source, target))
        seen[(source, relation, target)] += 1
        if source == target:
            problems.append(f"self-loop {relation} on {source}")
        backwards = rank[source] >= rank[target]
        if backwards != edge["feedback"]:
            problems.append(
                f"{relation} {source} (x {rank[source]}) -> {target} (x {rank[target]}) "
                f"is drawn {'backwards' if backwards else 'forwards'} but feedback={edge['feedback']}"
            )
        if not backwards:
            forward_in[target].append(edge)
            forward_out[source].append(edge)
    problems += [f"duplicate edge {key} x{count}" for key, count in seen.items() if count > 1]
    isolated = sorted(set(nodes) - touched)
    if isolated:
        problems.append(f"isolated nodes: {isolated}")

    # One root; everything else enters through a forward edge and is reachable from it.
    roots = sorted(node_id for node_id in nodes if not forward_in[node_id])
    if len(roots) != 1:
        problems.append(f"expected one root; nodes with no forward way in: {roots}")
    if roots:
        reached = {roots[0]}
        queue = deque(reached)
        while queue:
            for edge in forward_out[queue.popleft()]:
                if edge["target"] not in reached:
                    reached.add(edge["target"])
                    queue.append(edge["target"])
        unreachable = sorted(set(nodes) - reached)
        if unreachable:
            problems.append(f"not reachable from the root {roots[0]}: {unreachable}")
    root = roots[0] if len(roots) == 1 else None

    # The session spine: root -> model -> session, or root -> session when no model fed it.
    contexts = {node_id for node_id, node in nodes.items() if node["model_context"]}
    for context in sorted(contexts):
        entries = [edge for edge in forward_in[context] if edge["relation"] == "MODEL_CONTEXT"]
        if len(forward_in[context]) != 1 or len(entries) != 1 or entries[0]["source"] != root:
            problems.append(
                f"model node {nodes[context]['name']} must enter only from the root via MODEL_CONTEXT, got "
                f"{[(edge['relation'], edge['source']) for edge in forward_in[context]]}"
            )
        if not forward_out[context]:
            problems.append(f"model node {nodes[context]['name']} leads nowhere")
    feeds: list[frozenset[str]] = []
    for session in sorted(node_id for node_id, node in nodes.items() if node["type"] == "session"):
        incoming = forward_in[session]
        used = [edge for edge in incoming if edge["relation"] == "USED_IN_SESSION"]
        if used and len(used) == len(incoming) and all(edge["source"] in contexts for edge in used):
            feeds.append(frozenset(nodes[edge["source"]]["name"] for edge in used))
        elif (
            len(incoming) == 1
            and incoming[0]["relation"] == "RECORDED_IN_SESSION"
            and incoming[0]["source"] == root
        ):
            feeds.append(frozenset({ROOT}))
        else:
            problems.append(
                f"session {session} must enter from model nodes (USED_IN_SESSION) or from the root alone, got "
                f"{[(edge['relation'], edge['source']) for edge in incoming]}"
            )
    if Counter(feeds) != Counter(case.feeds):
        problems.append(f"sessions are fed by {sorted(map(sorted, feeds))}, expected {sorted(map(sorted, case.feeds))}")
    fed = {name for group in feeds for name in group}
    stray = sorted(nodes[context]["name"] for context in contexts if nodes[context]["name"] not in fed)
    if stray:
        problems.append(f"model nodes that feed no session: {stray}")

    # The things the user came to see are on the canvas.
    names = {(node["type"], node["name"]) for node in nodes.values()}
    missing = sorted(set(run.extra["required"]) - names)
    if missing:
        problems.append(f"missing nodes {missing}")

    # Every edge is drawn between its own endpoints and crosses no node; labels stay clear.
    paths = {path["id"]: path for path in page["paths"]}
    for edge in edges:
        path = paths.get(edge["id"])
        if path is None or not path["length"] > 0:
            problems.append(f"edge {edge['id']} has no visible path")
            continue
        # The DOM carries the relation lower-cased as a CSS-friendly token.
        drawn_as = (path["source"], path["target"], str(path["relation"]).upper())
        if drawn_as != (edge["source"], edge["target"], edge["relation"].upper()):
            problems.append(f"path {edge['id']} is drawn between the wrong nodes")
        if path["hits"]:
            problems.append(f"path {edge['id']} runs through {path['hits']}")
    labels = page["labels"]
    for index, label in enumerate(labels):
        for other in labels[index + 1 :]:
            if _overlap(label["box"], other["box"]):
                problems.append(f"labels overlap: {label['text']!r} / {other['text']!r}")
        for node in page["nodes"]:
            if _overlap(label["box"], node["box"]):
                problems.append(f"label {label['text']!r} covers node {node['id']}")
    return problems


def _settle(page: Any) -> None:
    page.wait_for_selector(".node", timeout=15000)
    page.evaluate("document.fonts.ready.then(() => true)")
    # The live page applies its snapshot asynchronously; wait until two reads agree.
    page.wait_for_function(
        """() => new Promise(resolve => {
          const read = () => [...document.querySelectorAll('.node[data-id]')]
            .map(n => n.dataset.id + n.getAttribute('transform')).join('|');
          const first = read();
          setTimeout(() => resolve(first === read() && first.length > 0), 300);
        })""",
        timeout=15000,
    )


def _inspect(browser: Any, run: ProviderRun, surface: str, directory: Path) -> tuple[dict[str, Any], list[str]]:
    from execweave import live as live_module
    from execweave import live_core

    errors: list[str] = []
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)
    server = thread = None
    try:
        if surface == "final":
            viewer = directory / "viewer.html"
            viewer.write_text(live_core.render_graph_html(run.graph), encoding="utf-8")
            page.goto(viewer.as_uri())
        else:
            session_id, event_path, semantic_path = live_inputs(run, directory / "live")
            state = live_module._LiveState(session_id, event_path, semantic_path)
            state.live_update(-1)
            token = "dashboard-invariants"
            server = live_module._LocalThreadingHTTPServer(
                ("127.0.0.1", 0), live_module._handler_factory(state, token)
            )
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            page.set_extra_http_headers({"X-ExecWeave-Token": token})
            page.goto(f"http://{host}:{port}/")
        _settle(page)
        return page.evaluate(_COLLECT), errors
    finally:
        page.close()
        if server is not None:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


@pytest.fixture(scope="module")
def chromium() -> Any:
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture(scope="module")
def recorded(tmp_path_factory: pytest.TempPathFactory) -> Any:
    runs: dict[str, ProviderRun] = {}

    def get(case_name: str) -> ProviderRun:
        if case_name not in runs:
            case = next(case for case in CASES if case.name == case_name)
            runs[case_name] = build(case, tmp_path_factory.mktemp(case_name))
        return runs[case_name]

    return get


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("case_name", [case.name for case in CASES])
def test_every_provider_dashboard_draws_a_connected_readable_flow(
    chromium: Any, recorded: Any, case_name: str, surface: str, tmp_path: Path
) -> None:
    run = recorded(case_name)
    page, errors = _inspect(chromium, run, surface, tmp_path)
    problems = errors + _violations(run, page)
    assert not problems, f"{case_name} ({surface}):\n  " + "\n  ".join(problems) + (
        "\n\ndrawn graph:\n" + json.dumps(page["display"], indent=1, sort_keys=True)
    )

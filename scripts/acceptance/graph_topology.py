"""Whether a dashboard page draws a graph a user can follow.

The same contract applies to the fixture recordings in the test suite and to real
provider runs in the acceptance journeys, on the final viewer.html and on the live
dashboard alike:

- every drawn node is reachable from the one root; nothing floats on its own;
- a provider session hangs off root -> model -> session, or straight off the root
  when no model was observed; a model switched inside a session is another model
  node from the root into that same session, and a new provider session gets its
  own session node;
- no self-loops and no duplicate edges; an edge is drawn right to left (or within
  one column) exactly when the projection marked it as feedback, so every other
  edge flows left to right;
- neither an edge's path nor its label runs through a node or another label.

Direction is judged from where the page actually draws each node, not from any
internal layout attribute. ``violations`` reports every problem of one snapshot
together with which models feed each session, so a caller can compare that with
what it knows the run did.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

# A session entered straight from the root (no model observed) is fed by ROOT.
ROOT = "<root>"

# What the page draws, read straight from the DOM and the dashboard core.
COLLECT_JS = r"""() => {
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

_STABLE_JS = """() => new Promise(resolve => {
  const read = () => [...document.querySelectorAll('.node[data-id]')]
    .map(n => n.dataset.id + n.getAttribute('transform')).join('|');
  const first = read();
  setTimeout(() => resolve(first === read() && first.length > 0), 300);
})"""


def settle(page: Any, timeout: float = 15000) -> None:
    """Wait until the page has drawn its graph and stopped moving it."""
    page.wait_for_selector(".node", timeout=timeout)
    page.evaluate("document.fonts.ready.then(() => true)")
    # The live page applies its snapshot asynchronously; wait until two reads agree.
    page.wait_for_function(_STABLE_JS, timeout=timeout)


def collect(page: Any) -> dict[str, Any]:
    """Read what the page draws: node positions, edge paths, labels, the display graph."""
    return page.evaluate(COLLECT_JS)


def _overlap(a: dict[str, float], b: dict[str, float], pad: float = 0.5) -> bool:
    return (
        min(a["right"], b["right"]) - max(a["left"], b["left"]) > pad
        and min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]) > pad
    )


def violations(snapshot: dict[str, Any]) -> tuple[list[str], list[frozenset[str]]]:
    """Every way the drawn graph breaks the contract, and the models feeding each session.

    Each entry of the second list is the set of model names whose nodes feed one
    session node, or ``{ROOT}`` for a session entered straight from the root.
    """
    problems: list[str] = []
    feeds: list[frozenset[str]] = []
    display = snapshot["display"]
    nodes = {node["id"]: node for node in display["nodes"]}
    edges = display["edges"]
    position = {node["id"]: node for node in snapshot["nodes"]}

    if not nodes:
        problems.append("the page draws no graph")
        return problems, feeds
    # What is drawn is what the dashboard says it shows.
    drawn = set(position)
    if drawn != set(nodes):
        problems.append(
            f"drawn nodes differ from the display graph: only drawn {sorted(drawn - set(nodes))}, "
            f"never drawn {sorted(set(nodes) - drawn)}"
        )
        return problems, feeds
    # A node's rank is the column it is drawn in.
    rank = {node_id: position[node_id]["x"] for node_id in nodes}
    unplaced = sorted(node_id for node_id, value in rank.items() if not isinstance(value, (int, float)))
    if unplaced:
        problems.append(f"nodes without a drawn position: {unplaced}")
        return problems, feeds

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
    for session in sorted(node_id for node_id, node in nodes.items() if node["type"] == "session"):
        incoming = forward_in[session]
        used = [edge for edge in incoming if edge["relation"] == "USED_IN_SESSION"]
        if used and len(used) == len(incoming) and all(edge["source"] in contexts for edge in used):
            names = [nodes[edge["source"]]["name"] for edge in used]
            # Two nodes of one model (``llama3.2`` and ``llama3.2:latest`` included) feeding
            # one session would show the user a model that is not there.
            twice = sorted(name for name, count in Counter(map(model_name, names)).items() if count > 1)
            if twice:
                problems.append(f"session {session} is fed by more than one node of model {twice}")
            feeds.append(frozenset(names))
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
    fed = {name for group in feeds for name in group}
    stray = sorted(nodes[context]["name"] for context in contexts if nodes[context]["name"] not in fed)
    if stray:
        problems.append(f"model nodes that feed no session: {stray}")

    # Every edge is drawn between its own endpoints and crosses no node; labels stay clear.
    paths = {path["id"]: path for path in snapshot["paths"]}
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
    labels = snapshot["labels"]
    for index, label in enumerate(labels):
        for other in labels[index + 1 :]:
            if _overlap(label["box"], other["box"]):
                problems.append(f"labels overlap: {label['text']!r} / {other['text']!r}")
        for node in snapshot["nodes"]:
            if _overlap(label["box"], node["box"]):
                problems.append(f"label {label['text']!r} covers node {node['id']}")
    return problems, feeds


def describe_feeds(feeds: Iterable[frozenset[str]]) -> list[list[str]]:
    return sorted(sorted(group) for group in feeds)


def model_name(name: str) -> str:
    """One spelling per model: Ollama resolves a bare name to its ``:latest`` tag."""
    return name[: -len(":latest")] if name.endswith(":latest") else name


def _comparable(feeds: Iterable[frozenset[str]]) -> Counter[tuple[str, ...]]:
    # Each name is kept, so two nodes that are one model under different spellings
    # still count as two and do not match a session fed once by that model.
    return Counter(tuple(sorted(model_name(name) for name in group)) for group in feeds)


def feeds_match(feeds: Iterable[frozenset[str]], expected: Iterable[frozenset[str]]) -> bool:
    """Whether the sessions are fed by exactly the expected models, one entry per session."""
    return _comparable(feeds) == _comparable(expected)


def inspect(
    page: Any,
    artifacts: Path,
    surface: str,
    *,
    expect_feeds: Iterable[frozenset[str]] | None = None,
    timeout: float = 15000,
) -> tuple[list[str], list[frozenset[str]]]:
    """Judge what ``page`` draws now and keep the snapshot as evidence.

    ``expect_feeds`` is what the caller knows the run did: one entry per provider
    session, the model names that served it (``{ROOT}`` when none was observed).
    The snapshot, the problems and the feeds are written to
    ``graph-topology-<surface>.json`` under ``artifacts``.
    """
    settle(page, timeout)
    snapshot = collect(page)
    problems, feeds = violations(snapshot)
    if expect_feeds is not None:
        expected = list(expect_feeds)
        if not feeds_match(feeds, expected):
            problems.append(
                f"sessions are fed by {describe_feeds(feeds)}, expected {describe_feeds(expected)}"
            )
    record = {
        "surface": surface,
        "problems": problems,
        "feeds": describe_feeds(feeds),
        "expected_feeds": None if expect_feeds is None else describe_feeds(expected),
        "snapshot": snapshot,
    }
    (Path(artifacts) / f"graph-topology-{surface}.json").write_text(
        json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    return [f"{surface}: {problem}" for problem in problems], feeds


def summary(problems: list[str], limit: int = 12) -> list[str]:
    """The first problems for a report, with a count of the rest."""
    shown = problems[:limit]
    if len(problems) > limit:
        shown.append(f"... and {len(problems) - limit} more")
    return shown

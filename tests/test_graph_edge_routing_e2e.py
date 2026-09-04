"""Ordinary edges share one routing family, and crossings do not regress.

Four routing families were chosen per edge rather than by one rule: a right-angle
trunk for bundles, two different bend formulas, and an offset loop for lifecycle
returns. Spawning a subagent is ordinary execution flow, so it had no business being
its own geometry.

The crossing count is recorded here rather than described. "Fewer crossings" with no
number cannot fail a build.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_graph_node_sizing_e2e import _browser, _launch, _render

# Measured on the fixture below at the commit that unified the routing families. The
# count is dominated by the bundle trunk and the lifecycle returns, both of which are
# deliberate, so this is a regression floor rather than a target: it may fall, and a
# rise has to be explained.
CROSSING_BASELINE = 73

_COUNT_CROSSINGS = """() => {
  const paths = [...document.querySelectorAll('.edge')];
  const poly = p => {
    const len = p.getTotalLength(), steps = 24, pts = [];
    for (let i = 0; i <= steps; i++) { const q = p.getPointAtLength(len * i / steps); pts.push([q.x, q.y]); }
    return pts;
  };
  const polys = paths.map(poly);
  const side = (a, b, c) => Math.sign((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]));
  const hit = (p1,p2,p3,p4) => {
    const d1=side(p3,p4,p1), d2=side(p3,p4,p2), d3=side(p1,p2,p3), d4=side(p1,p2,p4);
    return d1!==d2 && d3!==d4;
  };
  let count = 0;
  for (let a = 0; a < polys.length; a++)
    for (let b = a + 1; b < polys.length; b++) {
      let crossed = false;
      for (let i = 0; i < polys[a].length - 1 && !crossed; i++)
        for (let j = 0; j < polys[b].length - 1 && !crossed; j++)
          if (hit(polys[a][i], polys[a][i+1], polys[b][j], polys[b][j+1])) crossed = true;
      if (crossed) count++;
    }
  return JSON.stringify({edges: polys.length, crossings: count});
}"""


def _dense_graph(*, shuffle_names: bool = True) -> dict[str, Any]:
    """Five subagents that reach every routing family.

    File names deliberately do not follow the order of the agents that write them, so
    ordering an evidence lane by name rather than by its sources is visible as
    crossings rather than hidden by a lucky alphabet.
    """
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
        name = names[index] if shuffle_names else f"module_{index}.py"
        nodes.append({"id": f"file:f{index}", "type": "file", "name": name, "attributes": {}})
        edges.append({"id": f"w{index}", "source": agent, "target": f"file:f{index}",
                      "relation": "WROTE_FILE", "attributes": {}})
        edges.append({"id": f"x{index}", "source": agent, "target": "agent:/root",
                      "relation": "SUBAGENT_STOPPED", "attributes": {}})
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges}


def _on_page(tmp_path: Path, read):
    viewer = _render(tmp_path, _dense_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1100})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            page.wait_for_timeout(400)
            return read(page)
        finally:
            browser.close()


def test_the_crossing_count_does_not_rise_above_the_recorded_baseline(tmp_path: Path) -> None:
    measured = json.loads(_on_page(tmp_path, lambda page: page.evaluate(_COUNT_CROSSINGS)))
    assert measured["edges"] == 31, f"the fixture changed shape: {measured}"
    assert measured["crossings"] <= CROSSING_BASELINE, (
        f"routing got worse: {measured['crossings']} crossings against a recorded "
        f"baseline of {CROSSING_BASELINE}"
    )


def test_every_ordinary_edge_shares_one_geometry(tmp_path: Path) -> None:
    """Ordinary flow uses one family; bundles and lifecycle returns stay deliberate exceptions.

    After dagre routing points are wired, ordinary edges are polylines (M/L) snapped to
    ports. Spawns and tool calls must still share that family so they leave the same
    node on the same geometry.
    """

    def read(page: Any) -> dict[str, Any]:
        return json.loads(
            page.evaluate(
                """() => {
                    const shape = d => d.trim().split(/[-0-9.\\s]+/).filter(Boolean).join('');
                    const out = {};
                    for (const el of document.querySelectorAll('.edge')) {
                        const kind = el.dataset.routeKind;
                        (out[kind] = out[kind] || []).push(shape(el.getAttribute('d')));
                    }
                    return JSON.stringify(out);
                }"""
            )
        )

    shapes = _on_page(tmp_path, read)
    assert set(shapes) >= {"spawn", "forward", "bundle", "lifecycle-return"}, shapes
    ordinary = [command for kind in ("spawn", "forward") for command in shapes[kind]]
    assert ordinary, "ordinary edges produced no paths"
    assert all(command.startswith("M") and set(command) <= {"M", "L"} for command in ordinary), (
        f"ordinary edges are not dagre polylines: {set(ordinary)}"
    )
    # The two deliberate exceptions keep their own shapes.
    assert set(shapes["bundle"]) == {"MHVH"}, shapes["bundle"]
    assert set(shapes["lifecycle-return"]) == {"MC,,"}, shapes["lifecycle-return"]


def test_routing_is_deterministic_for_the_same_payload(tmp_path: Path) -> None:
    viewer = _render(tmp_path, _dense_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1100})
            read = "() => [...document.querySelectorAll('.edge')].map(e => e.getAttribute('d')).join('|')"
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            first = page.evaluate(read)
            page.reload()
            page.wait_for_selector(".node", timeout=15000)
            second = page.evaluate(read)
        finally:
            browser.close()
    assert first == second, "the same payload produced different path data"

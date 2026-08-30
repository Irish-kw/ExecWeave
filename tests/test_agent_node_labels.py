"""A graph node must name the agent it stands for.

Topology attributes are namespaced apart — a subagent carries
``child_agent_path`` and a root carries ``root_agent_path`` — but the dashboard
projection read ``agent_path`` alone. Finding nothing, it fell through to
labelling by an id fragment.

The ids are time-ordered, so the fragment is a timestamp: three siblings spawned
in the same millisecond window produced ``subagent · 01a051ee``,
``subagent · 01a051ee`` and ``subagent · 01a051ef``. Two nodes rendered
identically and no reader could tell which agent was which, even though the same
nodes already carried ``/root/dinner_taiwanese`` and a nickname.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
FOCUS = SRC / "viewer_dashboard_focus.py"
PANEL = SRC / "viewer_conversation_panel.py"

# Real ids from a four-agent Codex run: the first eight characters of the first
# two are identical, which is what collapsed them into one visible label.
_SESSION = "01a051ee-b0f1-7aa0-81c5-df4f94f5a64c"
_CHILDREN = (
    ("01a051ee-e985-7813-aad4-afad15a1e8c2", "/root/dinner_taiwanese", "Avicenna"),
    ("01a051ee-f723-7c42-b80f-9faa894d23c2", "/root/dinner_healthy", "Banach"),
    ("01a051ef-062b-7d40-bf4d-97ced2a8f070", "/root/dinner_fun", "Volta"),
)


def _nodes(*, with_paths: bool) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "agent:OpenAI Codex",
            "type": "agent",
            "name": "OpenAI Codex",
            "attributes": {"provider": "codex", "agent_role": "root", "root_agent_path": "/root"},
        }
    ]
    for subagent_id, path, nickname in _CHILDREN:
        attributes: dict[str, Any] = {
            "provider": "codex",
            "agent_role": "subagent",
            "subagent_id": subagent_id,
            "agent_nickname": nickname,
            "parent_agent_path": "/root",
        }
        if with_paths:
            attributes["child_agent_path"] = path
        nodes.append(
            {
                "id": f"agent:codex:{_SESSION}:subagent:{subagent_id}",
                "type": "agent",
                "name": "default",
                "attributes": attributes,
            }
        )
    return nodes


# ── the namespaced attributes must be read wherever a node is named ──────────


def test_dashboard_projection_reads_the_namespaced_topology_paths() -> None:
    source = FOCUS.read_text(encoding="utf-8")
    assert "attrs.agent_path||attrs.child_agent_path||attrs.root_agent_path" in source
    assert "typeof attrs.agent_path==='string'?attrs.agent_path.trim():''" not in source, (
        "reading agent_path alone leaves every subagent unnamed"
    )


def test_conversation_panel_fallback_reads_them_too() -> None:
    source = PANEL.read_text(encoding="utf-8")
    assert source.count("attributes?.child_agent_path") == 2, (
        "both the static and live fallback link titles must resolve a subagent path"
    )


def test_a_timestamp_ordered_id_prefix_is_never_the_label() -> None:
    source = FOCUS.read_text(encoding="utf-8")
    assert "agentId.slice(0,8)" not in source, (
        "eight characters of a time-ordered id are shared by siblings spawned together"
    )
    assert "subagent · ${nickname}" in source, "prefer the name the provider gave the agent"


# ── execute the shipped projection ───────────────────────────────────────────


def _labels(nodes: list[dict[str, Any]], tmp_path: Path) -> list[str]:
    """Run the real projection over these nodes and return what it would draw."""
    from execweave.viewer_projection import write_graph_html

    html_path = tmp_path / "viewer.html"
    write_graph_html({"nodes": nodes, "edges": []}, html_path)
    html = html_path.read_text(encoding="utf-8")

    start = html.index("const execweaveDashboardGraphBase=execweaveDashboardGraph;")
    end = html.index("const normalized=value=>", start)
    body = html[start:end]
    # Keep only the node-preparation stage; the merge stage below it needs the
    # rest of the dashboard runtime.
    body = body.replace("const execweaveDashboardGraphBase=execweaveDashboardGraph;", "")
    body = body.replace("execweaveDashboardGraph=function(data){", "function project(data){")
    body = body.replace("const projected=execweaveDashboardGraphBase(data);", "const projected=data;")

    script = tmp_path / "labels.js"
    script.write_text(
        body
        + """
  return prepared.map(node=>node.name);
}
console.log(JSON.stringify(project({nodes:JSON.parse(process.argv[2]),edges:[]})));
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("node"), str(script), json.dumps(nodes)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_each_agent_node_is_labelled_by_its_own_path(tmp_path: Path) -> None:
    labels = _labels(_nodes(with_paths=True), tmp_path)
    assert labels == [
        "/root",
        "/root/dinner_taiwanese",
        "/root/dinner_healthy",
        "/root/dinner_fun",
    ], labels
    assert len(set(labels)) == len(labels), "two agents rendered as the same node"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_siblings_stay_distinct_even_without_a_declared_path(tmp_path: Path) -> None:
    """The fallback must not collapse ids that share a timestamp prefix."""
    labels = _labels(_nodes(with_paths=False), tmp_path)
    assert len(set(labels)) == len(labels), f"fallback labels collided: {labels}"
    assert "subagent · 01a051ee" not in labels, "an eight-character prefix is not an identity"
    for _, _, nickname in _CHILDREN:
        assert f"subagent · {nickname}" in labels, labels

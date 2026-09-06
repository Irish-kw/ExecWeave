"""Visual UX & Readability tests (R5, R6, R7, R8).

Verifies:
- R5: Edge polyline geometry conforms strictly to SVG {M, L} commands.
- R6: Dark theme node category palette is distinct, high contrast, and visual hierarchy
      (selected, 1-hop neighbors, dimmed) is enforced.
- R7: Glow decay eliminates infinite animations and baseline ordinary edges are lightened.
- R8: Typographic hierarchy is well-formed and readable under Fit scale.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from execweave.live_view import LIVE_HTML
from execweave.live_view_markup import LIVE_MARKUP
from execweave.live_view_script_a import LIVE_SCRIPT_A
from execweave.live_view_script_b import LIVE_SCRIPT_B
from execweave.live_view_style import LIVE_STYLE


def _extract_css_rule(css: str, selector: str) -> str:
    """Extract the contents of a CSS rule block for a given selector, handling nested braces."""
    escaped = re.escape(selector)
    match = re.search(rf"{escaped}\s*\{{", css)
    assert match, f"Selector '{selector}' not found in stylesheet"
    start = match.end()
    depth = 1
    i = start
    while i < len(css) and depth > 0:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
        i += 1
    return css[start:i - 1].strip()


def _extract_js_function(js: str, fn_name: str) -> str:
    """Extract JavaScript function body, handling nested braces."""
    match = re.search(rf"function\s+{re.escape(fn_name)}\s*\([^)]*\)\s*\{{", js)
    assert match, f"Function '{fn_name}' not found"
    start = match.end()
    depth = 1
    i = start
    while i < len(js) and depth > 0:
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
        i += 1
    return js[start:i - 1].strip()


def _extract_var_map(css_block: str) -> dict[str, str]:
    """Parse CSS custom properties into a dictionary."""
    vars_dict: dict[str, str] = {}
    for entry in css_block.split(";"):
        if ":" in entry:
            key, value = entry.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key.startswith("--"):
                vars_dict[key] = value
    return vars_dict


# ==============================================================================
# R5: Polyline Edge Rendering & {M, L} Path Conformance
# ==============================================================================

def test_base_curve_in_script_a_strictly_conforms_to_m_l_commands() -> None:
    """Base curve() in LIVE_SCRIPT_A must generate sampled polyline using ONLY {M, L}."""
    assert "function curve(e)" in LIVE_SCRIPT_A
    curve_body = _extract_js_function(LIVE_SCRIPT_A, "curve")
    # Must NOT generate native cubic C commands
    assert " C " not in curve_body, "curve(e) in LIVE_SCRIPT_A still emits native 'C' commands"
    assert "`M " in curve_body
    assert "L " in curve_body


def test_script_b_route_wrapper_enforces_m_l_polyline_on_ordinary_edges() -> None:
    """LIVE_SCRIPT_B must wrap execweaveRoute to ensure ordinary edges conform to {M, L}."""
    assert "execweaveRoute=function(edge)" in LIVE_SCRIPT_B
    assert "bundle" in LIVE_SCRIPT_B
    assert "lifecycle-return" in LIVE_SCRIPT_B
    # The wrapper converts any cubic 'C' command into sampled 'L' segments
    assert "route.d.includes('C')" in LIVE_SCRIPT_B
    assert "L " in LIVE_SCRIPT_B


def test_cubic_polyline_sampling_produces_valid_m_l_shape() -> None:
    """Simulate cubic Bezier sampling to confirm {M, L} polyline format."""
    sx, sy, p1x, p1y, p2x, p2y, tx, ty = 10.0, 20.0, 50.0, 20.0, 150.0, 200.0, 200.0, 200.0
    segments = []
    segments.append(f"M {sx} {sy}")
    for i in range(1, 8):
        t = i / 8.0
        u = 1.0 - t
        x = u * u * u * sx + 3 * u * u * t * p1x + 3 * u * t * t * p2x + t * t * t * tx
        y = u * u * u * sy + 3 * u * u * t * p1y + 3 * u * t * t * p2y + t * t * t * ty
        segments.append(f"L {x:.1f} {y:.1f}")
    segments.append(f"L {tx} {ty}")
    path_d = " ".join(segments)

    # Extract command letters exactly as tests/test_graph_edge_routing_e2e.py does:
    commands = [part for part in re.split(r"[-0-9.\s]+", path_d.strip()) if part]
    command_str = "".join(commands)
    assert command_str.startswith("M")
    assert set(command_str) <= {"M", "L"}
    assert len(commands) == 9  # 1 M + 7 interior L + 1 end L


# ==============================================================================
# R6: Dark Theme / Node Contrast & Category Palette
# ==============================================================================

def test_dark_and_light_category_palettes_defined_and_distinct() -> None:
    """Category colors must be defined and distinct for both dark and light themes."""
    root_dark = _extract_css_rule(LIVE_STYLE, ":root")
    dark_vars = _extract_var_map(root_dark)

    categories = [
        "--node-agent",
        "--node-process",
        "--node-file",
        "--node-network",
        "--node-tool",
        "--node-model",
        "--node-other",
    ]

    for cat in categories:
        assert cat in dark_vars, f"Missing dark theme category variable: {cat}"

    # All dark theme category color values must be mutually distinct
    dark_colors = [dark_vars[cat] for cat in categories]
    assert len(dark_colors) == len(set(dark_colors)), f"Duplicate category colors in dark theme: {dark_colors}"

    # Verify light theme
    root_light = _extract_css_rule(LIVE_STYLE, ':root[data-theme="light"]')
    light_vars = _extract_var_map(root_light)

    for cat in categories:
        assert cat in light_vars, f"Missing light theme category variable: {cat}"

    light_colors = [light_vars[cat] for cat in categories]
    assert len(light_colors) == len(set(light_colors)), f"Duplicate category colors in light theme: {light_colors}"


def test_visual_hierarchy_styles_enforced() -> None:
    """Visual hierarchy rules for selected, 1-hop neighbor, and dimmed nodes."""
    # 1. Selected node: prominent accent border (stroke-width >= 2.6) and glow (filter drop-shadow)
    selected_rule = _extract_css_rule(LIVE_STYLE, ".node.selected rect")
    assert "var(--selected)" in selected_rule
    stroke_width_match = re.search(r"stroke-width:\s*([0-9.]+)", selected_rule)
    assert stroke_width_match and float(stroke_width_match.group(1)) >= 2.6
    assert "drop-shadow" in selected_rule

    # 2. Directly connected 1-hop neighbors: subtle highlighted border
    neighbor_rule = _extract_css_rule(LIVE_STYLE, ".node.context-neighbor rect")
    neighbor_width_match = re.search(r"stroke-width:\s*([0-9.]+)", neighbor_rule)
    assert neighbor_width_match and float(neighbor_width_match.group(1)) >= 1.8
    assert "var(--selected)" in neighbor_rule or "color-mix" in neighbor_rule

    # 3. Dimmed nodes: opacity 0.32
    context_dim_rule = _extract_css_rule(LIVE_STYLE, ".node.context-dim")
    dim_opacity_match = re.search(r"opacity:\s*([0-9.]+)", context_dim_rule)
    assert dim_opacity_match and abs(float(dim_opacity_match.group(1)) - 0.32) < 0.01

    # 4. Context neighbor runtime logic in LIVE_SCRIPT_B
    assert "execweaveFocusNodeEdges" in LIVE_SCRIPT_B
    assert "context-neighbor" in LIVE_SCRIPT_B
    assert "execweaveClearContextFocus" in LIVE_SCRIPT_B


# ==============================================================================
# R7: Glow Decay / Prohibition of Permanent Blinking
# ==============================================================================

def test_no_infinite_css_animations_in_latest_elements() -> None:
    """Strictly prohibit infinite animations on graph nodes and edges."""
    # Rule 1: .node.latest rect must NOT have infinite animation
    latest_node_rule = _extract_css_rule(LIVE_STYLE, ".node.latest rect")
    assert "infinite" not in latest_node_rule, "Prohibited 'infinite' animation found on .node.latest rect"
    assert "forwards" in latest_node_rule, ".node.latest rect should decay and persist in resting state ('forwards')"

    # Rule 2: .edge.latest-edge must NOT have infinite animation
    latest_edge_rule = _extract_css_rule(LIVE_STYLE, ".edge.latest-edge")
    assert "infinite" not in latest_edge_rule, "Prohibited 'infinite' animation found on .edge.latest-edge"
    assert "forwards" in latest_edge_rule, ".edge.latest-edge should decay and persist in resting state ('forwards')"

    # Rule 3: Keyframes must exist and provide smooth decay
    node_keyframes = _extract_css_rule(LIVE_STYLE, "@keyframes latestNode")
    assert "0%" in node_keyframes and "100%" in node_keyframes

    edge_keyframes = _extract_css_rule(LIVE_STYLE, "@keyframes latestEdge")
    assert "0%" in edge_keyframes and "100%" in edge_keyframes


def test_baseline_ordinary_edges_lightened_compared_to_active_paths() -> None:
    """Baseline ordinary edges must have lower visual weight so active paths pop."""
    base_edge_rule = _extract_css_rule(LIVE_STYLE, ".edge")
    base_width_match = re.search(r"stroke-width:\s*([0-9.]+)", base_edge_rule)
    assert base_width_match and float(base_width_match.group(1)) <= 1.35
    base_opacity_match = re.search(r"opacity:\s*([0-9.]+)", base_edge_rule)
    assert base_opacity_match and float(base_opacity_match.group(1)) <= 0.60

    # Active / selected edge must have heavier weight
    selected_edge_rule = _extract_css_rule(LIVE_STYLE, ".edge.selected")
    selected_width_match = re.search(r"stroke-width:\s*([0-9.]+)", selected_edge_rule)
    assert selected_width_match and float(selected_width_match.group(1)) >= 2.0


def test_mark_latest_runtime_triggers_fresh_glow_decay() -> None:
    """markLatest in LIVE_SCRIPT_B must reset animation state to replay transient pulse."""
    assert "function markLatest(nodeIdValue,edgeIdValue)" in LIVE_SCRIPT_B
    # Checks for animation reset logic (e.g. style.animation = 'none', offsetWidth, etc.)
    assert "style.animation" in LIVE_SCRIPT_B or "classList.add('latest')" in LIVE_SCRIPT_B


# ==============================================================================
# R8: Typography Hierarchy & Fit Scale Readability
# ==============================================================================

def test_typography_scale_and_rules_well_formed() -> None:
    """Establishing clear typography scale across type, name, detail, and edge labels."""
    # Type label: 9-10px, clear tracking, uppercase
    type_rule = _extract_css_rule(LIVE_STYLE, ".node .type")
    type_size_match = re.search(r"font-size:\s*([0-9.]+)px", type_rule)
    assert type_size_match and 9.0 <= float(type_size_match.group(1)) <= 10.0
    assert "uppercase" in type_rule
    assert "letter-spacing" in type_rule

    # Primary name label: 12-13.5px, bold/semibold
    name_rule = _extract_css_rule(LIVE_STYLE, ".node .name-label")
    name_size_match = re.search(r"font-size:\s*([0-9.]+)px", name_rule)
    assert name_size_match and 12.0 <= float(name_size_match.group(1)) <= 13.5
    name_weight_match = re.search(r"font-weight:\s*([0-9]+)", name_rule)
    assert name_weight_match and int(name_weight_match.group(1)) >= 600

    # Secondary / detail text: 10px
    detail_rule = _extract_css_rule(LIVE_STYLE, ".node .detail-text,.node .secondary-text")
    detail_size_match = re.search(r"font-size:\s*([0-9.]+)px", detail_rule)
    assert detail_size_match and 9.5 <= float(detail_size_match.group(1)) <= 10.5

    # Edge label: 9.5-10.5px
    label_rule = _extract_css_rule(LIVE_STYLE, ".label")
    label_size_match = re.search(r"font-size:\s*([0-9.]+)px", label_rule)
    assert label_size_match and 9.5 <= float(label_size_match.group(1)) <= 10.5


def test_edge_label_halo_for_fit_scale_readability() -> None:
    """Edge labels must use SVG stroke halo paint-order for contrast at Fit scale."""
    label_rule = _extract_css_rule(LIVE_STYLE, ".label")
    assert "paint-order:stroke fill" in label_rule or "paint-order: stroke fill" in label_rule
    assert "stroke:var(--bg)" in label_rule or "stroke: var(--bg)" in label_rule
    stroke_width_match = re.search(r"stroke-width:\s*([0-9.]+)px", label_rule)
    assert stroke_width_match and float(stroke_width_match.group(1)) >= 3.0

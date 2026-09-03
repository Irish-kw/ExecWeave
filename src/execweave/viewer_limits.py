from __future__ import annotations

import argparse
import os


DEFAULT_VIEWER_MAX_NODES = 1500
DEFAULT_VIEWER_MAX_EDGES = 4000
DEFAULT_VIEWER_MAX_DOM_ELEMENTS = 5000

VIEWER_MAX_NODES_ENV = "EXECWEAVE_VIEWER_MAX_NODES"
VIEWER_MAX_EDGES_ENV = "EXECWEAVE_VIEWER_MAX_EDGES"
VIEWER_MAX_DOM_ELEMENTS_ENV = "EXECWEAVE_VIEWER_MAX_DOM_ELEMENTS"


def viewer_limit_option(value: str) -> int:
    """Parse one positive dashboard safety limit for the command line."""
    try:
        parsed = int(str(value).strip())
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"viewer limit must be a whole number, not {value!r}"
        ) from None
    if parsed < 1:
        raise argparse.ArgumentTypeError(
            f"viewer limit must be at least 1, not {parsed}"
        )
    return parsed


def _environment_limit(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return value if value >= 1 else default


def resolve_viewer_limits(
    *,
    max_nodes: int | None = None,
    max_edges: int | None = None,
    max_dom_elements: int | None = None,
    defaults: tuple[int, int, int] = (
        DEFAULT_VIEWER_MAX_NODES,
        DEFAULT_VIEWER_MAX_EDGES,
        DEFAULT_VIEWER_MAX_DOM_ELEMENTS,
    ),
) -> tuple[int, int, int]:
    """Resolve one consistent budget from arguments, environment, or defaults."""
    default_nodes, default_edges, default_dom = defaults
    return (
        max_nodes
        if max_nodes is not None
        else _environment_limit(VIEWER_MAX_NODES_ENV, default_nodes),
        max_edges
        if max_edges is not None
        else _environment_limit(VIEWER_MAX_EDGES_ENV, default_edges),
        max_dom_elements
        if max_dom_elements is not None
        else _environment_limit(VIEWER_MAX_DOM_ELEMENTS_ENV, default_dom),
    )


def apply_viewer_limits(
    max_nodes: int | None,
    max_edges: int | None,
    max_dom_elements: int | None,
) -> None:
    """Publish CLI-selected limits to every renderer in this process."""
    values = (
        (VIEWER_MAX_NODES_ENV, max_nodes),
        (VIEWER_MAX_EDGES_ENV, max_edges),
        (VIEWER_MAX_DOM_ELEMENTS_ENV, max_dom_elements),
    )
    for name, value in values:
        if value is not None:
            os.environ[name] = str(int(value))


def viewer_limits_bootstrap(
    limits: tuple[int, int, int] | None = None,
) -> str:
    """Return the tiny JS bootstrap consumed by the live dashboard."""
    nodes, edges, dom = limits or resolve_viewer_limits()
    return (
        "window.__execweaveViewerLimits={"
        f"max_nodes:{int(nodes)},max_edges:{int(edges)},max_dom_elements:{int(dom)}"
        "};"
    )

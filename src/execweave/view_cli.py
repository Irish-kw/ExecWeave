from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path

from .theme import ensure_viewer_theme
from .viewer import build_viewer_from_graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave view",
        description="Create a standalone local interactive HTML graph viewer.",
    )
    parser.add_argument("graph", type=Path, help="Path to a graph JSON file")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path (default: <graph-stem>.html)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the generated viewer in the default browser",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    graph_path = args.graph.expanduser().resolve()
    output = args.output or graph_path.with_name(f"{graph_path.stem}.html")
    try:
        written = build_viewer_from_graph(graph_path, output, open_browser=False)
        ensure_viewer_theme(written)
    except (FileExistsError, ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.open_browser:
        webbrowser.open(written.as_uri())
    print(json.dumps({"output": str(written)}, indent=2, sort_keys=True))
    return 0

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .graph_ops import load_graph
from .rule_pack import analyze_graph_with_rule_packs, load_rule_pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-rule-pack",
        description="Run bounded observation rule packs over an ExecWeave execution graph.",
    )
    parser.add_argument("graph", type=Path, help="Path to a graph JSON file")
    parser.add_argument(
        "--rule-pack",
        dest="rule_packs",
        action="append",
        type=Path,
        required=True,
        help="JSON rule-pack path. Repeat to load multiple packs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON report output path; the report is always printed to stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        graph = load_graph(args.graph)
        packs = [load_rule_pack(path) for path in args.rule_packs]
        report = analyze_graph_with_rule_packs(graph, packs)
        if args.output is not None:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists() and output.stat().st_size > 0:
                raise FileExistsError(f"ExecWeave rule-pack output already exists: {output}")
            output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

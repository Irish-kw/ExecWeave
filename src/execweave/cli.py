from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from .backends import backend_diagnostics, create_collector, resolve_backend
from .benchmark import format_benchmark, run_benchmark
from .graph import build_execution_graph, write_execution_graph
from .graph_ops import (
    filter_graph,
    find_paths,
    graph_summary,
    load_graph,
    write_graph_payload,
)
from .sink import JsonlSink
from .validate import validate_event_stream
from .viewer import build_viewer_from_graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave",
        description="Graph-ready runtime collection for AI agents.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run = subparsers.add_parser("run", help="Run a command inside an ExecWeave session")
    run.add_argument(
        "--watch-root",
        type=Path,
        default=None,
        help="Working directory to observe (default: current directory)",
    )
    run.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSONL output path (default: .execweave/runs/<session-id>.jsonl)",
    )
    run.add_argument(
        "--interval",
        type=float,
        default=0.10,
        help="Portable backend polling interval in seconds (default: 0.10)",
    )
    run.add_argument(
        "--backend",
        choices=["auto", "portable", "strace"],
        default="auto",
        help="Runtime backend. auto prefers strace on Linux when available",
    )
    run.add_argument("--no-files", action="store_true", help="Disable filesystem observation")
    run.add_argument("--no-network", action="store_true", help="Disable network observation")
    run.add_argument(
        "--keep-native-trace",
        action="store_true",
        help="Keep raw Linux strace files after parsing (off by default)",
    )
    run.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")

    subparsers.add_parser("doctor", help="Show runtime collector availability")

    benchmark = subparsers.add_parser(
        "benchmark", help="Run the Phase 1 overhead smoke benchmark"
    )
    benchmark.add_argument(
        "--backend", choices=["auto", "portable", "strace"], default="auto"
    )
    benchmark.add_argument("--iterations", type=int, default=5)

    validate = subparsers.add_parser(
        "validate", help="Validate one graph-ready ExecWeave JSONL event stream"
    )
    validate.add_argument("path", type=Path, help="Path to a .jsonl event stream")
    validate.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Do not require session.started/session.finished (useful after an interrupted run)",
    )

    graph = subparsers.add_parser(
        "graph", help="Materialize a validated event stream into an execution graph"
    )
    graph.add_argument("path", type=Path, help="Path to a .jsonl event stream")
    graph.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Graph JSON output path (default: <input-stem>.graph.json)",
    )
    graph.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow graph construction from an interrupted but structurally valid run",
    )

    summary = subparsers.add_parser("graph-summary", help="Summarize an execution graph")
    summary.add_argument("path", type=Path, help="Path to a graph JSON file")

    graph_filter = subparsers.add_parser("graph-filter", help="Filter an execution graph")
    graph_filter.add_argument("path", type=Path, help="Path to a graph JSON file")
    graph_filter.add_argument("--output", type=Path, required=True)
    graph_filter.add_argument("--node-type", action="append", default=[])
    graph_filter.add_argument("--relation", action="append", default=[])
    graph_filter.add_argument("--backend", action="append", default=[])
    graph_filter.add_argument("--causal-only", action="store_true")

    path_query = subparsers.add_parser("path", help="Find directed paths in an execution graph")
    path_query.add_argument("graph", type=Path, help="Path to a graph JSON file")
    path_query.add_argument("source", help="Exact source node ID")
    path_query.add_argument("target", help="Exact target node ID")
    path_query.add_argument("--max-depth", type=int, default=6)
    path_query.add_argument("--max-paths", type=int, default=20)
    path_query.add_argument("--relation", action="append", default=[])
    path_query.add_argument("--causal-only", action="store_true")

    view = subparsers.add_parser(
        "view", help="Create a standalone local interactive HTML graph viewer"
    )
    view.add_argument("graph", type=Path, help="Path to a graph JSON file")
    view.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path (default: <graph-stem>.html)",
    )
    view.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the generated viewer in the default browser",
    )
    return parser


def _clean_command(command: list[str]) -> list[str]:
    result = list(command)
    if result and result[0] == "--":
        result = result[1:]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "doctor":
        print(json.dumps(backend_diagnostics(), indent=2, sort_keys=True))
        return 0

    if args.subcommand == "benchmark":
        try:
            result = run_benchmark(backend=args.backend, iterations=args.iterations)
        except (RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print(format_benchmark(result))
        return 0

    if args.subcommand == "validate":
        result = validate_event_stream(
            args.path,
            require_complete_session=not args.allow_incomplete,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0 if result.valid else 1

    if args.subcommand == "graph":
        source = args.path.expanduser().resolve()
        output = args.output or source.with_name(f"{source.stem}.graph.json")
        try:
            execution_graph = build_execution_graph(
                source,
                allow_incomplete=args.allow_incomplete,
            )
            written = write_execution_graph(execution_graph, output)
        except (FileExistsError, ValueError) as exc:
            parser.error(str(exc))
        summary = {
            "session_id": execution_graph.session_id,
            "event_count": execution_graph.event_count,
            "node_count": len(execution_graph.nodes),
            "edge_count": len(execution_graph.edges),
            "output": str(written),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if args.subcommand == "graph-summary":
        try:
            payload = load_graph(args.path)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(graph_summary(payload), indent=2, sort_keys=True))
        return 0

    if args.subcommand == "graph-filter":
        try:
            payload = load_graph(args.path)
            filtered = filter_graph(
                payload,
                node_types=args.node_type,
                relations=args.relation,
                causal_only=args.causal_only,
                backends=args.backend,
            )
            written = write_graph_payload(filtered, args.output)
        except (FileExistsError, ValueError) as exc:
            parser.error(str(exc))
        print(
            json.dumps(
                {**graph_summary(filtered), "output": str(written)},
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.subcommand == "path":
        try:
            payload = load_graph(args.graph)
            paths = find_paths(
                payload,
                source=args.source,
                target=args.target,
                max_depth=args.max_depth,
                max_paths=args.max_paths,
                relations=args.relation,
                causal_only=args.causal_only,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(
            json.dumps(
                {
                    "source": args.source,
                    "target": args.target,
                    "path_count": len(paths),
                    "paths": paths,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.subcommand == "view":
        graph_path = args.graph.expanduser().resolve()
        output = args.output or graph_path.with_name(f"{graph_path.stem}.html")
        try:
            written = build_viewer_from_graph(
                graph_path,
                output,
                open_browser=args.open_browser,
            )
        except (FileExistsError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({"output": str(written)}, indent=2, sort_keys=True))
        return 0

    command = _clean_command(args.command)
    if not command:
        parser.error("execweave run requires a command, e.g. execweave run -- claude")

    session_id = uuid4().hex
    watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
    output = args.output or (watch_root / ".execweave" / "runs" / f"{session_id}.jsonl")
    try:
        sink = JsonlSink(output)
    except FileExistsError as exc:
        parser.error(str(exc))

    try:
        resolved = resolve_backend(args.backend)
        collector = create_collector(
            backend=args.backend,
            session_id=session_id,
            sink=sink,
            watch_root=watch_root,
            poll_interval=args.interval,
            collect_filesystem=not args.no_files,
            collect_network=not args.no_network,
            keep_raw_trace=args.keep_native_trace,
        )
    except RuntimeError as exc:
        parser.error(str(exc))

    print(f"ExecWeave session: {session_id}")
    print(f"Backend: {resolved}")
    print(f"Working directory: {watch_root}")
    print(f"Events: {sink.path}")
    return collector.run(command)

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from .analysis import analyze_graph
from .backends import backend_diagnostics, create_collector, resolve_backend
from .benchmark import format_benchmark, run_benchmark
from .graph import build_execution_graph, write_execution_graph
from .graph_ops import (
    condense_graph,
    filter_graph,
    find_paths,
    graph_summary,
    load_graph,
    write_graph_payload,
)
from .live import run_live
from .sink import JsonlSink
from .validate import validate_event_stream
from .viewer import build_viewer_from_graph
from .workflow import record_to_viewer


def _add_collection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--watch-root",
        type=Path,
        default=None,
        help="Working directory to observe (default: current directory)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.10,
        help="Portable backend polling interval in seconds (default: 0.10)",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "portable", "strace"],
        default="auto",
        help="Runtime backend. auto prefers strace on Linux when available",
    )
    parser.add_argument("--no-files", action="store_true", help="Disable filesystem observation")
    parser.add_argument("--no-network", action="store_true", help="Disable network observation")
    parser.add_argument(
        "--keep-native-trace",
        action="store_true",
        help="Keep raw Linux strace files after parsing (off by default)",
    )


def _add_live_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--watch-root",
        type=Path,
        default=None,
        help="Working directory to observe (default: current directory)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Artifact directory (default: .execweave/runs/<session-id>/)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.10,
        help="Portable collector polling interval in seconds (default: 0.10)",
    )
    parser.add_argument("--no-files", action="store_true", help="Disable filesystem observation")
    parser.add_argument("--no-network", action="store_true", help="Disable network observation")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Localhost port. 0 selects an available port automatically (default: 0)",
    )
    parser.add_argument(
        "--linger",
        type=float,
        default=2.0,
        help="Seconds to keep the live server open after the command exits (default: 2.0)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the live graph in the default browser",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave",
        description="Graph-ready runtime collection for AI agents.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run = subparsers.add_parser("run", help="Run a command inside an ExecWeave session")
    _add_collection_arguments(run)
    run.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSONL output path (default: .execweave/runs/<session-id>.jsonl)",
    )
    run.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")

    record = subparsers.add_parser(
        "record",
        help="Record a command, validate it, build the graph, and create the local viewer",
    )
    _add_collection_arguments(record)
    record.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Artifact directory (default: .execweave/runs/<session-id>/)",
    )
    record.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the generated viewer after the command exits",
    )
    record.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")

    live = subparsers.add_parser(
        "live",
        help="Run a command with the portable collector and stream its graph to localhost",
    )
    _add_live_arguments(live)
    live.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")

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

    graph_condense = subparsers.add_parser(
        "graph-condense",
        help="Collapse repetitive leaf resources into inspectable cluster nodes",
    )
    graph_condense.add_argument("path", type=Path, help="Path to a graph JSON file")
    graph_condense.add_argument("--output", type=Path, required=True)
    graph_condense.add_argument(
        "--threshold",
        type=int,
        default=8,
        help="Minimum equivalent leaf nodes required to form a cluster (default: 8)",
    )
    graph_condense.add_argument(
        "--sample-size",
        type=int,
        default=8,
        help="Maximum member names stored as cluster examples (default: 8)",
    )
    graph_condense.add_argument(
        "--keep-expansion",
        action="store_true",
        help="Embed original cluster members so the Viewer can expand them on demand",
    )

    analyze = subparsers.add_parser(
        "analyze",
        help="Run conservative explainable security rules over an execution graph",
    )
    analyze.add_argument("graph", type=Path, help="Path to a graph JSON file")
    analyze.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON report output path; findings are always printed to stdout",
    )

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

    if args.subcommand == "graph-condense":
        try:
            payload = load_graph(args.path)
            condensed = condense_graph(
                payload,
                threshold=args.threshold,
                sample_size=args.sample_size,
                include_expansion=args.keep_expansion,
            )
            written = write_graph_payload(condensed, args.output)
        except (FileExistsError, ValueError) as exc:
            parser.error(str(exc))
        print(
            json.dumps(
                {
                    **graph_summary(condensed),
                    "condensation": condensed.get("condensation"),
                    "output": str(written),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.subcommand == "analyze":
        try:
            payload = load_graph(args.graph)
            report = analyze_graph(payload)
            if args.output is not None:
                output = args.output.expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                if output.exists() and output.stat().st_size > 0:
                    raise FileExistsError(f"ExecWeave analysis output already exists: {output}")
                output.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        except (FileExistsError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
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

    if args.subcommand == "record":
        command = _clean_command(args.command)
        if not command:
            parser.error(
                "execweave record requires a command, e.g. execweave record --open -- claude"
            )
        watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
        try:
            result = record_to_viewer(
                command,
                watch_root=watch_root,
                output_dir=args.output_dir,
                backend=args.backend,
                poll_interval=args.interval,
                collect_filesystem=not args.no_files,
                collect_network=not args.no_network,
                keep_raw_trace=args.keep_native_trace,
                open_browser=args.open_browser,
            )
        except (FileExistsError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return result.return_code

    if args.subcommand == "live":
        command = _clean_command(args.command)
        if not command:
            parser.error("execweave live requires a command, e.g. execweave live --open -- claude")
        watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
        try:
            result = run_live(
                command,
                watch_root=watch_root,
                output_dir=args.output_dir,
                poll_interval=args.interval,
                collect_filesystem=not args.no_files,
                collect_network=not args.no_network,
                port=args.port,
                open_browser=args.open_browser,
                linger_seconds=args.linger,
                announce=lambda url: print(f"ExecWeave live: {url}", flush=True),
            )
        except (FileExistsError, RuntimeError, ValueError, OSError) as exc:
            parser.error(str(exc))
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return result.return_code

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

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from .backends import backend_diagnostics, create_collector, resolve_backend
from .benchmark import format_benchmark, run_benchmark
from .sink import JsonlSink


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

    command = _clean_command(args.command)
    if not command:
        parser.error("execweave run requires a command, e.g. execweave run -- claude")

    session_id = uuid4().hex
    watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
    output = args.output or (watch_root / ".execweave" / "runs" / f"{session_id}.jsonl")
    sink = JsonlSink(output)
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

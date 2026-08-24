from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from .collector import RuntimeCollector
from .sink import JsonlSink


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave",
        description="Visualize-ready runtime collection for AI agents.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run = subparsers.add_parser("run", help="Run a command inside an ExecWeave session")
    run.add_argument(
        "--watch-root",
        type=Path,
        default=None,
        help="Directory whose filesystem changes are observed (default: current directory)",
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
        default=0.25,
        help="Process/network polling interval in seconds (default: 0.25)",
    )
    run.add_argument("--no-files", action="store_true", help="Disable filesystem observation")
    run.add_argument("--no-network", action="store_true", help="Disable network observation")
    run.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand != "run":
        parser.error("unknown subcommand")

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("execweave run requires a command, e.g. execweave run -- claude")

    session_id = uuid4().hex
    watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
    output = args.output or (watch_root / ".execweave" / "runs" / f"{session_id}.jsonl")
    sink = JsonlSink(output)

    collector = RuntimeCollector(
        session_id=session_id,
        sink=sink,
        watch_root=watch_root,
        poll_interval=args.interval,
        collect_filesystem=not args.no_files,
        collect_network=not args.no_network,
    )

    print(f"ExecWeave session: {session_id}")
    print(f"Watching: {watch_root}")
    print(f"Events: {sink.path}")
    return collector.run(command)

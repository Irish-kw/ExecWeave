from __future__ import annotations

import argparse
from pathlib import Path

from .top import run_top


def _clean_command(command: list[str]) -> list[str]:
    result = list(command)
    if result and result[0] == "--":
        result = result[1:]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave top",
        description="Show a terminal live dashboard for one ExecWeave session.",
    )
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
    parser.add_argument(
        "--refresh",
        type=float,
        default=0.50,
        help="Terminal dashboard refresh interval in seconds (default: 0.50)",
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
        help="Open the Web Viewer alongside the terminal dashboard",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = _clean_command(args.command)
    if not command:
        parser.error("execweave top requires a command, e.g. execweave top -- codex")
    watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
    try:
        result = run_top(
            command,
            watch_root=watch_root,
            output_dir=args.output_dir,
            poll_interval=args.interval,
            refresh_seconds=args.refresh,
            collect_filesystem=not args.no_files,
            collect_network=not args.no_network,
            port=args.port,
            open_browser=args.open_browser,
            linger_seconds=args.linger,
        )
    except (FileExistsError, RuntimeError, ValueError, OSError) as exc:
        parser.error(str(exc))
    return result.return_code

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from .top import _consume_attach_token_file, run_attached_top, run_top


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
        help="Open the Web Viewer in addition to the detached terminal dashboard",
    )
    parser.add_argument("--attach", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--attach-token-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--attach-command-json", default="[]", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    return parser


def _parse_attach_command(raw: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid detached dashboard command metadata") from exc
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ValueError("detached dashboard command metadata must be a string array")
    return payload


def _validate_attach_url(raw: str) -> str:
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid detached dashboard attach URL") from exc

    if parsed.scheme != "http":
        raise ValueError("detached dashboard attach URL must use localhost HTTP")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("detached dashboard attach URL must not contain credentials")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("detached dashboard attach URL must target localhost")
    if port is None or not (1 <= port <= 65535):
        raise ValueError("detached dashboard attach URL requires a valid localhost port")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("detached dashboard attach URL must be a live-server base URL")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.attach is not None:
        try:
            live_url = _validate_attach_url(args.attach)
            if args.attach_token_file is None:
                raise ValueError("detached dashboard attach token is required")
            token = _consume_attach_token_file(args.attach_token_file)
            command = _parse_attach_command(args.attach_command_json)
            run_attached_top(
                live_url,
                token=token,
                command=command,
                refresh_seconds=args.refresh,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            parser.error(str(exc))
        return 0

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

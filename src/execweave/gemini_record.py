from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backends import BackendName
from .provider_record import ProviderRecordResult, record_provider_to_viewer

GeminiRecordResult = ProviderRecordResult


def record_gemini_to_viewer(
    command: list[str],
    *,
    watch_root: str | Path,
    output_dir: str | Path | None = None,
    backend: BackendName = "auto",
    poll_interval: float = 0.10,
    collect_filesystem: bool = True,
    collect_network: bool = True,
    keep_raw_trace: bool = False,
    correlation_window_ms: int = 3000,
    open_browser: bool = False,
) -> GeminiRecordResult:
    """Record one Gemini CLI run using the shared provider-record pipeline."""
    return record_provider_to_viewer(
        command,
        provider_name="Gemini CLI",
        watch_root=watch_root,
        output_dir=output_dir,
        backend=backend,
        poll_interval=poll_interval,
        collect_filesystem=collect_filesystem,
        collect_network=collect_network,
        keep_raw_trace=keep_raw_trace,
        correlation_window_ms=correlation_window_ms,
        open_browser=open_browser,
    )


def _clean_command(command: list[str]) -> list[str]:
    result = list(command)
    if result and result[0] == "--":
        result = result[1:]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-gemini-record",
        description="Record runtime evidence, Gemini CLI hook telemetry, and conservative Tool-to-Process correlation in one local run.",
    )
    parser.add_argument("--watch-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--interval", type=float, default=0.10)
    parser.add_argument("--backend", choices=["auto", "portable", "strace"], default="auto")
    parser.add_argument("--correlation-window-ms", type=int, default=3000)
    parser.add_argument("--no-files", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--keep-native-trace", action="store_true")
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = _clean_command(args.command)
    if not command:
        parser.error("a Gemini CLI command is required, e.g. execweave-gemini-record --open -- gemini")
    watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
    try:
        result = record_gemini_to_viewer(
            command,
            watch_root=watch_root,
            output_dir=args.output_dir,
            backend=args.backend,
            poll_interval=args.interval,
            collect_filesystem=not args.no_files,
            collect_network=not args.no_network,
            keep_raw_trace=args.keep_native_trace,
            correlation_window_ms=args.correlation_window_ms,
            open_browser=args.open_browser,
        )
    except (FileExistsError, RuntimeError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return result.runtime.return_code


if __name__ == "__main__":
    raise SystemExit(main())

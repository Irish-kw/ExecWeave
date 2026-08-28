from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backends import BackendName
from .codex_message_diagnostics import enrich_codex_message_consumption
from .codex_message_transport_diagnostics import enrich_codex_message_transport_diagnostics
from .codex_rollout_structures import enrich_codex_rollout_structures
from .codex_rollout_trace import (
    CODEX_ROLLOUT_TRACE_ROOT_ENV,
    codex_rollout_trace_environment,
    import_codex_rollout_traces,
)
from .provider_record import ProviderRecordResult, record_provider_to_viewer

CodexRecordResult = ProviderRecordResult

_DIRECT_JS_RUNNERS = frozenset({"npx", "pnpx", "bunx"})
_SUBCOMMAND_JS_RUNNERS = {
    "npm": frozenset({"exec"}),
    "pnpm": frozenset({"dlx", "exec"}),
}


def _launcher_name(value: str) -> str:
    name = Path(value).name.lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _is_codex_package(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized == "codex"
        or normalized == "@openai/codex"
        or normalized.startswith("@openai/codex@")
    )


def _codex_reducer_command_prefix(command: list[str]) -> list[str]:
    """Return the launch prefix needed to invoke Codex subcommands again.

    Direct launchers keep the historical one-argv behavior. For explicit,
    recognized JavaScript package runners, preserve the runner flags/subcommand
    through the Codex package token, but never copy Codex runtime arguments such
    as ``--model`` into the reducer invocation.
    """
    if not command:
        raise ValueError("Codex command must not be empty")

    launcher = _launcher_name(command[0])
    scan = False
    if launcher in _DIRECT_JS_RUNNERS:
        scan = True
    elif launcher in _SUBCOMMAND_JS_RUNNERS and len(command) > 1:
        scan = _launcher_name(command[1]) in _SUBCOMMAND_JS_RUNNERS[launcher]

    if scan:
        for index, value in enumerate(command[1:], start=1):
            if _is_codex_package(value):
                return list(command[: index + 1])
    return [command[0]]


def record_codex_to_viewer(
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
) -> CodexRecordResult:
    """Record one Codex run with runtime, hooks, and first-party rollout tracing.

    ExecWeave opts the child process into Codex's local rollout-trace bundle,
    preserving prompts, model-visible conversation, reasoning representations,
    tool/runtime payloads, terminal activity, and multi-agent information-flow
    whenever the installed Codex build exposes them. The richer bundle is
    reduced and imported after Codex exits; older builds safely fall back to the
    existing hook + runtime collection path.
    """

    reducer_prefix = _codex_reducer_command_prefix(command)

    def enrich_rollout(runtime, semantic_sidecar, environment):
        del runtime
        trace_root = environment.get(CODEX_ROLLOUT_TRACE_ROOT_ENV)
        if not trace_root:
            return None
        result = import_codex_rollout_traces(
            trace_root=trace_root,
            semantic_sidecar=semantic_sidecar,
            codex_executable=reducer_prefix,
        )
        enrich_codex_rollout_structures(
            trace_root=trace_root,
            semantic_sidecar=semantic_sidecar,
        )
        enrich_codex_message_consumption(
            trace_root=trace_root,
            semantic_sidecar=semantic_sidecar,
        )
        enrich_codex_message_transport_diagnostics(
            trace_root=trace_root,
            semantic_sidecar=semantic_sidecar,
        )
        return result

    return record_provider_to_viewer(
        command,
        provider_name="Codex",
        watch_root=watch_root,
        output_dir=output_dir,
        backend=backend,
        poll_interval=poll_interval,
        collect_filesystem=collect_filesystem,
        collect_network=collect_network,
        keep_raw_trace=keep_raw_trace,
        correlation_window_ms=correlation_window_ms,
        open_browser=open_browser,
        provider_environment_builder=codex_rollout_trace_environment,
        post_runtime_semantic_enricher=enrich_rollout,
    )


def _clean_command(command: list[str]) -> list[str]:
    result = list(command)
    if result and result[0] == "--":
        result = result[1:]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-codex-record",
        description=(
            "Record runtime evidence, Codex hooks, first-party rollout payloads, "
            "multi-agent communication, and conservative Tool-to-Process correlation."
        ),
    )
    parser.add_argument("--watch-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--interval", type=float, default=0.10)
    parser.add_argument(
        "--backend",
        choices=["auto", "portable", "strace"],
        default="auto",
    )
    parser.add_argument(
        "--correlation-window-ms",
        type=int,
        default=3000,
        help="maximum Tool-to-Process correlation window in milliseconds (default: 3000)",
    )
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
        parser.error("a Codex command is required, e.g. execweave-codex-record --open -- codex")
    watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
    try:
        result = record_codex_to_viewer(
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

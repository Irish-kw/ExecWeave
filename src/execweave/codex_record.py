from __future__ import annotations

import argparse
import json
import os
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .backends import BackendName
from .correlation import CorrelationResult, correlate_tool_process
from .graph import build_execution_graph, write_execution_graph
from .semantic import SemanticMergeResult, merge_semantic_sidecar
from .viewer import write_graph_html
from .workflow import RecordResult, record_to_viewer

_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"


@dataclass(frozen=True)
class CodexRecordResult:
    runtime: RecordResult
    semantic_status: str
    semantic_sidecar: Path
    merged_event_stream: Path | None
    semantic_graph: Path | None
    semantic_viewer: Path | None
    semantic_merge: SemanticMergeResult | None
    correlation_status: str
    correlated_event_stream: Path | None
    correlated_graph: Path | None
    correlated_viewer: Path | None
    correlation: CorrelationResult | None

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime": self.runtime.to_dict(),
            "semantic_status": self.semantic_status,
            "semantic_sidecar": str(self.semantic_sidecar),
            "merged_event_stream": (
                str(self.merged_event_stream) if self.merged_event_stream is not None else None
            ),
            "semantic_graph": str(self.semantic_graph) if self.semantic_graph is not None else None,
            "semantic_viewer": str(self.semantic_viewer) if self.semantic_viewer is not None else None,
            "semantic_merge": (
                self.semantic_merge.to_dict() if self.semantic_merge is not None else None
            ),
            "correlation_status": self.correlation_status,
            "correlated_event_stream": (
                str(self.correlated_event_stream)
                if self.correlated_event_stream is not None
                else None
            ),
            "correlated_graph": (
                str(self.correlated_graph) if self.correlated_graph is not None else None
            ),
            "correlated_viewer": (
                str(self.correlated_viewer) if self.correlated_viewer is not None else None
            ),
            "correlation": self.correlation.to_dict() if self.correlation is not None else None,
        }


def _preflight(paths: list[Path]) -> None:
    conflicts = [path for path in paths if path.exists() and path.stat().st_size > 0]
    if conflicts:
        rendered = ", ".join(str(path) for path in conflicts)
        raise FileExistsError(f"ExecWeave Codex semantic artifacts already exist: {rendered}")


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
    """Record one Codex run with run-bound semantic and conservative correlation artifacts.

    The Codex process must already be configured to invoke ``execweave-codex-hook``.
    This function never edits Codex configuration. It only binds that hook to this
    run's semantic sidecar through an inherited environment variable.
    """
    if not command:
        raise ValueError("command must not be empty")
    if correlation_window_ms <= 0:
        raise ValueError("correlation_window_ms must be greater than zero")

    root = Path(watch_root).expanduser().resolve()
    run_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else root / ".execweave" / "runs" / uuid4().hex
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    semantic_sidecar = run_dir / "semantic.jsonl"
    merged_event_stream = run_dir / "events.semantic.jsonl"
    semantic_graph = run_dir / "graph.semantic.json"
    semantic_viewer = run_dir / "viewer.semantic.html"
    correlated_event_stream = run_dir / "events.correlated.jsonl"
    correlated_graph = run_dir / "graph.correlated.json"
    correlated_viewer = run_dir / "viewer.correlated.html"
    _preflight(
        [
            semantic_sidecar,
            merged_event_stream,
            semantic_graph,
            semantic_viewer,
            correlated_event_stream,
            correlated_graph,
            correlated_viewer,
        ]
    )

    previous = os.environ.get(_SEMANTIC_ENV)
    os.environ[_SEMANTIC_ENV] = str(semantic_sidecar)
    try:
        runtime = record_to_viewer(
            command,
            watch_root=root,
            output_dir=run_dir,
            backend=backend,
            poll_interval=poll_interval,
            collect_filesystem=collect_filesystem,
            collect_network=collect_network,
            keep_raw_trace=keep_raw_trace,
            open_browser=False,
        )
    finally:
        if previous is None:
            os.environ.pop(_SEMANTIC_ENV, None)
        else:
            os.environ[_SEMANTIC_ENV] = previous

    if not semantic_sidecar.exists() or semantic_sidecar.stat().st_size == 0:
        if open_browser:
            webbrowser.open(runtime.viewer.resolve().as_uri())
        return CodexRecordResult(
            runtime=runtime,
            semantic_status="no_events",
            semantic_sidecar=semantic_sidecar.resolve(),
            merged_event_stream=None,
            semantic_graph=None,
            semantic_viewer=None,
            semantic_merge=None,
            correlation_status="not_run_no_semantic_events",
            correlated_event_stream=None,
            correlated_graph=None,
            correlated_viewer=None,
            correlation=None,
        )

    merge_result = merge_semantic_sidecar(
        runtime.event_stream,
        semantic_sidecar,
        merged_event_stream,
    )
    execution_graph = build_execution_graph(merged_event_stream)
    write_execution_graph(execution_graph, semantic_graph)
    write_graph_html(execution_graph.to_dict(), semantic_viewer, open_browser=False)

    correlation_result = correlate_tool_process(
        merged_event_stream,
        correlated_event_stream,
        max_window_ms=correlation_window_ms,
    )
    correlated_execution_graph = build_execution_graph(correlated_event_stream)
    correlation_metadata = {"correlation": correlation_result.to_dict()}
    write_execution_graph(
        correlated_execution_graph,
        correlated_graph,
        metadata=correlation_metadata,
    )
    correlated_graph_payload = correlated_execution_graph.to_dict()
    correlated_graph_payload["metadata"] = correlation_metadata
    write_graph_html(
        correlated_graph_payload,
        correlated_viewer,
        open_browser=open_browser,
    )
    correlation_status = (
        "correlated"
        if correlation_result.correlated_tool_calls > 0
        else "completed_no_matches"
    )
    return CodexRecordResult(
        runtime=runtime,
        semantic_status="merged",
        semantic_sidecar=semantic_sidecar.resolve(),
        merged_event_stream=merged_event_stream.resolve(),
        semantic_graph=semantic_graph.resolve(),
        semantic_viewer=semantic_viewer.resolve(),
        semantic_merge=merge_result,
        correlation_status=correlation_status,
        correlated_event_stream=correlated_event_stream.resolve(),
        correlated_graph=correlated_graph.resolve(),
        correlated_viewer=correlated_viewer.resolve(),
        correlation=correlation_result,
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
            "Record runtime evidence, OpenAI Codex hook telemetry, and conservative "
            "Tool-to-Process correlation in one local run."
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

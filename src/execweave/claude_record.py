from __future__ import annotations

import argparse
import json
import os
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .backends import BackendName
from .graph import build_execution_graph, write_execution_graph
from .semantic import SemanticMergeResult, merge_semantic_sidecar
from .viewer import write_graph_html
from .workflow import RecordResult, record_to_viewer

_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"


@dataclass(frozen=True)
class ClaudeRecordResult:
    runtime: RecordResult
    semantic_status: str
    semantic_sidecar: Path
    merged_event_stream: Path | None
    semantic_graph: Path | None
    semantic_viewer: Path | None
    semantic_merge: SemanticMergeResult | None

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
        }


def _preflight(paths: list[Path]) -> None:
    conflicts = [path for path in paths if path.exists() and path.stat().st_size > 0]
    if conflicts:
        rendered = ", ".join(str(path) for path in conflicts)
        raise FileExistsError(f"ExecWeave Claude semantic artifacts already exist: {rendered}")


def record_claude_to_viewer(
    command: list[str],
    *,
    watch_root: str | Path,
    output_dir: str | Path | None = None,
    backend: BackendName = "auto",
    poll_interval: float = 0.10,
    collect_filesystem: bool = True,
    collect_network: bool = True,
    keep_raw_trace: bool = False,
    open_browser: bool = False,
) -> ClaudeRecordResult:
    """Record one Claude run with a run-bound semantic sidecar.

    This function is intended for the dedicated CLI process. It temporarily sets
    EXECWEAVE_SEMANTIC_SIDECAR only inside that process so Claude Code and its hook
    commands inherit a run-specific path without mutating the caller's shell.
    """
    if not command:
        raise ValueError("command must not be empty")

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
    _preflight([semantic_sidecar, merged_event_stream, semantic_graph, semantic_viewer])

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
        return ClaudeRecordResult(
            runtime=runtime,
            semantic_status="no_events",
            semantic_sidecar=semantic_sidecar.resolve(),
            merged_event_stream=None,
            semantic_graph=None,
            semantic_viewer=None,
            semantic_merge=None,
        )

    merge_result = merge_semantic_sidecar(
        runtime.event_stream,
        semantic_sidecar,
        merged_event_stream,
    )
    execution_graph = build_execution_graph(merged_event_stream)
    write_execution_graph(execution_graph, semantic_graph)
    write_graph_html(
        execution_graph.to_dict(),
        semantic_viewer,
        open_browser=open_browser,
    )
    return ClaudeRecordResult(
        runtime=runtime,
        semantic_status="merged",
        semantic_sidecar=semantic_sidecar.resolve(),
        merged_event_stream=merged_event_stream.resolve(),
        semantic_graph=semantic_graph.resolve(),
        semantic_viewer=semantic_viewer.resolve(),
        semantic_merge=merge_result,
    )


def _clean_command(command: list[str]) -> list[str]:
    result = list(command)
    if result and result[0] == "--":
        result = result[1:]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-claude-record",
        description=(
            "Record runtime evidence and bind Claude Code hook telemetry to the same local run."
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
        parser.error("a Claude command is required, e.g. execweave-claude-record --open -- claude")
    watch_root = (args.watch_root or Path.cwd()).expanduser().resolve()
    try:
        result = record_claude_to_viewer(
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
    except (FileExistsError, RuntimeError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return result.runtime.return_code


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

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
class ProviderRecordResult:
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


def _artifact_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "semantic_sidecar": run_dir / "semantic.jsonl",
        "merged_event_stream": run_dir / "events.semantic.jsonl",
        "semantic_graph": run_dir / "graph.semantic.json",
        "semantic_viewer": run_dir / "viewer.semantic.html",
        "correlated_event_stream": run_dir / "events.correlated.jsonl",
        "correlated_graph": run_dir / "graph.correlated.json",
        "correlated_viewer": run_dir / "viewer.correlated.html",
    }


def _preflight(paths: list[Path], *, provider_name: str) -> None:
    conflicts = [path for path in paths if path.exists() and path.stat().st_size > 0]
    if conflicts:
        rendered = ", ".join(str(path) for path in conflicts)
        raise FileExistsError(
            f"ExecWeave {provider_name} semantic artifacts already exist: {rendered}"
        )


def record_provider_to_viewer(
    command: list[str],
    *,
    provider_name: str,
    watch_root: str | Path,
    output_dir: str | Path | None = None,
    backend: BackendName = "auto",
    poll_interval: float = 0.10,
    collect_filesystem: bool = True,
    collect_network: bool = True,
    keep_raw_trace: bool = False,
    correlation_window_ms: int = 3000,
    open_browser: bool = False,
) -> ProviderRecordResult:
    """Record runtime + provider semantic evidence into layered local artifacts.

    Provider-specific hooks must already be configured to write to the inherited
    ``EXECWEAVE_SEMANTIC_SIDECAR`` path. This core never edits provider settings.
    Raw runtime and semantic evidence remain separate; correlation always derives a
    new stream and stays explicitly inferred/non-causal.
    """
    if not command:
        raise ValueError("command must not be empty")
    if not provider_name.strip():
        raise ValueError("provider_name must not be empty")
    if correlation_window_ms <= 0:
        raise ValueError("correlation_window_ms must be greater than zero")

    root = Path(watch_root).expanduser().resolve()
    run_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else root / ".execweave" / "runs" / uuid4().hex
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = _artifact_paths(run_dir)
    _preflight(list(paths.values()), provider_name=provider_name)

    semantic_sidecar = paths["semantic_sidecar"]
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
        return ProviderRecordResult(
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

    merged_event_stream = paths["merged_event_stream"]
    semantic_graph = paths["semantic_graph"]
    semantic_viewer = paths["semantic_viewer"]
    correlated_event_stream = paths["correlated_event_stream"]
    correlated_graph = paths["correlated_graph"]
    correlated_viewer = paths["correlated_viewer"]

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
    return ProviderRecordResult(
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

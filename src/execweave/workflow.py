from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .backends import BackendName, create_collector, resolve_backend
from .fidelity import write_fidelity_report
from .graph import build_execution_graph, write_execution_graph
from .semantic import merge_semantic_sidecar
from .sink import JsonlSink
from .theme import ensure_viewer_theme
from .validate import validate_event_stream
from .viewer_projection import strip_internal_hook_execution_graph, write_graph_html

_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"
_RUN_ID_ENV = "EXECWEAVE_RUN_ID"
_SESSION_ID_ENV = "EXECWEAVE_SESSION_ID"


@dataclass(frozen=True)
class RecordResult:
    session_id: str
    backend: str
    return_code: int
    output_dir: Path
    event_stream: Path
    fidelity: Path
    graph: Path
    viewer: Path
    event_count: int
    node_count: int
    edge_count: int
    semantic_sidecar: Path | None = None
    materialized_event_stream: Path | None = None
    semantic_event_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "backend": self.backend,
            "return_code": self.return_code,
            "output_dir": str(self.output_dir),
            "event_stream": str(self.event_stream),
            "fidelity": str(self.fidelity),
            "graph": str(self.graph),
            "viewer": str(self.viewer),
            "event_count": self.event_count,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "semantic_sidecar": (
                str(self.semantic_sidecar) if self.semantic_sidecar is not None else None
            ),
            "materialized_event_stream": (
                str(self.materialized_event_stream)
                if self.materialized_event_stream is not None
                else str(self.event_stream)
            ),
            "semantic_event_count": self.semantic_event_count,
        }


def _preflight_artifacts(paths: list[Path]) -> None:
    conflicts = [path for path in paths if path.exists() and path.stat().st_size > 0]
    if conflicts:
        rendered = ", ".join(str(path) for path in conflicts)
        raise FileExistsError(f"ExecWeave record artifacts already exist: {rendered}")


def record_to_viewer(
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
    integrate_semantic: bool = True,
) -> RecordResult:
    """Record one command and materialize a local graph/viewer after it exits."""
    if not command:
        raise ValueError("command must not be empty")

    session_id = uuid4().hex
    root = Path(watch_root).expanduser().resolve()
    run_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else root / ".execweave" / "runs" / session_id
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    event_path = run_dir / "events.jsonl"
    fidelity_path = run_dir / "fidelity.json"
    graph_path = run_dir / "graph.json"
    viewer_path = run_dir / "viewer.html"
    semantic_path = run_dir / "semantic.jsonl"
    merged_event_path = run_dir / "events.semantic.jsonl"
    artifacts = [event_path, fidelity_path, graph_path, viewer_path]
    if integrate_semantic:
        artifacts.extend([semantic_path, merged_event_path])
    _preflight_artifacts(artifacts)

    sink = JsonlSink(event_path)
    resolved = resolve_backend(backend)
    collector = create_collector(
        backend=backend,
        session_id=session_id,
        sink=sink,
        watch_root=root,
        poll_interval=poll_interval,
        collect_filesystem=collect_filesystem,
        collect_network=collect_network,
        keep_raw_trace=keep_raw_trace,
    )

    environment_updates = {
        _RUN_ID_ENV: session_id,
        _SESSION_ID_ENV: session_id,
    }
    if integrate_semantic:
        environment_updates[_SEMANTIC_ENV] = str(semantic_path)
    previous_environment = {
        key: os.environ.get(key) for key in environment_updates
    }
    os.environ.update(environment_updates)
    try:
        return_code = collector.run(command)
    finally:
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    validation = validate_event_stream(event_path)
    if not validation.valid:
        details = "; ".join(validation.errors)
        raise RuntimeError(f"recorded event stream failed validation: {details}")

    materialized_event_path = event_path
    semantic_event_count = 0
    if integrate_semantic and semantic_path.exists() and semantic_path.stat().st_size > 0:
        semantic_merge = merge_semantic_sidecar(
            event_path,
            semantic_path,
            merged_event_path,
        )
        materialized_event_path = merged_event_path
        semantic_event_count = semantic_merge.semantic_event_count

    execution_graph = strip_internal_hook_execution_graph(
        build_execution_graph(materialized_event_path)
    )
    write_fidelity_report(execution_graph.fidelity, fidelity_path)
    write_execution_graph(execution_graph, graph_path)
    write_graph_html(execution_graph.to_dict(), viewer_path, open_browser=False)
    ensure_viewer_theme(viewer_path)
    if open_browser:
        import webbrowser

        webbrowser.open(viewer_path.resolve().as_uri())

    return RecordResult(
        session_id=session_id,
        backend=resolved,
        return_code=return_code,
        output_dir=run_dir,
        event_stream=event_path,
        fidelity=fidelity_path,
        graph=graph_path,
        viewer=viewer_path,
        event_count=execution_graph.event_count,
        node_count=len(execution_graph.nodes),
        edge_count=len(execution_graph.edges),
        semantic_sidecar=semantic_path.resolve() if integrate_semantic else None,
        materialized_event_stream=materialized_event_path.resolve(),
        semantic_event_count=semantic_event_count,
    )

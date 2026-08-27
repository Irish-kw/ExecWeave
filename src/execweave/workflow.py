from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .backends import BackendName, create_collector, resolve_backend
from .fidelity import write_fidelity_report
from .graph import build_execution_graph, write_execution_graph
from .sink import JsonlSink
from .theme import ensure_viewer_theme
from .validate import validate_event_stream
from .viewer_projection import write_graph_html


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
    _preflight_artifacts([event_path, fidelity_path, graph_path, viewer_path])

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

    return_code = collector.run(command)

    validation = validate_event_stream(event_path)
    if not validation.valid:
        details = "; ".join(validation.errors)
        raise RuntimeError(f"recorded event stream failed validation: {details}")

    execution_graph = build_execution_graph(event_path)
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
    )

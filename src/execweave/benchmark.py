from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from .backends import BackendName, create_collector, resolve_backend
from .sink import JsonlSink


def _workload_command() -> list[str]:
    code = (
        "from pathlib import Path; "
        "p=Path('execweave-bench.tmp'); "
        "p.write_text('x'*4096, encoding='utf-8'); "
        "p.read_text(encoding='utf-8'); "
        "p.unlink()"
    )
    return [sys.executable, "-c", code]


def run_benchmark(
    *, backend: BackendName = "auto", iterations: int = 5
) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    resolved = resolve_backend(backend)
    baseline: list[float] = []
    instrumented: list[float] = []
    with tempfile.TemporaryDirectory(prefix="execweave-benchmark-") as temp:
        root = Path(temp)
        command = _workload_command()
        for _ in range(iterations):
            start = time.perf_counter()
            subprocess.run(
                command,
                cwd=root,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            baseline.append(time.perf_counter() - start)
        for _ in range(iterations):
            session_id = uuid4().hex
            sink = JsonlSink(root / ".execweave" / "runs" / f"{session_id}.jsonl")
            collector = create_collector(
                backend=backend,
                session_id=session_id,
                sink=sink,
                watch_root=root,
                poll_interval=0.05,
                collect_filesystem=True,
                collect_network=False,
            )
            start = time.perf_counter()
            rc = collector.run(command)
            if rc != 0:
                raise RuntimeError(f"benchmark workload failed with exit code {rc}")
            instrumented.append(time.perf_counter() - start)
    base_median = statistics.median(baseline)
    instrumented_median = statistics.median(instrumented)
    ratio = instrumented_median / base_median if base_median else None
    return {
        "backend": resolved,
        "iterations": iterations,
        "baseline_seconds": baseline,
        "instrumented_seconds": instrumented,
        "baseline_median_seconds": base_median,
        "instrumented_median_seconds": instrumented_median,
        "overhead_ratio": ratio,
    }


def format_benchmark(result: dict[str, object]) -> str:
    return json.dumps(result, indent=2, sort_keys=True)

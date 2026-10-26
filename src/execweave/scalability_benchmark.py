from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

import psutil

from . import __version__
from .graph import GraphAccumulator

BENCHMARK_SCHEMA_VERSION = "0.1"
DEFAULT_SIZES = (10_000, 100_000, 1_000_000)
DEFAULT_RESOURCES = 10_000


def _synthetic_event(index: int, resource_count: int) -> dict[str, object]:
    resource = index % resource_count
    target_id = f"file:/synthetic/resource-{resource}.txt"
    return {
        "schema_version": "0.2",
        "session_id": "scalability-benchmark",
        "event_id": f"event-{index}",
        "sequence": index + 1,
        "timestamp": "2026-01-01T00:00:00Z",
        "event_type": "filesystem.modified",
        "relation": "OBSERVED_FILE_CHANGE",
        "source": {
            "id": "session:scalability-benchmark",
            "type": "session",
            "name": "scalability-benchmark",
        },
        "target": {
            "id": target_id,
            "type": "file",
            "name": f"resource-{resource}.txt",
        },
        "attributes": {
            "backend": "portable",
            "attribution": "session_observation",
            "causal": False,
        },
    }


def benchmark_point(event_count: int, *, resource_count: int) -> dict[str, object]:
    if event_count <= 0:
        raise ValueError("event_count must be > 0")
    if resource_count <= 0:
        raise ValueError("resource_count must be > 0")

    process = psutil.Process(os.getpid())
    rss_before = process.memory_info().rss
    accumulator = GraphAccumulator(
        session_id="scalability-benchmark",
        source_path=Path("<synthetic>"),
        retain_event_ids=False,
    )

    started = time.perf_counter()
    for index in range(event_count):
        accumulator.apply(_synthetic_event(index, resource_count))
    elapsed = time.perf_counter() - started
    rss_after_apply = process.memory_info().rss

    snapshot_started = time.perf_counter()
    snapshot = accumulator.to_dict()
    snapshot_seconds = time.perf_counter() - snapshot_started
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rss_after_snapshot = process.memory_info().rss

    return {
        "event_count": event_count,
        "resource_count": resource_count,
        "node_count": accumulator.node_count,
        "edge_count": accumulator.edge_count,
        "apply_seconds": elapsed,
        "events_per_second": event_count / elapsed if elapsed else 0.0,
        "snapshot_seconds": snapshot_seconds,
        "snapshot_bytes": len(encoded),
        "rss_before_bytes": rss_before,
        "rss_after_apply_bytes": rss_after_apply,
        "rss_after_snapshot_bytes": rss_after_snapshot,
        "rss_apply_delta_bytes": max(0, rss_after_apply - rss_before),
        "rss_snapshot_delta_bytes": max(0, rss_after_snapshot - rss_after_apply),
        "retained_event_ids": sum(len(edge.event_ids) for edge in accumulator.edges.values()),
    }


def run_scalability_benchmark(
    *,
    sizes: tuple[int, ...] = DEFAULT_SIZES,
    resource_count: int = DEFAULT_RESOURCES,
) -> dict[str, object]:
    if not sizes:
        raise ValueError("at least one size is required")
    normalized = tuple(int(size) for size in sizes)
    if any(size <= 0 for size in normalized):
        raise ValueError("all benchmark sizes must be > 0")
    return {
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "execweave_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "resource_count": resource_count,
        "points": [
            benchmark_point(size, resource_count=resource_count)
            for size in normalized
        ],
    }


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MiB"
    return f"{value / 1024:.1f} KiB"


def format_scalability(result: dict[str, object]) -> str:
    lines = [
        f"ExecWeave {result['execweave_version']} scalability benchmark",
        "events      apply(s)   events/s     nodes    edges    RSS delta   snapshot",
    ]
    for point in result["points"]:
        assert isinstance(point, dict)
        lines.append(
            f"{int(point['event_count']):>10,}  "
            f"{float(point['apply_seconds']):>8.3f}  "
            f"{float(point['events_per_second']):>9,.0f}  "
            f"{int(point['node_count']):>8,}  "
            f"{int(point['edge_count']):>7,}  "
            f"{_format_bytes(int(point['rss_apply_delta_bytes'])):>10}  "
            f"{_format_bytes(int(point['snapshot_bytes'])):>10}"
        )
    return "\n".join(lines)


def _parse_sizes(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sizes must be comma-separated integers") from exc
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("sizes must contain positive integers")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-scalability",
        description="Measure incremental GraphAccumulator scaling without retaining raw event IDs.",
    )
    parser.add_argument(
        "--sizes",
        type=_parse_sizes,
        default=DEFAULT_SIZES,
        help="Comma-separated event counts (default: 10000,100000,1000000)",
    )
    parser.add_argument(
        "--resources",
        type=int,
        default=DEFAULT_RESOURCES,
        help="Unique synthetic file resources (default: 10000)",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_scalability_benchmark(
            sizes=tuple(args.sizes),
            resource_count=args.resources,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(format_scalability(result))
    if args.output_json is not None:
        output = args.output_json.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"JSON: {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import html
import importlib.metadata
import json
import math
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from . import __version__

_SAMPLE_INTERVAL_SECONDS = 0.005
_WORKLOAD_ID = "agent_like_files_and_subprocesses_v1"
_WORKLOAD_CODE = """
from pathlib import Path
import hashlib
import subprocess
import sys

root = Path("payload")
root.mkdir(exist_ok=True)
payload = (b"execweave-reference-workload-" * 2048)[:32768]
for index in range(256):
    path = root / f"file-{index % 16}.bin"
    path.write_bytes(payload)
    hashlib.sha256(path.read_bytes()).digest()
for path in root.iterdir():
    path.unlink()
root.rmdir()
for _ in range(6):
    subprocess.run(
        [sys.executable, "-c", "sum(i*i for i in range(20000))"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
""".strip()


def _workload_command() -> list[str]:
    return [sys.executable, "-c", _WORKLOAD_CODE]


def _tree_rss_bytes(pid: int) -> int:
    try:
        root = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0
    processes = [root]
    try:
        processes.extend(root.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    rss = 0
    for process in processes:
        try:
            rss += process.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rss


def _directory_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


def _measure_command(command: list[str], *, cwd: Path) -> dict[str, float | int]:
    start = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    peak_rss = 0
    while True:
        peak_rss = max(peak_rss, _tree_rss_bytes(process.pid))
        return_code = process.poll()
        if return_code is not None:
            break
        time.sleep(_SAMPLE_INTERVAL_SECONDS)
    elapsed = time.perf_counter() - start
    if return_code != 0:
        raise RuntimeError(f"benchmark command failed with exit code {return_code}")
    return {
        "wall_seconds": elapsed,
        "peak_tree_rss_bytes": peak_rss,
        "artifact_bytes": _directory_size_bytes(cwd),
    }


def _instrumented_command(backend: str, *, cwd: Path, output: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "execweave",
        "run",
        "--backend",
        backend,
        "--watch-root",
        str(cwd),
        "--interval",
        "0.05",
        "--no-network",
        "--output",
        str(output),
        "--",
        *_workload_command(),
    ]


def _run_one(profile: str, *, root: Path, index: str) -> dict[str, float | int]:
    run_dir = root / f"{profile}-{index}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if profile == "off":
        measurement = _measure_command(_workload_command(), cwd=run_dir)
    else:
        output = run_dir / "events.jsonl"
        measurement = _measure_command(
            _instrumented_command(profile, cwd=run_dir, output=output),
            cwd=run_dir,
        )
    measurement["artifact_bytes"] = _directory_size_bytes(run_dir)
    return measurement


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return float(ordered[index])


def _summarize(
    name: str,
    backend: str,
    measurements: list[dict[str, float | int]],
    *,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    walls = [float(item["wall_seconds"]) for item in measurements]
    rss = [float(item["peak_tree_rss_bytes"]) for item in measurements]
    artifacts = [float(item["artifact_bytes"]) for item in measurements]
    wall_median_ms = _median(walls) * 1000.0
    rss_median_mb = _median(rss) / (1024.0 * 1024.0)
    artifact_median_kb = _median(artifacts) / 1024.0
    if baseline is None:
        overhead_percent = 0.0
        rss_delta_mb = 0.0
    else:
        baseline_wall = float(baseline["wall_median_ms"])
        baseline_rss = float(baseline["peak_tree_rss_median_mb"])
        overhead_percent = (
            ((wall_median_ms / baseline_wall) - 1.0) * 100.0 if baseline_wall else 0.0
        )
        rss_delta_mb = rss_median_mb - baseline_rss
    return {
        "name": name,
        "backend": backend,
        "samples": len(measurements),
        "wall_median_ms": round(wall_median_ms, 3),
        "wall_p95_ms": round(_percentile(walls, 0.95) * 1000.0, 3),
        "runtime_overhead_percent": round(overhead_percent, 3),
        "peak_tree_rss_median_mb": round(rss_median_mb, 3),
        "peak_tree_rss_delta_mb": round(rss_delta_mb, 3),
        "additional_peak_rss_mb": round(max(0.0, rss_delta_mb), 3),
        "artifact_median_kb": round(artifact_median_kb, 3),
    }


def _cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine() or "unknown"


def _distribution_size_bytes() -> int | None:
    try:
        distribution = importlib.metadata.distribution("execweave")
    except importlib.metadata.PackageNotFoundError:
        return None
    total = 0
    seen = False
    for relative in distribution.files or []:
        try:
            candidate = Path(distribution.locate_file(relative))
            if candidate.is_file():
                total += candidate.stat().st_size
                seen = True
        except OSError:
            continue
    return total if seen else None


def run_reference_benchmark(*, iterations: int = 7, strace: str = "auto") -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if strace not in {"auto", "on", "off"}:
        raise ValueError("strace must be auto, on, or off")
    strace_available = platform.system() == "Linux" and shutil.which("strace") is not None
    if strace == "on" and not strace_available:
        raise RuntimeError("strace was requested but is unavailable")
    backends = ["portable"]
    if strace_available and strace != "off":
        backends.append("strace")

    with tempfile.TemporaryDirectory(prefix="execweave-reference-benchmark-") as temp:
        root = Path(temp)
        _run_one("off", root=root, index="warmup")
        for backend in backends:
            _run_one(backend, root=root, index="warmup")

        baseline_measurements = [
            _run_one("off", root=root, index=str(index)) for index in range(iterations)
        ]
        baseline = _summarize(
            "ExecWeave OFF",
            "off",
            baseline_measurements,
            baseline=None,
        )
        profiles = [baseline]
        for backend in backends:
            measurements = [
                _run_one(backend, root=root, index=str(index)) for index in range(iterations)
            ]
            profiles.append(
                _summarize(
                    f"{backend.capitalize()} ON",
                    backend,
                    measurements,
                    baseline=baseline,
                )
            )

    distribution_bytes = _distribution_size_bytes()
    return {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "execweave_version": __version__,
        "workload": {
            "id": _WORKLOAD_ID,
            "description": "fixed file read/write/hash operations plus short-lived Python subprocesses",
        },
        "iterations": iterations,
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "cpu_model": _cpu_model(),
            "logical_cpus": psutil.cpu_count(logical=True),
            "memory_total_mb": round(psutil.virtual_memory().total / (1024.0 * 1024.0), 1),
        },
        "package": {
            "distribution_kb": (
                round(distribution_bytes / 1024.0, 3) if distribution_bytes is not None else None
            ),
            "scope": "ExecWeave distribution files only; Python and dependency footprints excluded",
        },
        "profiles": profiles,
        "interpretation": {
            "x": "additional_peak_rss_mb",
            "y": "runtime_overhead_percent",
            "bubble": "artifact_median_kb",
            "preferred_region": "lower-left",
            "warning": "Reference microbenchmark only; rerun on the target host before making capacity claims.",
        },
    }


def _nice_ceiling(value: float, minimum: float) -> float:
    value = max(value, minimum)
    magnitude = 10 ** math.floor(math.log10(value)) if value > 0 else 1
    scaled = value / magnitude
    if scaled <= 1:
        step = 1
    elif scaled <= 2:
        step = 2
    elif scaled <= 5:
        step = 5
    else:
        step = 10
    return step * magnitude


def render_tradeoff_svg(report: dict[str, Any]) -> str:
    profiles = [profile for profile in report.get("profiles", []) if isinstance(profile, dict)]
    x_values = [max(0.0, float(profile.get("additional_peak_rss_mb", 0.0))) for profile in profiles]
    y_values = [float(profile.get("runtime_overhead_percent", 0.0)) for profile in profiles]
    x_max = _nice_ceiling(max(x_values, default=0.0) * 1.25, 8.0)
    y_min = min(0.0, min(y_values, default=0.0) * 1.15)
    y_max = _nice_ceiling(max(y_values, default=0.0) * 1.25, 10.0)
    if y_max <= y_min:
        y_max = y_min + 10.0

    width, height = 980, 640
    left, right, top, bottom = 110, 70, 125, 110
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(value: float) -> float:
        return left + (max(0.0, value) / x_max) * plot_w

    def sy(value: float) -> float:
        return top + ((y_max - value) / (y_max - y_min)) * plot_h

    colors = {"off": "#64748b", "portable": "#2563eb", "strace": "#7c3aed"}
    env = report.get("environment") or {}
    subtitle = f"{env.get('os', 'unknown OS')} · Python {env.get('python', '?')} · n={report.get('iterations', '?')}"
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">ExecWeave runtime overhead versus memory footprint</title>',
        '<desc id="desc">Lower-left is better. Bubble area indicates median artifact size per reference run.</desc>',
        '<rect width="100%" height="100%" rx="24" fill="#ffffff"/>',
        '<text x="70" y="54" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="28" font-weight="700" fill="#0f172a">ExecWeave overhead trade-off</text>',
        f'<text x="70" y="83" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="14" fill="#64748b">{html.escape(subtitle)}</text>',
        '<text x="910" y="54" text-anchor="end" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="13" font-weight="600" fill="#16a34a">LOWER-LEFT IS BETTER ↙</text>',
    ]

    for index in range(6):
        fraction = index / 5
        x = left + fraction * plot_w
        value = fraction * x_max
        lines.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" stroke="#e2e8f0" stroke-width="1"/>')
        lines.append(f'<text x="{x:.1f}" y="{top + plot_h + 28}" text-anchor="middle" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#64748b">{value:.0f}</text>')
    for index in range(6):
        fraction = index / 5
        y = top + fraction * plot_h
        value = y_max - fraction * (y_max - y_min)
        lines.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        lines.append(f'<text x="{left - 18}" y="{y + 4:.1f}" text-anchor="end" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12" fill="#64748b">{value:.0f}</text>')

    lines.extend(
        [
            f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#334155" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#334155" stroke-width="1.5"/>',
            f'<text x="{left + plot_w / 2:.1f}" y="{height - 45}" text-anchor="middle" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="15" font-weight="600" fill="#334155">Additional peak process-tree RSS (MB) → higher</text>',
            f'<text x="32" y="{top + plot_h / 2:.1f}" transform="rotate(-90 32 {top + plot_h / 2:.1f})" text-anchor="middle" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="15" font-weight="600" fill="#334155">Runtime overhead (%) → higher</text>',
        ]
    )

    for profile in profiles:
        backend = str(profile.get("backend", "unknown"))
        x_value = max(0.0, float(profile.get("additional_peak_rss_mb", 0.0)))
        y_value = float(profile.get("runtime_overhead_percent", 0.0))
        artifact = max(0.0, float(profile.get("artifact_median_kb", 0.0)))
        radius = 8.0 if backend == "off" else min(28.0, 10.0 + math.sqrt(artifact) * 0.9)
        x, y = sx(x_value), sy(y_value)
        color = colors.get(backend, "#0f766e")
        name = html.escape(str(profile.get("name", backend)))
        detail = html.escape(f"+{x_value:.1f} MB RSS · {y_value:+.1f}% time · {artifact:.1f} KB/run")
        label_x = x + 16
        label_y = y - radius - 8
        if backend == "off":
            label_y = y - 18
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" fill-opacity="0.88" stroke="#ffffff" stroke-width="3"/>')
        lines.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="14" font-weight="700" fill="#0f172a">{name}</text>')
        lines.append(f'<text x="{label_x:.1f}" y="{label_y + 19:.1f}" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#64748b">{detail}</text>')

    package = report.get("package") or {}
    package_kb = package.get("distribution_kb")
    package_text = f"Package footprint: {package_kb:.1f} KB (ExecWeave files only)" if isinstance(package_kb, (int, float)) else "Package footprint unavailable"
    lines.extend(
        [
            f'<text x="{left}" y="{height - 18}" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="11" fill="#94a3b8">Bubble area ≈ median residual artifact size per run · {html.escape(package_text)}</text>',
            '</svg>',
        ]
    )
    return "\n".join(lines) + "\n"


def _write_text(path: Path, content: str) -> Path:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-overhead",
        description="Measure ExecWeave runtime overhead and render a reproducible trade-off chart.",
    )
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--strace", choices=["auto", "on", "off"], default="auto")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-svg", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = run_reference_benchmark(iterations=args.iterations, strace=args.strace)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    print("EXECWEAVE_BENCHMARK_RESULT=" + json.dumps(report, sort_keys=True, separators=(",", ":")))
    if args.output_json is not None:
        _write_text(args.output_json, rendered + "\n")
    if args.output_svg is not None:
        _write_text(args.output_svg, render_tradeoff_svg(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

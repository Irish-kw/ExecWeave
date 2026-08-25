from execweave.overhead_benchmark import _summarize, render_tradeoff_svg


def test_overhead_summary_uses_baseline_for_time_and_rss_delta() -> None:
    baseline_measurements = [
        {"wall_seconds": 1.0, "peak_tree_rss_bytes": 100 * 1024 * 1024, "artifact_bytes": 0},
        {"wall_seconds": 1.2, "peak_tree_rss_bytes": 104 * 1024 * 1024, "artifact_bytes": 0},
        {"wall_seconds": 0.8, "peak_tree_rss_bytes": 96 * 1024 * 1024, "artifact_bytes": 0},
    ]
    baseline = _summarize("ExecWeave OFF", "off", baseline_measurements, baseline=None)
    instrumented = _summarize(
        "Portable ON",
        "portable",
        [
            {
                "wall_seconds": 1.1,
                "peak_tree_rss_bytes": 112 * 1024 * 1024,
                "artifact_bytes": 8 * 1024,
            },
            {
                "wall_seconds": 1.3,
                "peak_tree_rss_bytes": 114 * 1024 * 1024,
                "artifact_bytes": 10 * 1024,
            },
            {
                "wall_seconds": 1.2,
                "peak_tree_rss_bytes": 110 * 1024 * 1024,
                "artifact_bytes": 9 * 1024,
            },
        ],
        baseline=baseline,
    )

    assert baseline["wall_median_ms"] == 1000.0
    assert baseline["runtime_overhead_percent"] == 0.0
    assert instrumented["wall_median_ms"] == 1200.0
    assert instrumented["runtime_overhead_percent"] == 20.0
    assert instrumented["peak_tree_rss_delta_mb"] == 12.0
    assert instrumented["additional_peak_rss_mb"] == 12.0
    assert instrumented["artifact_median_kb"] == 9.0


def test_tradeoff_svg_is_self_contained_and_labels_evidence_dimensions() -> None:
    report = {
        "iterations": 7,
        "environment": {"os": "TestOS", "python": "3.12"},
        "package": {"distribution_kb": 420.0},
        "profiles": [
            {
                "name": "ExecWeave OFF",
                "backend": "off",
                "runtime_overhead_percent": 0.0,
                "additional_peak_rss_mb": 0.0,
                "artifact_median_kb": 0.0,
            },
            {
                "name": "Portable ON",
                "backend": "portable",
                "runtime_overhead_percent": 8.5,
                "additional_peak_rss_mb": 16.2,
                "artifact_median_kb": 24.0,
            },
            {
                "name": "Strace ON",
                "backend": "strace",
                "runtime_overhead_percent": 31.0,
                "additional_peak_rss_mb": 11.0,
                "artifact_median_kb": 90.0,
            },
        ],
    }

    svg = render_tradeoff_svg(report)

    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert "ExecWeave overhead trade-off" in svg
    assert "LOWER-LEFT IS BETTER" in svg
    assert "Additional peak process-tree RSS (MB)" in svg
    assert "Runtime overhead (%)" in svg
    assert "Bubble area" in svg
    assert "Portable ON" in svg
    assert "Strace ON" in svg
    assert "Package footprint: 420.0 KB" in svg
    assert "<script" not in svg

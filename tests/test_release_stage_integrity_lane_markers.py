"""The capture-marker guard exempts eBPF and ptrace in the lane backend only.

The lane backend is a root-only, opt-in backend built on an eBPF sensor, and it names
ptrace where Landlock scoping refuses it. These tests pin how narrow the exemption is:
the two markers pass inside src/execweave/lane/, the same markers anywhere else in the
package are still reported, and every other marker is still reported inside the lane
package too.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "release_integrity_lane_markers", ROOT / "scripts" / "_check_release_stage_integrity_impl.py"
)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(checker)


@pytest.mark.parametrize("marker", ["ebpf", "ptrace"])
def test_lane_backend_markers_pass_inside_the_lane_package(marker: str) -> None:
    sites = checker._marker_sites({"src/execweave/lane/service.py": f"# uses {marker}\n"})
    assert sites == set()


@pytest.mark.parametrize("marker", ["ebpf", "ptrace"])
def test_lane_backend_markers_are_still_refused_elsewhere(marker: str) -> None:
    sites = checker._marker_sites({"src/execweave/cli.py": f"# uses {marker}\n"})
    assert sites == {f"src/execweave/cli.py: {marker}"}


def test_a_lookalike_directory_gets_no_exemption() -> None:
    sites = checker._marker_sites({"src/execweave/lane_extra/x.py": "ebpf\n", "src/execweave/lanes.py": "ptrace\n"})
    assert sites == {"src/execweave/lane_extra/x.py: ebpf", "src/execweave/lanes.py: ptrace"}


@pytest.mark.parametrize(
    "marker",
    sorted(set(checker.FORBIDDEN_CAPTURE_MARKERS + checker.TLS_MITM_MARKERS) - checker.LANE_BACKEND_MARKERS),
)
def test_every_other_marker_is_refused_inside_the_lane_package(marker: str) -> None:
    sites = checker._marker_sites({"src/execweave/lane/runner.py": f"x = {marker}\n"})
    assert sites == {f"src/execweave/lane/runner.py: {marker}"}

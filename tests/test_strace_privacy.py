"""Independent opt-in native strace privacy tests (do not edit existing test gate files)."""

import shutil
from pathlib import Path

import pytest

from execweave.sink import JsonlSink
from execweave.strace_backend import StraceRuntimeCollector


def test_native_trace_directory_is_private_and_git_ignored_with_custom_output(
    tmp_path: Path,
) -> None:
    """A custom graph output cannot leave kept raw execve argv stageable."""
    import os
    import stat
    import subprocess

    project = tmp_path / "project"
    project.mkdir()
    assert shutil.which("git") is not None, (
        "git is required to verify that private raw trace evidence cannot be staged"
    )
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    # Intentionally put graph output OUTSIDE the default .execweave run tree.
    output = project / "out_keep" / "events.jsonl"
    trace_dir = project / ".execweave" / "traces" / "s-custom"
    collector = StraceRuntimeCollector(
        session_id="s-custom",
        sink=JsonlSink(output),
        watch_root=project,
        trace_root=trace_dir,
        keep_raw_trace=True,
    )
    collector._prepare_trace_directory()
    assert (project / ".execweave" / ".gitignore").read_bytes() == b"*\n"
    assert (trace_dir / ".gitignore").read_bytes() == b"*\n"
    if os.name != "nt":
        assert stat.S_IMODE(trace_dir.stat().st_mode) == 0o700
    # Mimic a native trace containing full argv; ordinary git add must not stage it.
    marker = trace_dir / "trace.1234"
    marker.write_text('execve("python", ["python", "--token", "ARGV-SECRET"], [])',
                      encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    staged = subprocess.run(
        ["git", "ls-files"], cwd=project, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    assert not any(line.endswith("trace.1234") for line in staged)
    assert not any(line.startswith(".execweave/traces/") and
                   not line.endswith("/.gitignore") for line in staged)
    assert "out_keep/events.jsonl" not in staged


def test_native_trace_with_existing_unsafe_gitignore_fails_closed(tmp_path: Path) -> None:
    trace_dir = tmp_path / ".execweave" / "traces" / "s"
    trace_dir.mkdir(parents=True)
    (trace_dir / ".gitignore").write_text("# does not ignore argv traces\n")
    collector = StraceRuntimeCollector(
        session_id="s",
        sink=JsonlSink(tmp_path / "custom-output" / "events.jsonl"),
        watch_root=tmp_path,
        trace_root=trace_dir,
        keep_raw_trace=True,
    )
    with pytest.raises(ValueError, match="must ignore all raw traces"):
        collector._prepare_trace_directory()

"""`live` and `top` record full provider/model content unless the user opts out.

ExecWeave runs on the user's own machine so the user can inspect what an agent
did; prompts and responses are the detail they came for. `--metadata-only` is the
opt-out, `--capture-content` stays accepted, and the two cannot be combined.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

from execweave import cli, entry, top_cli
from execweave.live import run_live
from execweave.top import run_top


def _live_args(*flags: str):
    return cli.build_parser().parse_args(["live", *flags, "--", sys.executable, "-c", "pass"])


def _top_args(*flags: str):
    return top_cli.build_parser().parse_args([*flags, "--", sys.executable, "-c", "pass"])


@pytest.mark.parametrize("parse", [_live_args, _top_args], ids=["live", "top"])
def test_parser_defaults_to_full_content_capture(parse) -> None:
    assert parse().content_capture == "full"
    assert parse("--capture-content").content_capture == "full"
    assert parse("--metadata-only").content_capture == "metadata_only"


@pytest.mark.parametrize("parse", [_live_args, _top_args], ids=["live", "top"])
def test_capture_flags_are_mutually_exclusive(parse, capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        parse("--capture-content", "--metadata-only")
    assert raised.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_entry_finds_the_command_after_the_metadata_only_flag() -> None:
    assert entry._live_command(["live", "--metadata-only", "--open", "python", "a.py"]) == [
        "python",
        "a.py",
    ]
    assert entry._live_command(["live", "--capture-content", "python", "a.py"]) == [
        "python",
        "a.py",
    ]


def test_run_live_and_run_top_default_to_full_capture() -> None:
    for function in (run_live, run_top):
        default = inspect.signature(function).parameters["content_capture"].default
        assert default == "full", function.__name__


def test_default_live_run_stamps_explicit_full_policy(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    result = run_live(
        [sys.executable, "-c", "pass"],
        watch_root=work,
        output_dir=tmp_path / "out",
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
        linger_seconds=0,
    )
    started = next(
        row
        for row in (
            json.loads(line)
            for line in Path(result.event_stream).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if row["event_type"] == "session.started"
    )
    assert started["attributes"]["content_capture_mode"] == "full"
    assert started["attributes"]["content_capture_policy_state"] == "explicit_full"

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from execweave import codex_rollout_trace
from execweave.codex_record import _codex_reducer_command_prefix


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["codex", "--model", "gpt-5.6-codex"], ["codex"]),
        (["/opt/bin/codex", "exec", "task"], ["/opt/bin/codex"]),
        (["npx", "codex", "--model", "gpt-5.6-codex"], ["npx", "codex"]),
        (
            ["npx", "-y", "@openai/codex@latest", "--model", "gpt-5.6-codex"],
            ["npx", "-y", "@openai/codex@latest"],
        ),
        (
            ["npm", "exec", "--", "@openai/codex", "--model", "gpt-5.6-codex"],
            ["npm", "exec", "--", "@openai/codex"],
        ),
        (
            ["pnpm", "dlx", "@openai/codex", "--model", "gpt-5.6-codex"],
            ["pnpm", "dlx", "@openai/codex"],
        ),
        (
            ["bunx", "@openai/codex", "--model", "gpt-5.6-codex"],
            ["bunx", "@openai/codex"],
        ),
        (
            ["custom-codex-wrapper", "--model", "gpt-5.6-codex"],
            ["custom-codex-wrapper"],
        ),
    ],
)
def test_codex_reducer_prefix_preserves_only_recognized_launch_wrapper(
    command: list[str],
    expected: list[str],
) -> None:
    assert _codex_reducer_command_prefix(command) == expected


def test_rollout_reducer_executes_full_command_prefix(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "trace-bundle"
    bundle.mkdir()
    state_path = bundle / "state.json"
    seen: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        state_path.write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(codex_rollout_trace.subprocess, "run", fake_run)

    error = codex_rollout_trace._reduce_bundle(
        ["npx", "-y", "@openai/codex@latest"],
        bundle,
        state_path,
    )

    assert error is None
    assert seen["argv"] == [
        "npx",
        "-y",
        "@openai/codex@latest",
        "debug",
        "trace-reduce",
        str(bundle),
        "--output",
        str(state_path),
    ]
    assert seen["kwargs"] == {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 60,
    }

"""A release branch may move the version; a stage still may not.

The guard used to refuse every version move, so the one branch whose job is the
release could not pass it and was pushed straight to the default branch instead.
These tests pin both halves of the replacement: a branch that changes only release
metadata is allowed to move the version, and a branch that touches anything else is
refused and told which files disqualified it.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_release_stage_integrity", ROOT / "scripts" / "check_release_stage_integrity.py"
)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(checker)


RELEASE_ONLY_BRANCH = [
    "pyproject.toml",
    "src/execweave/__init__.py",
    "tests/test_v069_dashboard_release.py",
    ".github/workflows/provider-capability-stage-integrity.yml",
    "README.md",
    "README.zh-TW.md",
    "README.ru.md",
]


def test_a_branch_of_only_release_metadata_has_no_offenders() -> None:
    assert checker._release_only_offenders(RELEASE_ONLY_BRANCH) == []


def test_a_source_or_test_change_makes_the_branch_a_stage() -> None:
    offenders = checker._release_only_offenders(
        [
            *RELEASE_ONLY_BRANCH,
            "src/execweave/viewer_agent_panel.py",
            "tests/test_dashboard_simplification.py",
        ]
    )
    assert offenders == [
        "src/execweave/viewer_agent_panel.py",
        "tests/test_dashboard_simplification.py",
    ]


def test_a_documentation_page_is_not_release_metadata() -> None:
    """Only the READMEs carry the release line; docs/ pages are ordinary content."""
    assert checker._release_only_offenders(["docs/live-graph.md"]) == ["docs/live-graph.md"]


def _fake_git(monkeypatch: pytest.MonkeyPatch, *, changed: list[str], version: str) -> None:
    """Answer the guard's two git questions without inventing a repository."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src" / "execweave" / "__init__.py").read_text(encoding="utf-8")
    current_version = checker.RELEASE_METADATA[0][1].search(pyproject).group(1)
    baseline = {
        "pyproject.toml": pyproject.replace(
            f'version = "{current_version}"', f'version = "{version}"'
        ),
        "src/execweave/__init__.py": init.replace(
            f'__version__ = "{current_version}"', f'__version__ = "{version}"'
        ),
    }

    def fake(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        if args[0] == "diff":
            stdout = "\n".join(changed) + "\n"
        else:
            stdout = baseline[args[-1].split(":", 1)[1]]
        return subprocess.CompletedProcess(list(args), 0, stdout, "")

    monkeypatch.setattr(checker, "_git", fake)


def test_the_guard_allows_the_move_on_a_release_only_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_git(monkeypatch, changed=RELEASE_ONLY_BRANCH, version="0.0.1")
    assert "0.0.1 ->" in checker._assert_release_metadata_unchanged("baseline")


def test_the_guard_refuses_the_move_when_a_stage_carries_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_git(
        monkeypatch,
        changed=[*RELEASE_ONLY_BRANCH, "src/execweave/live.py"],
        version="0.0.1",
    )
    with pytest.raises(RuntimeError) as caught:
        checker._assert_release_metadata_unchanged("baseline")
    assert "src/execweave/live.py" in str(caught.value)
    assert "a stage lands before its release" in str(caught.value).lower()


def test_a_branch_that_moves_nothing_reports_the_version_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = checker.RELEASE_METADATA[0][1].search(pyproject).group(1)
    _fake_git(monkeypatch, changed=["src/execweave/live.py"], version=version)
    assert checker._assert_release_metadata_unchanged("baseline") == "held"

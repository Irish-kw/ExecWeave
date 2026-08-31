"""The fold budget is a setting a run chooses, not a constant baked into the page.

Twelve was a starting point with no measurement behind it. A deployment whose agents
write hundreds of files needs a different number, and nobody should have to edit the
package to get one.
"""

from __future__ import annotations

import argparse

import pytest

from execweave import cli, top_cli, view_cli
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.live_core import _live_page
from execweave.viewer_dashboard_clean import (
    DEFAULT_FOLD_BUDGET,
    FOLD_BUDGET_ENV,
    apply_fold_budget,
    fold_budget_bootstrap,
    fold_budget_option,
    resolve_fold_budget,
)


def test_an_unset_budget_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FOLD_BUDGET_ENV, raising=False)
    assert resolve_fold_budget() == DEFAULT_FOLD_BUDGET


def test_the_run_budget_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FOLD_BUDGET_ENV, "50")
    assert resolve_fold_budget() == 50


@pytest.mark.parametrize("value", ["", "  ", "many", "12.5", "0", "-3"])
def test_an_unusable_environment_value_falls_back_rather_than_losing_the_viewer(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Rendering often happens at the end of a long run; it must not fail there.

    The command line refuses a bad value where the user can see it, which is the
    place to refuse it.
    """
    monkeypatch.setenv(FOLD_BUDGET_ENV, value)
    assert resolve_fold_budget() == DEFAULT_FOLD_BUDGET


@pytest.mark.parametrize("value", ["many", "12.5", "0", "-3"])
def test_the_command_line_refuses_a_value_the_reader_would_not_understand(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        fold_budget_option(value)


def test_the_command_line_accepts_a_whole_number(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FOLD_BUDGET_ENV, raising=False)
    apply_fold_budget(fold_budget_option(" 50 "))
    assert resolve_fold_budget() == 50


def test_omitting_the_flag_leaves_the_environment_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FOLD_BUDGET_ENV, "7")
    apply_fold_budget(None)
    assert resolve_fold_budget() == 7


@pytest.mark.parametrize(
    ("parser", "argv"),
    [
        (cli.build_parser(), ["live", "--fold-budget", "50", "--", "codex"]),
        (cli.build_parser(), ["record", "--fold-budget", "50", "--", "codex"]),
        (cli.build_parser(), ["view", "graph.json", "--fold-budget", "50"]),
        (view_cli.build_parser(), ["graph.json", "--fold-budget", "50"]),
        (top_cli.build_parser(), ["--fold-budget", "50", "--", "codex"]),
    ],
)
def test_every_command_that_renders_a_dashboard_offers_the_budget(
    parser: argparse.ArgumentParser, argv: list[str]
) -> None:
    assert parser.parse_args(argv).fold_budget == 50


def test_a_bad_value_on_the_command_line_exits_rather_than_rendering(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["live", "--fold-budget", "0", "--", "codex"])
    assert "at least 1" in capsys.readouterr().err


def test_the_static_page_carries_the_budget_the_run_chose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(FOLD_BUDGET_ENV, "50")
    html = render_static_dashboard_html({"nodes": [], "edges": []})
    assert "window.__execweaveFoldBudget=50;" in html


def test_the_live_page_carries_the_budget_the_run_chose() -> None:
    """The shell is a module constant, so the budget is spliced in when it is served."""
    page = _live_page("<html><head></head><body><script>x</script></body></html>", 50)
    assert "window.__execweaveFoldBudget=50;" in page
    assert page.index("__execweaveFoldBudget") < page.index("<script>x</script>")


def test_the_page_declares_a_whole_number() -> None:
    assert fold_budget_bootstrap(50) == "window.__execweaveFoldBudget=50;"

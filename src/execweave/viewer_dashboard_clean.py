from __future__ import annotations

import argparse
import os

# How many nodes of one foldable type stay drawn before the older ones collapse.
# Twelve is a starting point, not a measurement: the runs this was built against
# touch a handful of files. A deployment that writes hundreds will want its own
# number, so the value is a setting rather than a constant.
DEFAULT_FOLD_BUDGET = 12
FOLD_BUDGET_ENV = "EXECWEAVE_FOLD_BUDGET"


def resolve_fold_budget(raw: str | None = None) -> int:
    """Read the budget a run was started with, falling back to the default.

    The command line validates its own value and refuses a bad one there, where the
    user can see it. This function is called while rendering, often at the end of a
    long run, so an unusable environment value falls back rather than costing the
    reader the viewer.
    """
    value = os.environ.get(FOLD_BUDGET_ENV) if raw is None else raw
    if value is None:
        return DEFAULT_FOLD_BUDGET
    try:
        budget = int(str(value).strip())
    except ValueError:
        return DEFAULT_FOLD_BUDGET
    return budget if budget >= 1 else DEFAULT_FOLD_BUDGET


def fold_budget_option(value: str) -> int:
    """Parse --fold-budget, refusing a value the reader would not understand."""
    try:
        budget = int(str(value).strip())
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"fold budget must be a whole number, not {value!r}"
        ) from None
    if budget < 1:
        raise argparse.ArgumentTypeError(
            f"fold budget must be at least 1, not {budget}; a large value effectively "
            "turns folding off"
        )
    return budget


def add_fold_budget_argument(parser: argparse.ArgumentParser) -> None:
    """Offer the budget on any command that renders a dashboard."""
    parser.add_argument(
        "--fold-budget",
        type=fold_budget_option,
        default=None,
        metavar="N",
        help=(
            "How many nodes of one crowded type stay drawn before the older ones "
            f"collapse into a single node that still lists them (default: "
            f"{DEFAULT_FOLD_BUDGET}). Set it high to effectively turn folding off. "
            f"Also readable from {FOLD_BUDGET_ENV}."
        ),
    )


def apply_fold_budget(budget: int | None) -> None:
    """Publish the chosen budget so every renderer in this run agrees on it.

    The value travels in the environment rather than through each render call: a run
    resolves one budget, the renderers are reached from several entry points, and top
    launches the live server as a child process that has to agree with its parent.
    """
    if budget is not None:
        os.environ[FOLD_BUDGET_ENV] = str(int(budget))


def fold_budget_bootstrap(budget: int | None = None) -> str:
    """The one statement a rendered page needs so its fold budget is the run's."""
    resolved = resolve_fold_budget() if budget is None else budget
    return f"window.__execweaveFoldBudget={int(resolved)};"

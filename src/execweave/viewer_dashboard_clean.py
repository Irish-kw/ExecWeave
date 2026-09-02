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

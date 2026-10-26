"""Finalizers must not bypass the owned tracker's creation-time check."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/owned_cleanup_acceptance.py",
        "tests/test_acceptance_owned_processes.py",
    ],
)
def test_cleanup_finalizers_do_not_reacquire_bare_child_pid(relative):
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / relative).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for statement in node.finalbody:
            for call in ast.walk(statement):
                if not isinstance(call, ast.Call):
                    continue
                assert not (
                    isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "psutil"
                    and call.func.attr == "Process"
                ), f"{relative}: finally reacquires a PID without its saved creation time"

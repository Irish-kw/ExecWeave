"""The observation-stage allowance cannot authorize an unreviewed test change."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "observation_migrations", ROOT / "scripts/_observation_test_change_allowances.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def test_only_named_branch_receives_allowances(tmp_path):
    assert guard.allowance_args(tmp_path, baseline_ref=guard.BASELINE, head_ref="main") == []


def test_changed_baseline_cannot_reuse_approval():
    with pytest.raises(RuntimeError, match="exact reviewed baseline"):
        guard.allowance_args(ROOT, baseline_ref="another-commit", head_ref=guard.BRANCH)


def test_reviewed_postimages_have_explicit_reasons():
    args = guard.allowance_args(ROOT, baseline_ref=guard.BASELINE, head_ref=guard.BRANCH)
    assert args[::2] == ["--allow-test-change"] * 10
    assert {value.split("=", 1)[0] for value in args[1::2]} == set(guard.CHANGES)
    assert all(len(value.split("=", 1)[1]) > 80 for value in args[1::2])


@pytest.mark.parametrize("changed", sorted(guard.CHANGES))
def test_any_additional_test_edit_is_rejected(tmp_path, changed):
    for name in guard.CHANGES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    path = tmp_path / changed
    path.write_bytes(path.read_bytes() + b"\n# unreviewed change\n")
    with pytest.raises(RuntimeError, match="unreviewed test postimage"):
        guard.allowance_args(tmp_path, baseline_ref=guard.BASELINE, head_ref=guard.BRANCH)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(RuntimeError, match="missing or linked"):
        guard.allowance_args(tmp_path, baseline_ref=guard.BASELINE, head_ref=guard.BRANCH)

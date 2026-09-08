"""Exercise real Git merges and reject stale/unrelated/conflicting RC inputs."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('combined_checkout', ROOT/'scripts/prepare_combined_acceptance.py')
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def history(tmp_path):
    repo = tmp_path/'source'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo, text=True, encoding='utf-8',
                                       stderr=subprocess.PIPE).strip()
    git('init')
    git('config', 'user.name', 'RC test')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'commit.gpgsign', 'false')
    def commit(filename, text):
        (repo/filename).write_text(text, encoding='utf-8')
        git('add', filename)
        git('commit', '-m', filename)
        return git('rev-parse', 'HEAD')
    base = commit('shared.txt', 'original\n')
    first = commit('first.txt', 'GIF\n')
    git('checkout', '--detach', base)
    second = commit('second.txt', 'layout\n')
    return repo, git, commit, base, first, second


def test_both_orders_produce_real_clean_identical_combined_tree(tmp_path):
    repo, git, _, base, first, second = history(tmp_path)
    refs = git('show-ref')
    result = MODULE.prepare(repo, base, first, second, tmp_path/'combined')
    assert result['merge_order_equal'] and result['source_clean']
    assert result['remote_refs_modified'] is False
    assert result['order_69_70_tree'] == result['order_70_69_tree']
    out = tmp_path/'combined'
    assert (out/'first.txt').read_text() == 'GIF\n'
    assert (out/'second.txt').read_text() == 'layout\n'
    assert git('show-ref') == refs
    assert git('rev-parse', 'HEAD') == second  # Original checkout is untouched.
    assert MODULE.git(out, 'status', '--porcelain') == ''
    assert MODULE.git(out, 'rev-parse', 'HEAD^{tree}') == result['combined_tree']


def test_conflicting_product_changes_are_not_auto_resolved(tmp_path):
    repo, git, commit, base, first, _ = history(tmp_path)
    a = commit('shared.txt', 'left\n')
    git('checkout', '--detach', first)
    b = commit('shared.txt', 'right\n')
    with pytest.raises(subprocess.CalledProcessError):
        MODULE.prepare(repo, base, a, b, tmp_path/'combined')
    assert not (tmp_path/'combined').exists()


def test_main_advanced_beyond_a_tip_is_rejected(tmp_path):
    repo, _, commit, _, first, second = history(tmp_path)
    newer_main = commit('new-main.txt', 'new baseline\n')
    with pytest.raises(subprocess.CalledProcessError):
        MODULE.prepare(repo, newer_main, first, second, tmp_path/'combined')
    assert not (tmp_path/'combined').exists()


@pytest.mark.parametrize('invalid', ['HEAD', '--help', 'abcd', 'z'*40])
def test_unpinned_or_option_like_revision_is_rejected(tmp_path, invalid):
    repo, _, _, base, first, _ = history(tmp_path)
    with pytest.raises(ValueError, match='exact 40-character'):
        MODULE.prepare(repo, base, first, invalid, tmp_path/'combined')


def test_existing_directory_is_never_removed_or_overwritten(tmp_path):
    repo, _, _, base, first, second = history(tmp_path)
    out = tmp_path/'combined'
    out.mkdir()
    (out/'keep.txt').write_text('existing user data')
    with pytest.raises(ValueError, match='never removed'):
        MODULE.prepare(repo, base, first, second, out)
    assert (out/'keep.txt').read_text() == 'existing user data'

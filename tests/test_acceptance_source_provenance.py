from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('acceptance_source_provenance', ROOT / 'scripts/acceptance_source_provenance.py')
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample_repo(tmp_path: Path):
    def git(*args):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init')
    git('config', 'user.name', 'Acceptance fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    (tmp_path / 'source.py').write_bytes(b'VALUE = 1\n')
    git('add', 'source.py')
    git('commit', '-m', 'fixture baseline')
    return tmp_path


def test_manifest_proves_git_and_actual_checkout_bytes(tmp_path):
    repo = sample_repo(tmp_path)
    result = module.capture(repo)
    assert len(result['commit']) == len(result['tree']) == 40
    assert result['tracked_files']['source.py']['sha256'] == hashlib.sha256(b'VALUE = 1\n').hexdigest()
    assert result == module.capture(repo)


def test_changed_tracked_source_is_not_accepted(tmp_path):
    repo = sample_repo(tmp_path)
    module.capture(repo)
    (repo / 'source.py').write_bytes(b'VALUE = 2\n')
    with pytest.raises(AssertionError, match='dirty'):
        module.capture(repo)


def test_missing_tracked_source_is_not_accepted(tmp_path):
    repo = sample_repo(tmp_path)
    (repo / 'source.py').unlink()
    with pytest.raises(FileNotFoundError):
        module.capture(repo)


def test_untracked_test_artifact_does_not_change_source_identity(tmp_path):
    repo = sample_repo(tmp_path)
    before = module.capture(repo)
    (repo / 'result.json').write_text('{}')
    assert module.capture(repo) == before

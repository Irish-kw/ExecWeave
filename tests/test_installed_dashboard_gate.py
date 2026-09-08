"""Adversarial checks of installed-artifact provenance, not source-string tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = load('check_installed_dashboard')
PROBE = load('installed_dashboard_probe')


def synthetic_wheel(tmp: Path, *, missing: str = '', altered: str = '') -> Path:
    """Package actual source bytes without invoking a build backend/network."""
    wheel = tmp / 'execweave-0.8.16-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        for source in (ROOT / 'src/execweave').rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts:
                continue
            relative = source.relative_to(ROOT / 'src').as_posix()
            if relative.removeprefix('execweave/') == missing:
                continue
            data = source.read_bytes()
            if relative.removeprefix('execweave/') == altered:
                data += b'\n# altered wheel\n'
            archive.writestr(relative, data)
        archive.writestr('execweave-0.8.16.dist-info/METADATA', 'Metadata-Version: 2.1\nName: execweave\nVersion: 0.8.16\n')
    return wheel


def test_matching_package_has_full_byte_and_dashboard_provenance(tmp_path):
    result = GATE.manifest(ROOT, synthetic_wheel(tmp_path), tmp_path)
    assert result['package_files']['vendor/dagre.min.js'] == GATE.sha256(
        (ROOT / 'src/execweave/vendor/dagre.min.js').read_bytes())
    assert len(result['package_files']) > 100
    assert len(result['dashboard_sha256']) == len(result['static_sha256']) == 64
    assert len(result['source_sha']) == len(result['source_tree']) == 40
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize('missing', ['vendor/dagre.min.js', 'viewer_gif.py', 'live_view_process_layout.py'])
def test_missing_packaged_browser_asset_is_a_hard_failure(tmp_path, missing):
    with pytest.raises(AssertionError, match='omits assets'):
        GATE.manifest(ROOT, synthetic_wheel(tmp_path, missing=missing), tmp_path)


def test_modified_package_bytes_are_not_accepted_as_source_parity(tmp_path):
    with pytest.raises(AssertionError, match='differs from source'):
        GATE.manifest(ROOT, synthetic_wheel(tmp_path, altered='viewer_gif.py'), tmp_path)


def test_direct_checkout_import_cannot_pass_clean_venv_proof(tmp_path, monkeypatch):
    import execweave
    assert Path(execweave.__file__).resolve().is_relative_to(ROOT)
    monkeypatch.setattr(PROBE.sysconfig, 'get_paths', lambda: {'purelib': str(tmp_path / 'venv/site-packages')})
    with pytest.raises(AssertionError):
        PROBE.prove_install({'source_root': str(ROOT)}, tmp_path)


def test_source_path_contamination_rejected_even_if_module_looks_installed(tmp_path, monkeypatch):
    import execweave
    pure = tmp_path / 'site-packages'
    monkeypatch.setattr(execweave, '__file__', str(pure / 'execweave/__init__.py'))
    monkeypatch.setattr(PROBE.sysconfig, 'get_paths', lambda: {'purelib': str(pure)})
    monkeypatch.setattr(sys, 'prefix', str(tmp_path / 'venv'))
    monkeypatch.setattr(sys, 'path', [str(ROOT / 'src')])
    with pytest.raises(AssertionError):
        PROBE.prove_install({'source_root': str(ROOT)}, tmp_path)

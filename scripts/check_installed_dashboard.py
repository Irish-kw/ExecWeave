"""Clean wheel -> genuine browser acceptance; no checkout imports in the worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from email.parser import BytesParser
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture() -> dict:
    nodes = [{'id': 'agent:root', 'name': '/root', 'type': 'agent',
              'attributes': {'agent_path': '/root', 'agent_role': 'root'}}]
    edges = []
    for i in range(6):
        identity = f'file:{i}'
        nodes.append({'id': identity, 'type': 'file', 'name': f'wheel-{i}.txt',
                      'attributes': {'path': f'/fixture/wheel-{i}.txt'}})
        edges.append({'id': f'write:{i}', 'source': 'agent:root', 'target': identity,
                      'relation': 'WROTE', 'first_sequence': i+1})
    return {'session_id': 'installed-wheel-fixture', 'nodes': nodes, 'edges': edges,
            'node_count': len(nodes), 'edge_count': len(edges), 'event_count': len(edges)}


def manifest(repo: Path, wheel: Path, out: Path) -> dict:
    state = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all', '--', 'src/execweave'], cwd=repo,
    ).decode().strip()
    assert not state, f'package source does not match committed provenance: {state}'
    # This subprocess intentionally imports checkout source to establish the
    # baseline; the separate worker must instead prove site-packages provenance.
    env = dict(os.environ, PYTHONPATH=str(repo / 'src'))
    code = """
import hashlib,json,sys
from execweave.dashboard_shell import DASHBOARD_HTML,render_static_dashboard_html
from execweave.viewer_projection import project_viewer_graph
fixture=json.loads(sys.stdin.read())
print(json.dumps({'dashboard_sha256':hashlib.sha256(DASHBOARD_HTML.encode()).hexdigest(),
 'static_sha256':hashlib.sha256(render_static_dashboard_html(project_viewer_graph(fixture)).encode()).hexdigest(),
 'gif_mode':'topology' if '__execweaveGifTopologySteps=' in DASHBOARD_HTML else 'screen-history'}))
"""
    baseline = subprocess.run([sys.executable, '-c', code], input=json.dumps(fixture()),
                              cwd=out, env=env, check=True, capture_output=True,
                              text=True, encoding='utf-8', timeout=30)
    result = json.loads(baseline.stdout)
    with zipfile.ZipFile(wheel) as archive:
        metadata = next(p for p in archive.namelist() if p.endswith('.dist-info/METADATA'))
        assert all('..' not in Path(p).parts for p in archive.namelist()), 'unsafe wheel member path'
        result['version'] = BytesParser().parsebytes(archive.read(metadata))['Version']
        package_files = {p.removeprefix('execweave/'): sha256(archive.read(p))
                         for p in archive.namelist() if p.startswith('execweave/') and not p.endswith('/')}
    source_files = {str(p.relative_to(repo / 'src/execweave')).replace('\\', '/'): sha256(p.read_bytes())
                    for p in (repo / 'src/execweave').rglob('*') if p.is_file()
                    and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    missing = [p for p, sha in source_files.items() if package_files.get(p) != sha]
    assert not missing, f'wheel differs from source or omits assets: {missing}'
    assert 'vendor/dagre.min.js' in package_files
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, check=True,
                            capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    result.update(source_root=str(repo), source_sha=commit, source_tree=tree, wheel_sha256=sha256(wheel.read_bytes()),
                  package_files=package_files, fixture=fixture())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--wheelhouse', type=Path)
    parser.add_argument('--output', type=Path, default=Path('artifacts/installed-dashboard'))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    choices = [args.wheel] if args.wheel else sorted((repo / 'dist').glob('execweave-*.whl'))
    assert len(choices) == 1, f'expected exactly one wheel, got {choices}'
    wheel = choices[0].resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    baseline = manifest(repo, wheel, output)
    (output / 'source-manifest.json').write_text(json.dumps(baseline, indent=2), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='execweave-installed-dashboard-') as directory:
        scratch = Path(directory).resolve()
        assert not scratch.is_relative_to(repo)
        env_root = scratch / 'venv'
        venv.EnvBuilder(with_pip=True).create(env_root)
        python = env_root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        env['PATH'] = str(python.parent) + os.pathsep + env.get('PATH', '')
        env['PYTHONUTF8'] = '1'
        install = [str(python), '-I', '-m', 'pip', 'install']
        if args.wheelhouse:
            install += ['--no-index', '--find-links', str(args.wheelhouse.resolve())]
        install += [f'{wheel}[e2e]']
        subprocess.run(install, cwd=scratch, env=env, check=True, timeout=240)
        # CI provisions this exact browser revision outside the checkout. An
        # explicit local browser is allowed, but navigation policy is never evaded.
        if not env.get('EXECWEAVE_E2E_CHROMIUM'):
            subprocess.run([str(python), '-I', '-m', 'playwright', 'install', 'chromium'],
                           cwd=scratch, env=env, check=True, timeout=240)
        worker = scratch / 'probe.py'
        shutil.copy2(repo / 'scripts/installed_dashboard_probe.py', worker)
        shutil.copy2(repo / 'scripts/installed_dashboard_live_probe.py', scratch / 'live_probe.py')
        spec = scratch / 'manifest.json'
        spec.write_text(json.dumps(baseline), encoding='utf-8')
        subprocess.run([str(python), '-I', str(worker), '--manifest', str(spec), '--output', str(output)],
                       cwd=scratch, env=env, check=True, timeout=300)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

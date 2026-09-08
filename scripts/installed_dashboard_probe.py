"""Run only from the wheel audit's external, isolated virtual environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import re
import subprocess
import sys
import sysconfig
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prove_install(manifest: dict, destination: Path) -> dict:
    import execweave
    from importlib.metadata import version
    from execweave.dashboard_shell import DASHBOARD_HTML

    root = Path(execweave.__file__).resolve().parent
    purelib = Path(sysconfig.get_paths()['purelib']).resolve()
    assert root.is_relative_to(purelib), (root, purelib)
    assert sys.prefix != sys.base_prefix, 'a clean venv is required'
    source = Path(manifest['source_root']).resolve()
    assert not any(Path(p or '.').resolve().is_relative_to(source) for p in sys.path)
    assert version('execweave') == manifest['version'] == execweave.__version__
    mismatches = [p for p, sha in manifest['package_files'].items()
                  if not (root / p).is_file() or digest((root / p).read_bytes()) != sha]
    assert not mismatches, mismatches
    assert digest(DASHBOARD_HTML.encode()) == manifest['dashboard_sha256']
    proof = {'module_path': str(root), 'python': sys.executable, 'prefix': sys.prefix,
             'cwd': str(Path.cwd()), 'sys_path': sys.path, 'source_contamination': False,
             'version': version('execweave'), 'package_files_verified': len(manifest['package_files']),
             'wheel_sha256': manifest['wheel_sha256'], 'source_sha': manifest['source_sha'],
             'dashboard_sha256': manifest['dashboard_sha256']}
    (destination / 'installed-provenance.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    return proof


def export_and_decode(page, out: Path, *, prove_growth: bool = False) -> dict:
    from PIL import Image, ImageChops, ImageStat

    out.mkdir(parents=True, exist_ok=True)
    page.wait_for_selector('#download-gif:visible')
    page.wait_for_timeout(250)
    page.locator('#svg').screenshot(path=str(out / 'dashboard.png'))
    regions = page.evaluate("""() => {
      const svg=document.getElementById('svg').getBoundingClientRect();
      return [...document.querySelectorAll('.node')].map(node=>{
        const r=node.querySelector('rect').getBoundingClientRect();
        return {id:node.dataset.id,box:[Math.ceil(r.left-svg.left+5),Math.ceil(r.top-svg.top+5),
          Math.floor(r.right-svg.left-5),Math.floor(r.bottom-svg.top-5)]};
      });
    }""") if prove_growth else []
    with page.expect_download(timeout=90000) as result:
        page.locator('#download-gif').click()
    path = out / 'product.gif'
    result.value.save_as(str(path))
    frames, delays, hashes = [], [], []
    with Image.open(path) as gif:
        for i in range(gif.n_frames):
            gif.seek(i)
            frame = gif.convert('RGB')
            frame.load()  # Decode every frame, not only its header or final image.
            frames.append(frame.copy())
            delays.append(int(gif.info.get('duration', 0)))
            hashes.append(digest(frame.tobytes()))
        dimensions = [gif.width, gif.height]
    assert frames
    expected = Image.open(out / 'dashboard.png').convert('RGB')
    assert frames[-1].size == expected.size
    mae = sum(ImageStat.Stat(ImageChops.difference(expected, frames[-1])).mean) / 3
    assert mae < 2.5, mae
    contract = page.evaluate("""() => {
        const g=window.__execweaveCore.getDisplayGraph();
        const replay=window.__execweaveGifTopologySteps;
        return {nodes:g.nodes.length,edges:g.edges.length,
          mode:typeof replay==='function'?'topology':'screen-history',
          steps:typeof replay==='function'?replay(g).length:null};
    }""")
    if contract['mode'] == 'topology':
        assert len(frames) == contract['steps']
        if contract['nodes'] > 1:
            assert len(set(hashes)) > 1
        assert delays[-1] >= 800
    visibility = []
    if prove_growth and contract['mode'] == 'topology':
        assert len(regions) == contract['nodes']
        for region in regions:
            x1, y1, x2, y2 = region['box']
            assert 0 <= x1 < x2 <= expected.width and 0 <= y1 < y2 <= expected.height
        seen = set()
        for index, frame in enumerate(frames):
            scores = {r['id']: sum(ImageStat.Stat(ImageChops.difference(
                expected.crop(r['box']), frame.crop(r['box']))).mean) / 3 for r in regions}
            visible = {identity for identity, score in scores.items() if score < 8}
            visibility.append({'frame': index, 'visible': sorted(visible), 'crop_mae': scores})
            assert seen <= visible and len(visible-seen) <= 1, visibility
            seen = visible
            frame.save(out / f'frame-{index:03}.png')
        assert seen == {r['id'] for r in regions}
    frames[0].save(out / 'first.png')
    frames[-1].save(out / 'final.png')
    report = {**contract, 'gif_sha256': digest(path.read_bytes()), 'dimensions': dimensions,
              'frames': len(frames), 'frame_sha256': hashes, 'delays_ms': delays, 'final_mae': mae,
              'decoded_node_visibility': visibility}
    (out / 'gif.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def static_probe(browser, manifest: dict, out: Path) -> dict:
    from execweave.dashboard_shell import render_static_dashboard_html
    from execweave.viewer_projection import project_viewer_graph

    graph = manifest['fixture']
    before = digest(json.dumps(graph, sort_keys=True).encode())
    html = render_static_dashboard_html(project_viewer_graph(graph))
    assert digest(html.encode()) == manifest['static_sha256']
    viewer = out / 'fixture-viewer.html'
    viewer.write_text(html, encoding='utf-8')
    errors, requests = [], []
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
    page.on('request', lambda r: requests.append(r.url))
    page.goto(viewer.as_uri())  # Real file navigation; never page.route/set_content here.
    page.wait_for_selector('.node')
    assert page.locator('.node').count() >= 5
    result = {}
    for theme in ('dark', 'light'):
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme-toggle').click()
        page.locator('#arrange').click()
        page.locator('#fit').click()
        page.wait_for_timeout(400)
        result[theme] = export_and_decode(page, out / f'static-{theme}', prove_growth=True)
        assert result[theme]['mode'] == manifest['gif_mode'], 'installed/source GIF contract differs'
    result['repeat'] = export_and_decode(page, out / 'static-repeat', prove_growth=True)
    assert result['repeat']['gif_sha256'] == result['light']['gif_sha256']
    raw_before = page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
    for mode in ('hide', 'all', 'changed'):
        page.locator('#file-graph-filter').select_option(mode)
        assert raw_before == page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
        if mode == 'hide':
            assert page.locator('.node.category-file').count() == 0
    assert digest(json.dumps(graph, sort_keys=True).encode()) == before
    assert not errors, errors
    assert not any('/live.json' in url or '/final' in url for url in requests)
    page.close()
    return result




def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    result = {'overall': 'FAIL'}
    try:
        result['provenance'] = prove_install(manifest, out)
        cli = Path(sys.executable).with_name('execweave.exe' if os.name == 'nt' else 'execweave')
        assert cli.is_file()
        for name, argv in [('help', ['--help']), ('doctor', ['doctor']), ('top-help', ['top', '--help'])]:
            done = subprocess.run([str(cli), *argv], check=True, capture_output=True,
                                  text=True, encoding='utf-8', timeout=30)
            (out / f'cli-{name}.log').write_text(done.stdout + done.stderr, encoding='utf-8')
        record = out / 'record-run'
        done = subprocess.run([str(cli), 'record', '--backend', 'portable', '--no-files',
            '--no-network', '--output-dir', str(record), '--', sys.executable, '-c',
            "import time; print('WHEEL_RECORD'); time.sleep(.2)"], check=True,
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        (out / 'cli-record.log').write_text(done.stdout + done.stderr, encoding='utf-8')
        assert (record / 'events.jsonl').is_file() and (record / 'viewer.html').is_file()
        from execweave.top import run_top
        import io
        stream = io.StringIO()
        run_top([sys.executable, '-c', "import time; print('WHEEL_TOP'); time.sleep(.2)"],
            watch_root=out, output_dir=out / 'top-run', collect_filesystem=False,
            collect_network=False, linger_seconds=0, stream=stream)
        (out / 'installed-top-inline.log').write_text(stream.getvalue(), encoding='utf-8')
        assert (out / 'top-run/graph.json').is_file()
        result['cli_record'] = 'PASS'
        result['top_mode'] = 'installed run_top inline; CLI help separately checked'
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            explicit = os.environ.get('EXECWEAVE_E2E_CHROMIUM')
            browser = playwright.chromium.launch(**({'executable_path': explicit} if explicit else {}))
            try:
                result['static'] = static_probe(browser, manifest, out)
                native = runpy.run_path(str(Path(__file__).with_name('live_probe.py')))['native_probe']
                result['native'] = native(browser, cli, out, export_and_decode)
            finally:
                browser.close()
        result['overall'] = 'PASS'
    except Exception as error:
        result['error'] = re.sub(r'([?&]t=)[A-Za-z0-9_-]+', r'\1REDACTED',
                                 f'{type(error).__name__}: {error}')
        raise
    finally:
        (out / 'INSTALLED_DASHBOARD.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

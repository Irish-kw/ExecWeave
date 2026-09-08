"""Byte-identical repeat exports under an explicitly stable, real visual input."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.viewer_projection import project_viewer_graph
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e
ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_reduced_motion_keeps_repeated_export_input_and_pixels_stable(tmp_path, theme):
    probe = load('installed_dashboard_probe')
    launcher = load('check_installed_dashboard')
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000},
                                    accept_downloads=True, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            # This small gate tests actual export and OS reduced-motion support;
            # clean-wheel CI separately navigates file and genuine HTTP origins.
            page.set_content(render_static_dashboard_html(project_viewer_graph(launcher.fixture())))
            page.wait_for_selector('.node')
            if page.locator('html').get_attribute('data-theme') != theme:
                page.locator('#theme-toggle').click()
            page.locator('#arrange').click()
            page.locator('#fit').click()
            page.mouse.move(0, 0)
            page.wait_for_timeout(400)
            assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
            assert page.evaluate("document.getElementById('svg').getAnimations({subtree:true}).filter(a=>a.playState==='running').length") == 0
            first = probe.export_and_decode(page, tmp_path / 'first', prove_growth=True)
            repeat = probe.export_and_decode(page, tmp_path / 'repeat', prove_growth=True)
            assert first['gif_sha256'] == repeat['gif_sha256']
            assert first['frame_sha256'] == repeat['frame_sha256']
            assert (tmp_path / 'first/dashboard.png').read_bytes() == (tmp_path / 'repeat/dashboard.png').read_bytes()
            assert not errors, errors
        finally:
            browser.close()

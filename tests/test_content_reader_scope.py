"""Content-folder capabilities stay within the complete execution identity.

Component cases use real file inputs with deliberately size-mismatched bytes:
reaching size_mismatch proves the file path was read, not hash verification.
Native cases separately open a relocated file-backed full Dashboard and use the
browser's real SHA-256. No fetch, file API, digest or timer is replaced.
"""
from __future__ import annotations

import hashlib
import shutil

import pytest

from execweave.viewer_projection import write_graph_html
from test_content_browser import fixture_html, reference
from test_investigation_workspace import browser_page
from test_message_handoff_navigation import PANEL, capture, select

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e
DIALOG = '#execweave-content-dialog'


def wait_state(page, state):
    page.wait_for_function(
        "s=>document.querySelector('#execweave-content-dialog')?.dataset.state===s",
        arg=state, timeout=2000,
    )


def component(page, root):
    ref = reference(b'expected body')
    folder = root / 'recorded-run'
    stored = folder / ref['path']
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b'bad-size')
    page.set_content(fixture_html([ref], static=True))
    page.evaluate("""()=>Object.assign(window.__execweaveStaticGraph,{
        run_id:'execution-A',source_path:'/run-A/events.jsonl'
    })""")
    page.locator('.execweave-content-actions button').first.click()
    wait_state(page, 'folder_required')
    page.locator('#execweave-content-folder').set_input_files(str(folder))
    wait_state(page, 'size_mismatch')
    return folder


@pytest.mark.parametrize('field,value', [
    ('session_id', 'session-B'),
    ('run_id', 'execution-B'),
    ('source_path', '/run-B/events.jsonl'),
])
def test_reopening_requires_folder_selection_for_each_identity_change(
    tmp_path, browser_page, field, value,
):
    page = browser_page
    component(page, tmp_path)
    page.get_by_role('button', name='Close', exact=True).click()
    page.evaluate('([k,v])=>window.__execweaveStaticGraph[k]=v', [field, value])
    page.locator('.execweave-content-actions button').first.click()
    wait_state(page, 'folder_required')
    assert page.locator('#execweave-content-text').inner_text() == ''


def test_load_retry_cannot_reuse_previous_run_capability(tmp_path, browser_page):
    page = browser_page
    component(page, tmp_path)
    page.evaluate("window.__execweaveStaticGraph.run_id='execution-B'")
    page.get_by_role('button', name='Load / retry', exact=True).click()
    assert not page.locator(DIALOG).is_visible()
    page.locator('.execweave-content-actions button').first.click()
    wait_state(page, 'folder_required')


@pytest.mark.parametrize('event', ['onPayload', 'onFinished'])
def test_lifecycle_change_revokes_folder_even_without_inspector_mutation(
    tmp_path, browser_page, event,
):
    page = browser_page
    component(page, tmp_path)
    page.evaluate("window.__execweaveStaticGraph.source_path='/another/events.jsonl'")
    page.evaluate('name=>window.__execweaveDashboard?.[name]?.({})', event)
    assert not page.locator(DIALOG).is_visible()
    assert page.locator('#execweave-content-text').inner_text() == ''
    page.locator('.execweave-content-actions button').first.click()
    wait_state(page, 'folder_required')


def test_same_identity_retains_selected_folder_across_reopening(tmp_path, browser_page):
    page = browser_page
    component(page, tmp_path)
    page.get_by_role('button', name='Close', exact=True).click()
    page.evaluate("window.__execweaveStaticGraph.event_count=99")
    page.evaluate('window.__execweaveDashboard?.onPayload?.({})')
    page.locator('.execweave-content-actions button').first.click()
    wait_state(page, 'size_mismatch')


def test_pagehide_revokes_folder_not_just_visible_text(tmp_path, browser_page):
    page = browser_page
    component(page, tmp_path)
    page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    assert not page.locator(DIALOG).is_visible()
    page.locator('.execweave-content-actions button').first.click()
    wait_state(page, 'folder_required')


def test_existing_dashboard_hooks_keep_arguments(browser_page):
    from execweave.viewer_content_browser import inject_content_browser

    source = '''<html><body><div id="details"></div><script>
    window.__execweaveStaticGraph={session_id:'a'};
    window.calls=[];window.__execweaveDashboard={
      onPayload(...args){window.calls.push(['payload',...args]);},
      onFinished(...args){window.calls.push(['finished',...args]);}
    };</script></body></html>'''
    browser_page.set_content(inject_content_browser(source))
    browser_page.evaluate("""()=>{
      window.__execweaveDashboard.onPayload({sentinel:1},'extra');
      window.__execweaveDashboard.onFinished({sentinel:2});
    }""")
    assert browser_page.evaluate('window.calls') == [
        ['payload', {'sentinel': 1}, 'extra'], ['finished', {'sentinel': 2}],
    ]


@pytest.mark.parametrize('variant,expected', [
    ('intact', 'verified'), ('same_size_tamper', 'hash_mismatch'), ('missing', 'missing_blob'),
])
def test_native_relocated_message_body_after_original_folder_removed(
    tmp_path, browser_page, variant, expected,
):
    """Native Offline path, not a synthetic File/digest substitute or set_content."""
    source = tmp_path / 'original'
    source.mkdir()
    graph, index, sender, recipient, _ = capture(source)
    write_graph_html(graph, source / 'viewer.html')
    record = next(r for r in index['messages'] if r['owner_id'] == sender and r['target_id'] == recipient)
    ref = record['references'][0]['reference']
    data = (source / ref['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == ref['sha256']
    moved = tmp_path / 'relocated'
    shutil.copytree(source, moved)
    shutil.rmtree(source)
    if variant == 'same_size_tamper':
        (moved / ref['path']).write_bytes(b'x' * len(data))
    elif variant == 'missing':
        (moved / ref['path']).unlink()
    before = {str(p.relative_to(moved)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in moved.rglob('*') if p.is_file()}
    page = browser_page
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    page.goto((moved / 'viewer.html').as_uri())
    select(page, sender, recipient)
    row = page.locator(PANEL + ' .investigation-row').filter(has=page.locator('summary')).first
    row.locator('summary').click()
    row.locator('.execweave-content-actions button').first.click()
    wait_state(page, 'folder_required')
    page.locator('#execweave-content-folder').set_input_files(str(moved))
    wait_state(page, expected)
    shown = page.locator('#execweave-content-text').text_content()
    assert shown == (data.decode('utf-8') if variant == 'intact' else '')
    assert not any(url.startswith(('http:', 'https:')) for url in requests)
    assert not source.exists()
    assert before == {str(p.relative_to(moved)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in moved.rglob('*') if p.is_file()}

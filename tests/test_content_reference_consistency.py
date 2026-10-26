"""Reference agreement in the real browser reader; no byte verification claim.

Synthetic metadata is loaded into the shipped content component. A rejected
reference must fail before file selection or network access. Consistent legacy
references may still reach folder_required, which is not verified plaintext.
"""
from __future__ import annotations

import copy

import pytest

from test_content_browser import fixture_html, reference
from test_investigation_workspace import browser_page

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e
DIALOG = '#execweave-content-dialog'


def content_node(ref, *, identity='blob-A', **changes):
    return {'id': identity, 'type': 'observed_content',
            'attributes': {**ref, **changes}}


def open_reference(page, ref, nodes):
    page.set_content(fixture_html([ref], static=True))
    page.evaluate('nodes=>window.__execweaveStaticGraph.nodes=nodes', nodes)
    before = page.evaluate('window.__execweaveStaticGraph')
    requests = []
    page.on('request', lambda req: requests.append(req.url))
    page.locator('.execweave-content-actions button').first.click()
    page.wait_for_function(
        "()=>document.querySelector('#execweave-content-dialog').dataset.state!=='loading'",
        timeout=2000,
    )
    assert page.evaluate('window.__execweaveStaticGraph') == before
    assert not requests
    assert page.locator('#execweave-content-text').inner_text() == ''
    return page.locator(DIALOG).get_attribute('data-state')


@pytest.mark.parametrize('order', ['original-first', 'conflict-first'])
def test_all_known_size_declarations_must_agree(browser_page, order):
    ref = reference(b'recorded body')
    nodes = [content_node(ref), content_node(ref, identity='blob-B', size_bytes=999)]
    if order == 'conflict-first':
        nodes.reverse()
    assert open_reference(browser_page, ref, nodes) == 'conflicting_reference'


def test_explicit_reader_size_cannot_override_graph_declaration(browser_page):
    ref = reference(b'recorded body')
    node = content_node(ref)
    supplied = {**ref, 'size_bytes': ref['size_bytes'] + 1}
    assert open_reference(browser_page, supplied, [node]) == 'conflicting_reference'


@pytest.mark.parametrize('conflict', ['path', 'digest', 'node-type'])
def test_named_content_identity_cannot_be_redirected(browser_page, conflict):
    ref = reference(b'recorded body', id='blob-A')
    node = content_node(ref)
    if conflict == 'path':
        node['attributes']['path'] = reference(b'another body')['path']
    elif conflict == 'digest':
        node['attributes']['sha256'] = 'f' * 64
    else:
        node['type'] = 'agent'
    assert open_reference(browser_page, ref, [node]) == 'conflicting_reference'


def test_conflicting_duplicate_identity_cannot_use_first_match(browser_page):
    ref = reference(b'recorded body', id='blob-A')
    first = content_node(ref)
    second = content_node(reference(b'other bytes'))
    assert open_reference(browser_page, ref, [first, second]) == 'conflicting_reference'


@pytest.mark.parametrize('variant', ['no-graph-copy', 'unknown-size', 'same-bytes-two-kinds'])
def test_consistent_legacy_and_multi_kind_references_remain_readable(browser_page, variant):
    ref = reference(b'recorded body')
    nodes = [content_node(ref)]
    if variant == 'no-graph-copy':
        nodes = []
    elif variant == 'unknown-size':
        ref.pop('size_bytes')
    else:
        nodes.append(content_node(ref, identity='blob-B', content_kind='model.response'))
        nodes[0]['attributes']['content_kind'] = 'tool.output'
        nodes[0]['attributes']['complete_from_source'] = False
        nodes[1]['attributes']['complete_from_source'] = True
    assert open_reference(browser_page, ref, nodes) == 'folder_required'


def test_identical_repeated_declaration_is_not_a_conflict(browser_page):
    ref = reference(b'recorded body', id='blob-A')
    node = content_node(ref)
    assert open_reference(browser_page, ref, [node, copy.deepcopy(node)]) == 'folder_required'


def test_retry_checks_new_graph_conflict_before_reading(browser_page):
    ref = reference(b'recorded body')
    assert open_reference(browser_page, ref, [content_node(ref)]) == 'folder_required'
    browser_page.evaluate('window.__execweaveStaticGraph.nodes[0].attributes.size_bytes+=1')
    browser_page.get_by_role('button', name='Load / retry', exact=True).click()
    assert browser_page.locator(DIALOG).get_attribute('data-state') == 'conflicting_reference'
    assert browser_page.locator('#execweave-content-text').inner_text() == ''


def test_invalid_known_size_is_not_erased_by_valid_reader_value(browser_page):
    ref = reference(b'recorded body')
    assert open_reference(browser_page, ref, [content_node(ref, size_bytes=True)]) == 'invalid_reference'

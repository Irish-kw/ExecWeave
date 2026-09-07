"""Focus must be exitable, by three routes, without reloading the page.

Selecting a node marked it and opened the inspector, and nothing put the graph back:
clearSelection existed but no control, key or gesture called it. A reader who clicked a
node was stuck with it until they reloaded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_graph_node_sizing_e2e import _browser, _graph_with, _launch, _render

pytestmark = pytest.mark.viewer_e2e


def _focused_page(page: Any) -> None:
    page.wait_for_selector(".node", timeout=15000)
    page.eval_on_selector(".node[data-id='tool:codex:x']", "el => el.dispatchEvent(new MouseEvent('click', {bubbles: true}))")
    page.wait_for_selector(".node.selected", timeout=5000)


def _empty_point(page: Any) -> tuple[float, float]:
    """A point inside the canvas that is not over a node.

    Hard-coding coordinates put the earlier version of these checks outside the svg
    entirely, where the events never reached the graph at all.
    """
    found = page.evaluate(
        """() => {
            const svg = document.querySelector('svg');
            const box = svg.getBoundingClientRect();
            for (let y = box.top + 20; y < box.bottom - 20; y += 25) {
                for (let x = box.left + 20; x < box.right - 20; x += 25) {
                    const el = document.elementFromPoint(x, y);
                    if (el && el.closest('svg') && !el.closest('.node')) return [x, y];
                }
            }
            return null;
        }"""
    )
    assert found, "no empty canvas point was reachable"
    return found[0], found[1]


def _state(page: Any) -> dict[str, Any]:
    return {
        "selected": page.eval_on_selector_all(".node.selected", "n => n.length"),
        "control_hidden": page.eval_on_selector("#clear-focus", "el => el.hidden"),
    }


def _run(tmp_path: Path, exit_focus) -> tuple[dict[str, Any], dict[str, Any]]:
    viewer = _render(tmp_path, _graph_with("read"))
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(viewer.as_uri())
            _focused_page(page)
            focused = _state(page)
            exit_focus(page)
            page.wait_for_timeout(150)
            return focused, _state(page)
        finally:
            browser.close()


def test_the_control_appears_only_while_something_is_focused(tmp_path: Path) -> None:
    viewer = _render(tmp_path, _graph_with("read"))
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            assert page.eval_on_selector("#clear-focus", "el => el.hidden") is True, (
                "the graph must not offer a button that would do nothing"
            )
            _focused_page(page)
            assert page.eval_on_selector("#clear-focus", "el => el.hidden") is False
        finally:
            browser.close()


def test_the_control_clears_focus(tmp_path: Path) -> None:
    focused, after = _run(tmp_path, lambda page: page.click("#clear-focus"))
    assert focused["selected"] == 1 and focused["control_hidden"] is False, focused
    assert after["selected"] == 0, "the node is still focused after the control was used"
    assert after["control_hidden"] is True


def test_escape_clears_focus(tmp_path: Path) -> None:
    focused, after = _run(tmp_path, lambda page: page.keyboard.press("Escape"))
    assert focused["selected"] == 1, focused
    assert after["selected"] == 0, "Escape did not return the graph to unfocused"


def test_clicking_empty_canvas_clears_focus(tmp_path: Path) -> None:
    def click_away(page: Any) -> None:
        x, y = _empty_point(page)
        page.mouse.click(x, y)

    focused, after = _run(tmp_path, click_away)
    assert focused["selected"] == 1, focused
    assert after["selected"] == 0, "clicking away from every node did not clear focus"


def test_dragging_the_canvas_is_a_pan_and_keeps_focus(tmp_path: Path) -> None:
    """Panning starts on empty canvas too; only a click without travel clears."""

    def drag(page: Any) -> None:
        x, y = _empty_point(page)
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x - 120, y - 60, steps=8)
        page.mouse.up()

    focused, after = _run(tmp_path, drag)
    assert focused["selected"] == 1, focused
    assert after["selected"] == 1, "a pan cleared the focus the reader was holding"

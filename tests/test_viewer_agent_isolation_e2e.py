"""Drive the visible v0.7.9 dashboard in Chromium.

The product contract is deliberately small: root shows Prompt + Final response;
a subagent shows Task + Thinking + Response; a non-agent shows no conversation.
Live and viewer.html must render the same inspector and counts for the same graph evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from multi_agent_run_fixture import (
    CHILDREN,
    ENCRYPTED_SPAWN_INDEX,
    QUOTED_ROUTING_ANSWER,
    SECOND_ANSWER,
    SECOND_QUESTION,
    build_run,
)

# The single wording the inspector uses for a turn the provider recorded but never
# exposed in plaintext. Kept here so the browser check fails if it drifts back to a
# phrase that claims the run observed nothing.
ENCRYPTED_NOTICE = "Observed — plaintext not exposed by provider."

MARKERS = {path: marker for _, path, _, marker in CHILDREN}
ALL_MARKERS = set(MARKERS.values())
FORBIDDEN_VISIBLE_COPY = (
    "Raw node evidence",
    "Conversation records",
    "Show all agents",
    "Agent trace",
    "Provider trace visibility",
    "Focus 1 hop",
    "Focus 2 hops",
    "Saved views",
    "Save view",
)

pytestmark = pytest.mark.viewer_e2e


def _chromium_path() -> str | None:
    explicit = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
    if explicit and Path(explicit).exists():
        return explicit
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
    if base.is_dir():
        for candidate in sorted(base.glob("chromium*/chrome-linux/chrome")):
            return str(candidate)
        for candidate in sorted(
            base.glob("chromium*/chrome-mac/Chromium.app/Contents/MacOS/Chromium")
        ):
            return str(candidate)
    return shutil.which("chromium") or shutil.which("chromium-browser")


def _required() -> bool:
    return os.environ.get("EXECWEAVE_E2E_REQUIRED", "").strip().lower() not in {
        "",
        "0",
        "false",
    }


def _unavailable(reason: str) -> None:
    if _required():
        pytest.fail(f"the viewer end-to-end check is required here but {reason}")
    pytest.skip(reason)


def _browser():
    try:
        from playwright import sync_api
    except ImportError:
        _unavailable("playwright is not installed")
    return sync_api.sync_playwright(), _chromium_path()


def _launch(playwright: Any, executable: str | None) -> Any:
    try:
        return playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
    except Exception as error:  # noqa: BLE001 - report the browser failure verbatim
        _unavailable(f"chromium would not launch: {error}")
        raise


def _artifact_dir() -> Path | None:
    value = os.environ.get("EXECWEAVE_VISUAL_ARTIFACT_DIR")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _agent_id(graph: dict[str, Any], path: str) -> str:
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        candidate = attrs.get("agent_path") or attrs.get("child_agent_path") or attrs.get(
            "root_agent_path"
        )
        if candidate == path or (path == "/root" and attrs.get("agent_role") == "root"):
            return str(node["id"])
    raise AssertionError(f"no graph agent for {path}")


def _click_id(page: Any, node_id: str) -> None:
    found = page.eval_on_selector_all(
        ".node",
        """(nodes,id)=>{const node=nodes.find(item=>item.dataset.id===id);if(!node)return false;
        node.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true} """,
        node_id,
    )
    assert found, f"graph did not render node {node_id}"
    page.wait_for_timeout(250)


def _cards(page: Any) -> tuple[list[str], list[str]]:
    labels = page.locator("#details .execweave-agent-label").all_text_contents()
    bodies = page.locator("#details .execweave-agent-body").all_text_contents()
    return [value.strip() for value in labels], [value.strip() for value in bodies]


def _wait_for_text(page: Any, text: str) -> None:
    page.wait_for_function(
        "value=>(document.getElementById('details')?.innerText||'').includes(value)",
        arg=text,
        timeout=15000,
    )


def _visible_page_text(page: Any) -> str:
    return page.locator("body").inner_text()


def _assert_no_dashboard_clutter(page: Any) -> None:
    visible = _visible_page_text(page).casefold()
    for text in FORBIDDEN_VISIBLE_COPY:
        assert text.casefold() not in visible, f"obsolete dashboard copy is visible: {text!r}"


def _audit(page: Any, graph: dict[str, Any]) -> dict[str, tuple[list[str], list[str]]]:
    results: dict[str, tuple[list[str], list[str]]] = {}

    root_id = _agent_id(graph, "/root")
    _click_id(page, root_id)
    _wait_for_text(page, "spawn four agents")
    labels, bodies = _cards(page)
    assert labels == ["Prompt", "Final response"]
    assert bodies[0] == "spawn four agents"
    assert ALL_MARKERS <= {marker for marker in ALL_MARKERS if marker in bodies[1]}
    results["/root"] = labels, bodies
    _assert_no_dashboard_clutter(page)

    for index, (_, path, _, marker) in enumerate(CHILDREN, start=1):
        _click_id(page, _agent_id(graph, path))
        _wait_for_text(page, marker)
        labels, bodies = _cards(page)
        assert labels == ["Task", "Thinking", "Response"]
        assert bodies[0] == f"answer question {index}"
        assert bodies[1] == "Not observed."
        assert marker in bodies[2]
        assert "recommended_plugins" not in "\n".join(bodies)
        assert "Plugin 042" not in "\n".join(bodies)
        leaked = sorted(other for other in ALL_MARKERS - {marker} if other in "\n".join(bodies))
        assert not leaked, f"{path} shows sibling conversation markers: {leaked}"
        results[path] = labels, bodies
        _assert_no_dashboard_clutter(page)

    # A non-agent node describes itself — v0.8.0 gives it its command, its address and
    # what was observed of it — and never carries a conversation.
    for node_id in ("process:codex", "endpoint:203.0.113.7:443"):
        _click_id(page, node_id)
        labels, _ = _cards(page)
        assert labels, f"{node_id} shows nothing at all"
        conversation = {"Prompt", "Final response", "Task", "Thinking", "Response"}
        assert not conversation & set(labels), f"{node_id} shows conversation cards: {labels}"
        visible = page.locator("#details").inner_text()
        assert not any(marker in visible for marker in ALL_MARKERS), (
            f"{node_id}, which is not an agent, shows an agent's turn"
        )

    return results


def _capture(page: Any, name: str) -> None:
    output = _artifact_dir()
    if output is not None:
        page.screenshot(path=str(output / name), full_page=True)


def test_the_recorded_viewer_shows_each_agent_only_its_own_conversation(tmp_path: Path) -> None:
    from execweave.viewer_projection import write_graph_html

    graph = build_run(tmp_path)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)
    output = _artifact_dir()
    if output is not None:
        shutil.copyfile(viewer, output / "viewer.html")

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            _click_id(page, _agent_id(graph, "/root"))
            _wait_for_text(page, "spawn four agents")
            _capture(page, "viewer-root.png")
            first_path = CHILDREN[0][1]
            _click_id(page, _agent_id(graph, first_path))
            _wait_for_text(page, MARKERS[first_path])
            _capture(page, "viewer-subagent.png")
            _audit(page, graph)
        finally:
            browser.close()


def test_the_live_dashboard_isolates_agents_before_the_run_finishes(tmp_path: Path) -> None:
    """The live page must match viewer.html before the run reaches finalization."""
    from execweave import live as live_module
    from execweave.viewer_projection import project_viewer_graph, write_graph_html

    graph = build_run(tmp_path)
    projected_graph = project_viewer_graph(graph)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_module._LiveState("e2e", event_path)
    state._projected_graph_locked = lambda: dict(projected_graph)  # type: ignore[method-assign]
    # The real projection path sets this when it emits viewer-only graph counts. The
    # fixture supplies the projected graph directly, so mirror that production state.
    state._viewer_projection_ever_active = True
    token = "e2e-token"
    server = live_module._LocalThreadingHTTPServer(
        ("127.0.0.1", 0), live_module._handler_factory(state, token)
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    manager, executable = _browser()
    try:
        with manager as playwright:
            browser = _launch(playwright, executable)
            try:
                static_page = browser.new_page(viewport={"width": 1440, "height": 1000})
                static_page.goto(viewer.as_uri())
                static_page.wait_for_selector(".node", timeout=15000)
                static_result = _audit(static_page, graph)
                static_stats = static_page.locator("#stats").inner_text().strip()

                live_page = browser.new_page(viewport={"width": 1440, "height": 1000})
                live_page.goto(f"http://{host}:{port}/?t={token}")
                live_page.wait_for_selector(".node", timeout=15000)
                live_page.wait_for_function(
                    "expected=>(document.getElementById('stats')?.innerText||'').trim()===expected",
                    arg=static_stats,
                    timeout=15000,
                )
                assert not state._finished, "this test only means something mid-run"
                live_result = _audit(live_page, graph)
                assert live_result == static_result
                assert live_page.locator("#stats").inner_text().strip() == static_stats

                _click_id(live_page, _agent_id(graph, "/root"))
                _wait_for_text(live_page, "spawn four agents")
                _capture(live_page, "live-root.png")
                first_path = CHILDREN[0][1]
                _click_id(live_page, _agent_id(graph, first_path))
                _wait_for_text(live_page, MARKERS[first_path])
                _capture(live_page, "live-subagent.png")
                output = _artifact_dir()
                if output is not None:
                    (output / "live.html").write_text(live_page.content(), encoding="utf-8")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_live_server_serves_the_same_index_the_file_would_carry(tmp_path: Path) -> None:
    from urllib.request import urlopen

    from execweave import live as live_module
    from execweave.conversation_records import conversation_index_payload

    graph = build_run(tmp_path)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_module._LiveState("e2e", event_path)
    state._projected_graph_locked = lambda: dict(graph)  # type: ignore[method-assign]
    token = "e2e-token"
    server = live_module._LocalThreadingHTTPServer(
        ("127.0.0.1", 0), live_module._handler_factory(state, token)
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        assert not (tmp_path / "conversations.json").exists()
        with urlopen(f"http://{host}:{port}/conversations.json?t={token}", timeout=5) as response:
            served = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert served == conversation_index_payload(graph, tmp_path)
    paths = {
        (entry.get("conversation_preview") or {}).get("agent_path")
        for entry in served["entries"]
    }
    assert {"/root", *MARKERS} <= paths, paths


def test_no_agent_hands_over_a_transcript_that_is_not_its_own(tmp_path: Path) -> None:
    """The compact agent inspector must never offer a raw transcript escape hatch."""
    from execweave.viewer_projection import write_graph_html

    graph = build_run(tmp_path, per_agent_rollouts=False)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page()
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            for _, path, _, marker in CHILDREN:
                _click_id(page, _agent_id(graph, path))
                _wait_for_text(page, marker)
                text = page.locator("#details").inner_text()
                assert marker in text
                assert page.locator("#details a").count() == 0
                assert "raw" not in text.lower()
                leaked = sorted(other for other in ALL_MARKERS - {marker} if other in text)
                assert not leaked, f"{path} exposes another agent through its inspector: {leaked}"
        finally:
            browser.close()

def test_an_agent_archived_many_times_still_shows_its_prompt_and_answer(tmp_path: Path) -> None:
    """One agent owns several archives, and the earliest carry nothing usable.

    Codex writes the rollout again on every Stop hook. A real four-agent run produced
    fourteen index entries of which nine held no conversation at all, and a renderer
    that took the first record matching an agent found one of those and showed
    "Not observed." for the prompt and the answer, permanently, for the rest of the
    run. The inspector has to aggregate every record the agent owns.
    """
    from execweave.viewer_projection import write_graph_html

    graph = build_run(tmp_path, snapshots=2)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            _click_id(page, _agent_id(graph, "/root"))
            _wait_for_text(page, "spawn four agents")
            labels, bodies = _cards(page)
        finally:
            browser.close()

    assert labels == ["Prompt", "Final response"]
    assert bodies[0] == "spawn four agents"
    assert "Not observed." not in bodies, "the earliest empty archive won the selection"
    leaked = sorted(marker for marker in ALL_MARKERS if marker not in bodies[1])
    assert not leaked, f"the root lost answers addressed to it: {leaked}"


def test_encrypted_turns_read_as_observed_and_quoted_routing_words_survive(
    tmp_path: Path,
) -> None:
    """Two ways a turn can be misread, both checked in the page.

    A delegation the provider encrypted is observed evidence whose plaintext was never
    exposed; rendering it as "Not observed." would claim the run never recorded it. And
    an answer that quotes ``Sender:`` or ``Task name:`` is prose, not a routing
    envelope — a parser that scans for those words outside a real ``Payload:`` block
    swallows the whole answer.
    """
    from execweave.viewer_projection import write_graph_html

    graph = build_run(tmp_path, per_agent_rollouts=False)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)
    encrypted_path = CHILDREN[ENCRYPTED_SPAWN_INDEX][1]
    quoting_path = CHILDREN[0][1]

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)

            _click_id(page, _agent_id(graph, encrypted_path))
            _wait_for_text(page, MARKERS[encrypted_path])
            labels, bodies = _cards(page)
            assert labels == ["Task", "Thinking", "Response"]
            assert bodies[0] == ENCRYPTED_NOTICE, (
                "an encrypted delegation must read as observed, not as never recorded"
            )

            _click_id(page, _agent_id(graph, quoting_path))
            _wait_for_text(page, MARKERS[quoting_path])
            _, bodies = _cards(page)
        finally:
            browser.close()

    for line in QUOTED_ROUTING_ANSWER.splitlines():
        assert line in bodies[2], f"the answer lost a quoted line: {line!r}"


def test_finishing_a_run_keeps_the_reader_on_the_same_dashboard(tmp_path: Path) -> None:
    """Completion changes the state of the page, not which page it is.

    The live dashboard used to fetch a separate ``/final`` document and write it over
    the open one, so a reader watching a run was moved to a second renderer the moment
    it ended. v0.7.9 has one renderer: the DOM the reader is looking at stays, its
    nodes keep their identity, and only the terminal state changes.
    """
    from execweave import live as live_module
    from execweave.viewer_projection import project_viewer_graph

    graph = build_run(tmp_path)
    projected = project_viewer_graph(graph)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_module._LiveState("finish", event_path)
    state._projected_graph_locked = lambda: dict(projected)  # type: ignore[method-assign]
    state._viewer_projection_ever_active = True
    token = "finish-token"
    server = live_module._LocalThreadingHTTPServer(
        ("127.0.0.1", 0), live_module._handler_factory(state, token)
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    manager, executable = _browser()
    try:
        with manager as playwright:
            browser = _launch(playwright, executable)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.goto(f"http://{host}:{port}/?t={token}")
                page.wait_for_selector(".node", timeout=15000)
                _click_id(page, _agent_id(graph, "/root"))
                _wait_for_text(page, "spawn four agents")

                # Mark the live document so a replacement is detectable.
                page.evaluate("()=>{window.__execweaveSameDocument=true}")
                before_url = page.url
                before_cards = _cards(page)

                state.finish(dict(graph), final_html="<html><body>replaced</body></html>")
                page.wait_for_function(
                    "()=>(document.body.innerText||'').includes('FINISHED')", timeout=15000
                )

                assert page.evaluate("()=>window.__execweaveSameDocument===true"), (
                    "the finished run replaced the document the reader was on"
                )
                assert page.url == before_url, f"completion navigated away: {page.url}"
                assert "replaced" not in page.locator("body").inner_text()
                assert page.locator(".node").count() > 0, "the graph was torn down"
                assert _cards(page) == before_cards, "the selected agent lost its inspector"
                _assert_no_dashboard_clutter(page)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_each_round_keeps_its_own_question_and_answer(tmp_path: Path) -> None:
    """A run is rarely one question, and the panel has room for one.

    With two rounds it took the oldest prompt and the newest answer, so it showed the
    first question beside the second question's answer. The first round's real answer
    and the second question were both unreachable. Rounds are now separate: the newest
    is open, older ones fold to their own moment, and each keeps the pair it belongs to.
    """
    from execweave.viewer_projection import write_graph_html

    graph = build_run(tmp_path, rounds=2)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            _click_id(page, _agent_id(graph, "/root"))
            _wait_for_text(page, SECOND_QUESTION)

            open_round = page.locator("#details .execweave-agent-round").first
            newest = open_round.locator(".execweave-agent-body").all_text_contents()
            folds = page.locator("#details .execweave-agent-older > summary").all_text_contents()

            page.eval_on_selector_all("#details details", "items=>items.forEach(x=>{x.open=true})")
            page.wait_for_timeout(200)
            older = page.locator(
                "#details .execweave-agent-older .execweave-agent-body"
            ).all_text_contents()

            # One assignment per child, so a subagent has a single round and no fold.
            _click_id(page, _agent_id(graph, CHILDREN[0][1]))
            _wait_for_text(page, MARKERS[CHILDREN[0][1]])
            child_folds = page.locator("#details .execweave-agent-older").count()
        finally:
            browser.close()

    assert [value.strip() for value in newest] == [SECOND_QUESTION, SECOND_ANSWER], (
        "the open round must hold the question and the answer that belong together"
    )
    assert len(folds) == 1, f"the earlier round should fold to one line: {folds}"
    assert "spawn four agents" in folds[0], f"the fold must name its own round: {folds[0]}"
    assert [value.strip() for value in older][0] == "spawn four agents"
    assert ALL_MARKERS <= {marker for marker in ALL_MARKERS if marker in older[1]}, (
        "the earlier round lost the answer it was given"
    )
    assert child_folds == 0, "a subagent with one round must not grow a fold"


def test_a_crowded_type_folds_its_older_nodes_instead_of_dropping_them(tmp_path: Path) -> None:
    """A run that edits a codebase produces one file node per path.

    Drawing all of them buries the graph, and hiding them loses evidence. Past a
    per-type budget the most recent stay drawn and the older ones collapse into one
    node that says how many it holds and lists them, the same way an agent's older
    rounds fold rather than disappear.
    """
    from execweave.viewer_projection import write_graph_html

    total = 40
    graph = build_run(tmp_path, files=total)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            drawn = page.eval_on_selector_all(".node", "nodes=>nodes.map(n=>n.dataset.id)")
            drawn_files = [value for value in drawn if str(value).startswith("file:")]
            folds = [value for value in drawn if "folded" in str(value)]
            assert len(folds) == 1, f"expected one fold node, drew {folds}"
            _click_id(page, folds[0])
            labels, bodies = _cards(page)
        finally:
            browser.close()

    assert drawn_files, "every file node was folded away; the newest must stay drawn"
    assert len(drawn_files) < total, "nothing folded, so the budget did not apply"
    held = dict(zip(labels, bodies))
    assert "Folded" in held and "Holding" in held, f"the fold node says nothing: {labels}"
    listed = [line for line in held["Holding"].splitlines() if line.strip()]
    assert len(drawn_files) + len(listed) == total, (
        f"{len(drawn_files)} drawn plus {len(listed)} folded does not account for {total}"
    )
    assert "src/module_" in listed[0], f"the fold must name what it holds: {listed[0]}"

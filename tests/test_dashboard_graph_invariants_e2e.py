"""Every provider's dashboard must draw a graph a user can follow.

For each provider-shaped recording in ``dashboard_provider_runs`` -- CLI agents
through their hook CLIs, a user's own Python script through the proxy recorder or
an SDK / runtime / gateway adapter (commercial APIs and a local Ollama alike), and
framework agents inside ``execweave record`` -- both the final viewer.html and the
live dashboard mid-run must satisfy the same contract:

- every drawn node is reachable from the one root; nothing floats on its own;
- a provider session hangs off root -> model -> session, or straight off the root
  when no model was observed; a model switched inside a session is another model
  node from the root into that same session, and a new provider session gets its
  own model node(s);
- no self-loops and no duplicate edges; an edge is drawn right to left (or within
  one column) exactly when the projection marked it as feedback, so every other
  edge flows left to right;
- neither an edge's path nor its label runs through a node or another label.

Direction is judged from where the page actually draws each node, not from any
internal layout attribute. The contract itself lives in
``scripts/acceptance/graph_topology.py`` so the real-provider acceptance journeys
judge their pages by the same rules; this test adds what each fixture is known to
contain (which models feed which session, and the nodes the user came to see).

All violations of one page are collected and reported together.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from dashboard_provider_runs import CASES, ProviderRun, build, live_inputs
from test_viewer_agent_isolation_e2e import _browser, _launch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance import graph_topology  # noqa: E402

pytestmark = pytest.mark.viewer_e2e

SURFACES = ("final", "live")


def _violations(run: ProviderRun, page: dict[str, Any]) -> list[str]:
    case = run.case
    problems, feeds = graph_topology.violations(page)
    if not graph_topology.feeds_match(feeds, case.feeds):
        problems.append(
            f"sessions are fed by {graph_topology.describe_feeds(feeds)}, "
            f"expected {graph_topology.describe_feeds(case.feeds)}"
        )
    # The things the user came to see are on the canvas.
    names = {(node["type"], node["name"]) for node in page["display"]["nodes"]}
    missing = sorted(set(run.extra["required"]) - names)
    if missing:
        problems.append(f"missing nodes {missing}")
    return problems


def _inspect(browser: Any, run: ProviderRun, surface: str, directory: Path) -> tuple[dict[str, Any], list[str]]:
    from execweave import live as live_module
    from execweave import live_core

    errors: list[str] = []
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)
    server = thread = None
    try:
        if surface == "final":
            viewer = directory / "viewer.html"
            viewer.write_text(live_core.render_graph_html(run.graph), encoding="utf-8")
            page.goto(viewer.as_uri())
        else:
            session_id, event_path, semantic_path = live_inputs(run, directory / "live")
            state = live_module._LiveState(session_id, event_path, semantic_path)
            state.live_update(-1)
            token = "dashboard-invariants"
            server = live_module._LocalThreadingHTTPServer(
                ("127.0.0.1", 0), live_module._handler_factory(state, token)
            )
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            page.set_extra_http_headers({"X-ExecWeave-Token": token})
            page.goto(f"http://{host}:{port}/")
        graph_topology.settle(page)
        return graph_topology.collect(page), errors
    finally:
        page.close()
        if server is not None:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


@pytest.fixture(scope="module")
def chromium() -> Any:
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture(scope="module")
def recorded(tmp_path_factory: pytest.TempPathFactory) -> Any:
    runs: dict[str, ProviderRun] = {}

    def get(case_name: str) -> ProviderRun:
        if case_name not in runs:
            case = next(case for case in CASES if case.name == case_name)
            runs[case_name] = build(case, tmp_path_factory.mktemp(case_name))
        return runs[case_name]

    return get


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("case_name", [case.name for case in CASES])
def test_every_provider_dashboard_draws_a_connected_readable_flow(
    chromium: Any, recorded: Any, case_name: str, surface: str, tmp_path: Path
) -> None:
    run = recorded(case_name)
    page, errors = _inspect(chromium, run, surface, tmp_path)
    problems = errors + _violations(run, page)
    assert not problems, f"{case_name} ({surface}):\n  " + "\n  ".join(problems) + (
        "\n\ndrawn graph:\n" + json.dumps(page["display"], indent=1, sort_keys=True)
    )

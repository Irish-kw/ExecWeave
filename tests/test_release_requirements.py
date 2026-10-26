"""Release-blocker contracts: local integrity, reader provenance, handoff warnings."""
from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

import pytest

from execweave.integrity_cli import main as integrity_main
from execweave.session_summary import SessionSummary
from execweave.validate import validate_event_stream
from execweave.viewer_run_assessment import RUN_ASSESSMENT_JS, RUN_ASSESSMENT_CSS
from test_observation_diagnostics import _finish, _handoff, _stream


@pytest.mark.parametrize("schemas", [
    ["0.3", "0.3"], ["0.2", "0.3"], ["0.3", "0.2"],
])
def test_release_future_schema_has_named_error(
    tmp_path: Path, schemas: list[str],
) -> None:
    path = tmp_path / "events.jsonl"
    _stream(path, schemas)
    result = validate_event_stream(path)
    assert result.valid is False
    assert result.to_dict()["reader"]["version"] == version("execweave")
    assert any("unsupported_schema_version" in error
               and "0.3" in error and "0.2" in error for error in result.errors)


def test_release_missing_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _stream(path, ["0.2", "0.2"])
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    del lines[0]["schema_version"]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    result = validate_event_stream(path)
    assert result.valid is False
    assert any("unsupported_schema_version" in err for err in result.errors)


def test_release_viewer_rejects_graph_with_future_source_schema(tmp_path: Path) -> None:
    from execweave.graph_ops import load_graph

    graph = {
        "graph_schema_version": "0.2",
        "session_id": "fixed",
        "source_schema_versions": ["0.3"],
        "nodes": [{"id": "agent:reviewer", "type": "agent"}],
        "edges": [],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported_schema_version"):
        load_graph(path)

    graph["source_schema_versions"] = ["0.2"]
    path.write_text(json.dumps(graph), encoding="utf-8")
    assert load_graph(path)["source_schema_versions"] == ["0.2"]


def test_release_reader_metadata_exists_even_when_invalid(tmp_path: Path) -> None:
    invalid = validate_event_stream(tmp_path / "missing.jsonl")
    assert invalid.to_dict()["reader"] == {"name": "execweave", "version": version("execweave")}


def test_release_handoff_diagnostic_is_uncertainty_not_delivery_failure() -> None:
    summary = SessionSummary()
    summary.observe(_handoff("id-1", "MESSAGE_SENT"))
    summary.observe(_handoff("id-1", "MESSAGE_RECEIVED"))
    summary.observe(_handoff("id-2", "MESSAGE_SENT"))
    summary.observe(_finish())
    delivery = summary.observation["message_delivery"]
    assert delivery["diagnostics"] == [{
        "kind": "message_receive_not_observed",
        "message_id": "id-2",
        "sender_id": "agent:engineer",
        "recipient_id": "agent:reviewer",
        "delivery_status": "receive_not_observed",
        "delivery_failure_proven": False,
    }]
    assert summary.observation["state"] == "observation_incomplete"
    assert delivery["delivery_failure_proven"] is False


def test_release_top_level_handoff_marker_and_click_contract() -> None:
    assert "execweave-handoff-alerts" in RUN_ASSESSMENT_JS
    assert "receive not observed" in RUN_ASSESSMENT_JS
    assert "line.onclick=" in RUN_ASSESSMENT_JS
    assert "api.selectNode(recipient.id)" in RUN_ASSESSMENT_JS
    assert "data-warning" in RUN_ASSESSMENT_CSS
    assert ".edge.handoff-unconfirmed" in RUN_ASSESSMENT_CSS


def test_release_local_verification_reader_and_no_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "run"
    root.mkdir()
    (root / "graph.json").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    assert integrity_main(["seal", str(root)]) == 0
    sealed = json.loads(capsys.readouterr().out)
    assert sealed["malicious_writer_resistance"] is False
    assert "external_anchor_state" not in sealed

    assert integrity_main(["verify", str(root)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True
    assert verified["local_integrity_valid"] is True
    assert verified["malicious_writer_resistance"] is False
    assert verified["reader"] == {"name": "execweave", "version": version("execweave")}

    (root / "graph.json").write_text("changed", encoding="utf-8")
    assert integrity_main(["verify", str(root)]) == 1
    tampered = json.loads(capsys.readouterr().out)
    assert tampered["valid"] is False


@pytest.mark.parametrize("suffix", [
    "md", "zh-TW.md", "zh-CN.md", "de.md", "fr.md", "ja.md", "ko.md", "ru.md",
])
def test_release_local_only_docs_and_downgrade_parity(suffix: str) -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / (
        "run-integrity." + suffix)
    body = path.read_text(encoding="utf-8")
    for marker in (
        "<!-- ew:trust:local-only -->",
        "<!-- ew:trust:privileged -->",
        "<!-- ew:compat:no-downgrade -->",
    ):
        assert marker in body
        tail = body.split(marker, 1)[1].split("\n", 3)[0:3]
        assert any(part.strip() for part in tail)
    assert "v0.8.34" in body
    assert "v0.8.35" in body
    for removed in ("--anchor-github", "--expected-manifest-body-sha256",
                    "EXECWEAVE_INTEGRITY_GITHUB_TOKEN"):
        assert removed not in body


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("missing_receipt", [True, False], ids=["missing-receipt", "receipt-observed"])
def test_release_handoff_and_workflow_controls_keep_first_view_position(
    missing_receipt: bool,
) -> None:
    """Both the handoff banner and workflow controls must precede the canvas."""
    import os
    from playwright.sync_api import sync_playwright
    from execweave.dashboard_shell import render_static_dashboard_html

    engineer = "agent:rolesdemo:session:Engineer"
    reviewer = "agent:rolesdemo:session:Reviewer"
    graph = {
        "graph_schema_version": "0.2", "session_id": "rolesdemo",
        "nodes": [
            {"id": engineer, "type": "agent", "name": "Engineer"},
            {"id": reviewer, "type": "agent", "name": "Reviewer"},
        ],
        "edges": [{"id": "send", "source": engineer, "target": reviewer,
                   "relation": "MESSAGE_SENT", "attributes": {"message_id": "m2"}}],
        "session_outcome": {"state": "observation_incomplete", "recorder_finished": True},
        "observation_assessment": {"message_delivery": {
            "unconfirmed_count": 1 if missing_receipt else 0,
            "delivery_failure_proven": False,
            "unconfirmed": ([{"message_id": "m2", "sender_id": engineer,
                            "recipient_id": reviewer, "state": "receive_not_observed"}]
                            if missing_receipt else []),
        }},
    }
    with sync_playwright() as playwright:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = playwright.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.set_content(render_static_dashboard_html(graph))
            workflow = page.locator("#execweave-workflow-controls")
            workflow.wait_for(state="visible")
            toolbar = page.locator("#graph-panel > .panel-bar").bounding_box()
            workflow_box = workflow.bounding_box()
            graph_wrap = page.locator("#wrap").bounding_box()
            assert toolbar and workflow_box and graph_wrap
            # Regression: this row must never be auto-placed below #wrap.
            assert workflow_box["y"] >= toolbar["y"] + toolbar["height"] - 1
            assert workflow_box["y"] + workflow_box["height"] <= graph_wrap["y"] + 1
            assert workflow_box["y"] < 200
            alert = page.locator("#execweave-handoff-alerts .execweave-handoff-alert")
            if missing_receipt:
                alert.wait_for(state="visible")
                alert_box = alert.bounding_box()
                assert alert_box
                assert alert_box["y"] >= toolbar["y"] + toolbar["height"] - 1
                assert alert_box["y"] + alert_box["height"] <= workflow_box["y"] + 1
                assert alert_box["y"] < 200
                assert "Engineer → Reviewer — receive not observed" in alert.inner_text()
                alert.click()
                assert "Reviewer" in page.locator("#details").inner_text()
                assert page.locator('.node[data-warning="receive-not-observed"]').count() == 1
                assert page.locator(".edge.handoff-unconfirmed").count() == 1
                # Switch modes and redraw the SVG without new telemetry; the
                # banner and graph warnings must remain synchronized.
                for mode in ("workflow", "all"):
                    page.locator("#execweave-workflow-controls select").select_option(mode)
                    page.wait_for_function(
                        "() => document.querySelectorAll('.node[data-warning=\\\"receive-not-observed\\\"]').length===1 && "
                        "document.querySelectorAll('.edge.handoff-unconfirmed').length===1"
                    )
                page.locator("#file-graph-filter").select_option("all")
                page.wait_for_function(
                    "() => document.querySelectorAll('.edge.handoff-unconfirmed').length===1"
                )
            else:
                assert alert.count() == 0
                assert page.locator('#execweave-handoff-alerts').is_hidden()
                assert page.locator('.node[data-warning="receive-not-observed"]').count() == 0
                assert page.locator(".edge.handoff-unconfirmed").count() == 0
            assert errors == []
        finally:
            browser.close()

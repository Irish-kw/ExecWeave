"""#110 follow-up: bounded inventory and native-browser agent evidence regressions."""
from __future__ import annotations

import os

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.session_summary import SessionSummary
from test_issue110_observation_diagnostics import _finish, _handoff


def test_bounded_inventory_does_not_claim_exact_zero_after_overflow() -> None:
    summary = SessionSummary()
    for index in range(10_000):
        summary.observe(_handoff(f"received-{index}", "MESSAGE_RECEIVED"))
    exact = summary.observation["message_delivery"]
    assert exact["unconfirmed_count"] == 0
    assert exact["unconfirmed_count_lower_bound"] == 0
    assert exact["inventory_truncated"] is False

    summary.observe(_handoff("overflow-sent", "MESSAGE_SENT"))
    summary.observe(_finish())
    assessment = summary.observation
    delivery = assessment["message_delivery"]
    assert delivery["unconfirmed_count"] is None
    assert delivery["unconfirmed_count_lower_bound"] == 0
    assert delivery["inventory_truncated"] is True
    assert delivery["truncated"] is True
    assert delivery["delivery_failure_proven"] is False
    assert "message_delivery_inventory_truncated" in assessment["reasons"]
    # An unknown inventory is not evidence of any particular missing receipt.
    assert "message_receive_not_observed" not in assessment["reasons"]


def test_bounded_inventory_retains_known_unconfirmed_lower_bound() -> None:
    summary = SessionSummary()
    summary.observe(_handoff("known-missing", "MESSAGE_SENT"))
    for index in range(9_999):
        summary.observe(_handoff(f"received-{index}", "MESSAGE_RECEIVED"))
    summary.observe(_handoff("overflow-sent", "MESSAGE_SENT"))
    summary.observe(_finish())
    assessment = summary.observation
    delivery = assessment["message_delivery"]
    assert delivery["unconfirmed_count"] is None
    assert delivery["unconfirmed_count_lower_bound"] == 1
    assert delivery["unconfirmed"][0]["message_id"] == "known-missing"
    assert delivery["inventory_truncated"] is True
    assert delivery["delivery_failure_proven"] is False
    assert {"message_receive_not_observed", "message_delivery_inventory_truncated"} <= set(
        assessment["reasons"]
    )


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("ambiguous_name", [False, True])
def test_browser_response_preview_prompt_and_unambiguous_handoff(ambiguous_name: bool) -> None:
    from playwright.sync_api import sync_playwright

    engineer = "agent:rolesdemo:session:Engineer"
    reviewer = "agent:rolesdemo:session:Reviewer"
    sibling = "agent:rolesdemo:session:OtherReviewer"
    prompt = "You are a code reviewer. Check the Engineer patch."
    nodes = [
        {"id": engineer, "type": "agent", "name": "Engineer",
         "attributes": {"framework": "rolesdemo", "conversation_scope": "framework_agent"}},
        {"id": reviewer, "type": "agent", "name": "Reviewer",
         "attributes": {"framework": "rolesdemo", "conversation_scope": "framework_agent"}},
        {"id": sibling, "type": "agent", "name": "OtherReviewer",
         "attributes": {"framework": "rolesdemo", "conversation_scope": "framework_agent"}},
    ]
    if ambiguous_name:
        nodes.append({
            "id": "agent:rolesdemo:another-session:Engineer",
            "type": "agent", "name": "Engineer",
            "attributes": {"framework": "rolesdemo", "conversation_scope": "framework_agent"},
        })
    graph = {
        "graph_schema_version": "0.2", "session_id": "session",
        "nodes": nodes, "edges": [],
        "observation_assessment": {"message_delivery": {
            "unconfirmed_count": 1, "truncated": False,
            "delivery_failure_proven": False,
            "unconfirmed": [{"message_id": "msg-2", "sender_id": engineer,
                             "recipient_id": reviewer, "state": "receive_not_observed"}],
        }},
    }
    entries = [
        {"source_id": reviewer, "provider": "rolesdemo",
         "relation": "HAS_MODEL_CONTENT", "content_kind": "rolesdemo.model_request",
         "conversation_preview": None},
        {"source_id": reviewer, "provider": "rolesdemo",
         "relation": "HAS_MODEL_CONTENT", "content_kind": "rolesdemo.model_response",
         "conversation_preview": {"agent_path": "Reviewer", "messages": [
             {"kind": "model_request", "phase": "request", "text": prompt,
              "observed": None, "timestamp": "2026-10-10T18:00:00Z"},
             {"kind": "agent_message", "phase": "sent", "message_id": "msg-2",
              "sender": "Engineer", "recipient": "Reviewer", "text": "Review this.",
              "timestamp": "2026-10-10T18:00:01Z"},
         ]}},
        {"source_id": sibling, "provider": "rolesdemo",
         "relation": "HAS_MODEL_CONTENT", "content_kind": "rolesdemo.model_response",
         "conversation_preview": {"agent_path": "OtherReviewer", "messages": [
             {"kind": "model_request", "phase": "request",
              "text": "SIBLING PRIVATE PROMPT", "timestamp": "2026-10-10T18:00:00Z"},
         ]}},
    ]
    with sync_playwright() as playwright:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = playwright.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(graph, conversation_entries=entries))
            page.wait_for_selector(".node")
            page.evaluate("(id) => window.__execweaveCore.selectNode(id)", reviewer)
            panel = page.locator("#details").inner_text()
            assert prompt in panel
            assert "SIBLING PRIVATE PROMPT" not in panel
            assert "incoming handoff" in panel.lower()
            summaries = page.locator(".execweave-message-history summary").all_inner_texts()
            assert len(summaries) == 1
            if ambiguous_name:
                assert "Delivery not verified" in summaries[0]
                assert "Receive not observed" not in summaries[0]
            else:
                assert "Receive not observed" in summaries[0]
            assert errors == []
        finally:
            browser.close()

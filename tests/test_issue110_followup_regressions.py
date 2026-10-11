"""#110 follow-up: bounded inventory and native-browser agent evidence regressions."""
from __future__ import annotations

import os
import re
from pathlib import Path

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
@pytest.mark.parametrize("prompt_present", [True, False])
def test_browser_response_preview_prompt_and_unambiguous_handoff(
    ambiguous_name: bool, prompt_present: bool
) -> None:
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
         "conversation_preview": {"agent_path": "/root", "is_root": True, "messages": [
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
    if not prompt_present:
        # A genuinely absent prompt must stay absent, even if another agent has one.
        entries[1]["conversation_preview"]["messages"] = [
            item for item in entries[1]["conversation_preview"]["messages"]
            if item.get("kind") != "model_request"
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
            round_prompt = page.locator(
                ".execweave-agent-rounds .execweave-agent-round "
                ".execweave-agent-body"
            ).first.inner_text()
            if prompt_present:
                assert round_prompt == prompt
                assert panel.count(prompt) == 1
                assert "PROMPT\\nNot observed." not in panel
            else:
                assert round_prompt == "Not observed."
                assert prompt not in panel
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


# Locale-specific, security-critical statements are intentionally checked as
# translated text. Token-only checks cannot detect a deleted trust-boundary
# warning or an English fallback substituted into a translated README.
_ISSUE110_LOCALE_CLAIMS = {
    "README.md": (
        "`execution_state=succeeded` is not the same as complete observation.",
        "**Configured does not mean evidence was delivered.**",
        "The live dashboard no longer puts its API credential in `?t=...`.",
    ),
    "README.zh-TW.md": (
        "`execution_state=succeeded` 不代表完整觀測，也不等於經過獨立任務驗證。",
        "**完成設定不等於已送出證據**",
        "Live dashboard 不再把 API credential 放進 `?t=...`。",
    ),
    "README.de.md": (
        "es installiert oder überschreibt keine Hooks.",
        "ohne sudo.",
        "`execution_state=succeeded` beweist weder eine vollständige Beobachtung noch eine unabhängige Aufgabenvalidierung.",
        "**Konfiguriert bedeutet nicht, dass Beobachtungsdaten eingegangen sind.**",
        "Das Live-Dashboard überträgt keine API-Zugangsdaten mehr über `?t=...`.",
    ),
    "README.fr.md": (
        "Une politique de capture invalide déclenche un repli sécurisé vers metadata-only aux frontières des enregistreurs automatiques.",
        "L’absence de preuve de réception et l’observation incomplète sont enregistrées indépendamment du code de sortie.",
        "`execution_state=succeeded` ne prouve ni une observation complète ni une validation indépendante de la tâche.",
        "**Un hook configuré ne prouve pas la réception des preuves.**",
        "Le dashboard Live ne place plus d’identifiant API dans `?t=...`.",
    ),
    "README.ja.md": (
        "表示される URL に credential は含まれません。",
        "`execution_state=succeeded` は観測の完全性やタスクの独立した検証を証明しません。",
        "**設定済みであることは証拠が届いたことを意味しません。**",
        "Live dashboard の URL に API credential を `?t=...` として含めることはありません。",
    ),
    "README.ko.md": (
        "`execution_state=succeeded`는 관측의 완전성이나 작업의 독립적인 검증을 의미하지 않습니다.",
        "**구성 완료가 증거 전달을 의미하지는 않습니다.**",
        "Live dashboard URL에는 더 이상 API credential이 `?t=...` 형태로 포함되지 않습니다.",
    ),
    "README.ru.md": (
        "Браузер отправляет одноразовый pairing code в теле POST",
        "`execution_state=succeeded` не доказывает полноту наблюдения или независимую проверку задачи.",
        "**Настроенный hook не доказывает получение данных наблюдения.**",
        "Live dashboard больше не передаёт API credential через `?t=...`.",
    ),
    "README.zh-CN.md": (
        "`execution_state=succeeded` 不代表观察完整，也不等于经过独立的任务验证。",
        "**完成配置不等于已收到证据。**",
        "Live dashboard 不再将 API credential 放在 `?t=...` 中。",
    ),
}


@pytest.mark.parametrize("locale", sorted(_ISSUE110_LOCALE_CLAIMS))
def test_issue110_readme_provider_privacy_parity(locale: str) -> None:
    """Catch security-guide omissions and untranslated fallback across locales."""
    readme = (Path(__file__).resolve().parents[1] / locale).read_text(encoding="utf-8")
    # Ignore HTML comments: invisible guidance must not satisfy security checks.
    readme = re.sub(r"<!--.*?-->", "", readme, flags=re.DOTALL)
    assert readme.count("execweave live --open -- codex") == 1, locale
    for claim in _ISSUE110_LOCALE_CLAIMS[locale]:
        assert claim in readme, (locale, claim)
    for required in (
        "docs/observation-integrity.md",
        "--metadata-only",
        "--capture-content",
        "X-ExecWeave-Token",
        "HttpOnly; SameSite=Strict",
        "0.8.35",
        "execweave hooks install antigravity",
        "execweave hooks status antigravity",
    ):
        assert required in readme, (locale, required)

    # The original unlocalized sentence includes Markdown code spans.
    # Match the actual bytes so this guard cannot silently miss it again.
    if locale not in ("README.md", "README.zh-TW.md"):
        assert (
            "`observation-negative/graph.json` and `finalization.json`: "
            "`execution_state=succeeded` does not prove observation "
            "completeness or task validation."
        ) not in readme, locale

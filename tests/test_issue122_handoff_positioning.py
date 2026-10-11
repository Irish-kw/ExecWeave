"""Release positioning: documented sender/recipient uncertainty, not delivery-failure proof."""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

OPENING_SUBSTRINGS = {
    "README.md": ("In multi-role agent workflows", "matching observed receive event"),
    "README.zh-TW.md": ("在多角色 Agent 工作流程中", "未觀察到對應接收事件"),
    "README.zh-CN.md": ("在多角色 Agent 工作流中", "未观察到对应接收事件"),
    "README.de.md": ("In Multi-Rollen-Agentenabläufen", "kein passendes Empfangsereignis"),
    "README.fr.md": ("Dans les flux d’agents à plusieurs rôles", "pas d’événement de réception correspondant"),
    "README.ja.md": ("複数ロールの Agent ワークフローでは", "対応する受信イベントが観測されない"),
    "README.ko.md": ("여러 역할의 Agent 워크플로에서", "수신 이벤트가 관측되지 않은"),
    "README.ru.md": ("В многоагентных сценариях с несколькими ролями", "событие получения не наблюдалось"),
}


@pytest.mark.parametrize("readme,claims", OPENING_SUBSTRINGS.items())
def test_eight_readme_openings_advertise_observed_handoff_without_overclaim(
    readme: str, claims: tuple[str, str],
) -> None:
    text = (ROOT / readme).read_text(encoding="utf-8")
    first_screen = "\n".join(text.splitlines()[:35])
    for claim in claims:
        assert claim in first_screen, (readme, claim)
    assert "message_receive_not_observed" in first_screen
    assert "`graph.json`" in first_screen
    assert first_screen.count("message_receive_not_observed") == 1
    # Each locale has an explicit qualified conclusion, not a claim of
    # independently proven failed delivery. Do not assert this via token-only
    # markers: the translated text above must remain present.


def test_project_summary_mentions_handoff_roles_and_observation_limits() -> None:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    summary = project["description"]
    assert project["name"] == "execweave"
    assert project["version"] == "0.8.35"
    assert "sender/recipient handoffs" in summary
    assert "no observed receive" in summary
    assert "graph.json" in summary
    assert len(summary) <= 160
    assert not re.search(r"\\b(tamper-proof|forensic proof|failed delivery)\\b", summary, re.I)

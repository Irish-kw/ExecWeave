from pathlib import Path

from execweave.agent_topology import COMPLETENESS_ROUTING_ONLY
from execweave.conversation_preview import conversation_preview

FIXTURES = Path(__file__).parent / "fixtures" / "codex_multi_agent"
SESSION_ID = "01a04cea-0a14-71e0-8c32-4aeafda0f039"
CHILDREN = {
    "01a04cea-67b2-7683-9f6b-cd644497b862": "/root/rain_forecast",
    "01a04cea-7a7b-7620-9485-3c9ef4e0b343": "/root/official_alerts",
    "01a04cea-8b3c-7182-8d14-2627b03d8c0d": "/root/hydrology",
    "01a04cea-fe38-7cf3-bf61-ff7ebf2de646": "/root/forecast_consensus",
}


def test_routing_only_codex_children_keep_their_own_provider_native_ids() -> None:
    """A child projected from the root rollout must never inherit the root native id."""
    root_source = {
        "id": "agent:OpenAI Codex",
        "type": "agent",
        "attributes": {"session_id": SESSION_ID},
    }
    preview = conversation_preview(
        FIXTURES / "rollout-main.jsonl",
        content_kind="codex.conversation_transcript.main",
        provider="codex",
        source=root_source,
    )
    assert preview is not None
    assert preview["agent_path"] == "/root"
    assert preview["provider_native_id"] == SESSION_ID

    derived = {
        child["agent_path"]: child
        for child in preview.get("derived_agent_previews") or []
    }
    assert set(derived) == set(CHILDREN.values())

    for agent_id, path in CHILDREN.items():
        child = derived[path]
        assert child["conversation_completeness"] == COMPLETENESS_ROUTING_ONLY
        assert child["thread_id"] == agent_id
        assert child["provider_native_id"] == agent_id
        assert child["provider_native_id"] != SESSION_ID

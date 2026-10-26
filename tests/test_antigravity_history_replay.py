from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from execweave.conversation_archive import antigravity_conversation_archive_events
from execweave.conversation_records import conversation_record_entries
from execweave.content_store import FullFidelityContentStore
from execweave.graph import GraphAccumulator
from execweave.viewer_projection import write_graph_html


_CONVERSATION_ID = "sus-001-three-rounds"
_AGENT_ID = f"agent:antigravity:conversation:{_CONVERSATION_ID}"


def _transcript_path(tmp_path: Path) -> Path:
    path = (
        tmp_path
        / "antigravity-cli"
        / "brain"
        / _CONVERSATION_ID
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _round(step_index: int, label: str) -> list[dict[str, object]]:
    return [
        {
            "step_index": step_index,
            "source": "USER",
            "type": "USER_MESSAGE",
            "content": f"question {label}",
        },
        {
            "step_index": step_index + 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "content": f"answer {label}",
        },
    ]


def _write_snapshot(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _apply_snapshot(
    graph: GraphAccumulator,
    store: FullFidelityContentStore,
    transcript: Path,
    records: list[dict[str, object]],
    snapshot_index: int,
) -> None:
    _write_snapshot(transcript, records)
    events = antigravity_conversation_archive_events(
        {
            "conversationId": _CONVERSATION_ID,
            "transcriptPath": str(transcript),
        },
        store=store,
        timestamp=f"2026-08-31T14:0{snapshot_index}:00Z",
    )
    assert len(events) == 1
    event = dict(events[0])
    event["sequence"] = snapshot_index * 100
    graph.apply(event)


def _messages(graph: GraphAccumulator, run_root: Path) -> list[dict[str, object]]:
    entries = conversation_record_entries(graph.to_dict(), run_root)
    previews = [
        entry["conversation_preview"]
        for entry in entries
        if entry.get("provider") == "antigravity"
        and isinstance(entry.get("conversation_preview"), dict)
    ]
    assert len(previews) == 1
    messages = previews[0].get("messages")
    assert isinstance(messages, list)
    return messages


def test_antigravity_cumulative_stop_snapshots_preserve_three_round_history(
    tmp_path: Path,
) -> None:
    """SUS-001 replay: cumulative Stop snapshots must not re-identify old turns."""
    transcript = _transcript_path(tmp_path)
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    graph = GraphAccumulator(session_id="sus-001", source_path=run_root / "events.jsonl")
    records: list[dict[str, object]] = []

    expected_texts: list[str] = []
    for snapshot_index, label in enumerate(("A", "B", "C"), start=1):
        records.extend(_round(snapshot_index * 10, label))
        expected_texts.extend((f"question {label}", f"answer {label}"))
        _apply_snapshot(graph, store, transcript, records, snapshot_index)

        messages = _messages(graph, run_root)
        assert [message.get("text") for message in messages] == expected_texts
        assert len(messages) == snapshot_index * 2


@pytest.mark.viewer_e2e
def test_antigravity_history_survives_new_stop_and_manual_fold_state_in_chromium(
    tmp_path: Path,
) -> None:
    """Provider-shaped SUS-001 replay through the shipped dashboard in Chromium."""
    sync_api = pytest.importorskip("playwright.sync_api")

    transcript = _transcript_path(tmp_path)
    run_root = tmp_path / "run-browser"
    store = FullFidelityContentStore(run_root)
    graph = GraphAccumulator(
        session_id="sus-001-browser",
        source_path=run_root / "events.jsonl",
    )
    records: list[dict[str, object]] = []

    for snapshot_index, label in enumerate(("A", "B"), start=1):
        records.extend(_round(snapshot_index * 10, label))
        _apply_snapshot(graph, store, transcript, records, snapshot_index)

    viewer = run_root / "viewer.html"
    write_graph_html(graph.to_dict(), viewer)

    records.extend(_round(30, "C"))
    _apply_snapshot(graph, store, transcript, records, 3)
    updated_entries = conversation_record_entries(graph.to_dict(), run_root)

    required = os.environ.get("EXECWEAVE_E2E_REQUIRED", "").strip().lower() not in {
        "",
        "0",
        "false",
    }
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:  # noqa: BLE001 - browser availability is environmental
            if required:
                pytest.fail(f"Chromium is required for this release gate: {error}")
            pytest.skip(f"Chromium is not available: {error}")

        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            clicked = page.eval_on_selector_all(
                ".node",
                """(nodes,id)=>{const node=nodes.find(item=>item.dataset.id===id);
                if(!node)return false;
                node.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true}""",
                _AGENT_ID,
            )
            assert clicked, "the Antigravity conversation agent must render in the graph"
            page.wait_for_function(
                "()=>(document.getElementById('details')?.innerText||'').includes('question B')"
            )

            old_a = page.locator("#details .execweave-agent-older").filter(
                has_text="question A"
            )
            assert old_a.count() == 1
            assert page.locator("#details .execweave-agent-older").count() == 1
            assert not old_a.first.evaluate("node=>node.open")
            old_a.first.locator("summary").click()
            assert old_a.first.evaluate("node=>node.open")
            assert "answer A" in old_a.first.inner_text()

            page.evaluate(
                "payload=>window.__execweaveAgentPanel.setEntries(payload)",
                updated_entries,
            )
            page.wait_for_function(
                "()=>(document.getElementById('details')?.innerText||'').includes('question C')"
            )

            folds = page.locator("#details .execweave-agent-older")
            assert folds.count() == 2
            old_a = folds.filter(has_text="question A")
            old_b = folds.filter(has_text="question B")
            assert old_a.count() == 1
            assert old_b.count() == 1
            assert old_a.first.evaluate("node=>node.open"), (
                "a newly archived Stop snapshot closed a historical round the user opened"
            )
            assert not old_b.first.evaluate("node=>node.open")

            current = page.locator(
                "#details .execweave-agent-rounds > .execweave-agent-round"
            )
            assert current.count() == 1
            assert "question C" in current.first.inner_text()
            assert "answer C" in current.first.inner_text()

            page.evaluate(
                """()=>{window.__sus001Fold=
                [...document.querySelectorAll('#details .execweave-agent-older')]
                .find(node=>node.innerText.includes('question A'))}"""
            )
            page.evaluate(
                "payload=>window.__execweaveAgentPanel.setEntries(payload)",
                updated_entries,
            )
            assert page.evaluate(
                """()=>window.__sus001Fold===
                [...document.querySelectorAll('#details .execweave-agent-older')]
                .find(node=>node.innerText.includes('question A'))"""
            ), "an identical polling payload rebuilt the historical fold"
            assert old_a.first.evaluate("node=>node.open")

            old_a.first.locator("summary").click()
            assert not old_a.first.evaluate("node=>node.open")
            page.evaluate(
                "payload=>window.__execweaveAgentPanel.setEntries(payload)",
                updated_entries,
            )
            assert not page.locator("#details .execweave-agent-older").filter(
                has_text="question A"
            ).first.evaluate("node=>node.open")
        finally:
            browser.close()

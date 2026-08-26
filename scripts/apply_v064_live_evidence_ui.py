from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"{path}: expected patch anchor not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_live() -> None:
    path = Path("src/execweave/live.py")
    old = '''    def snapshot(self) -> dict[str, object]:
        with self._lock:
            if not self._finished:
                self._refresh_incremental_locked()
            payload = self._snapshot_from_accumulator_locked()
            payload["live_finished"] = self._finished
            payload["live_evidence_counts"] = {
                "os_runtime": self._runtime_event_count,
                "specialized": self._specialized_event_count,
            }
            payload["live_specialized_provisional"] = (
                self._specialized_event_count > 0 and not self._finished
            )
            return payload
'''
    new = '''    def _evidence_metadata_locked(self) -> dict[str, object]:
        return {
            "live_evidence_counts": {
                "os_runtime": self._runtime_event_count,
                "specialized": self._specialized_event_count,
            },
            "live_specialized_provisional": (
                self._specialized_event_count > 0 and not self._finished
            ),
        }

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            if not self._finished:
                self._refresh_incremental_locked()
            payload = self._snapshot_from_accumulator_locked()
            payload["live_finished"] = self._finished
            payload.update(self._evidence_metadata_locked())
            return payload
'''
    replace_once(path, old, new)

    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '"graph": self._snapshot_from_accumulator_locked(),\n                    "live_finished": self._finished,',
        '"graph": self._snapshot_from_accumulator_locked(),\n                    **self._evidence_metadata_locked(),\n                    "live_finished": self._finished,',
    )
    text = text.replace(
        '**counts,\n                    "live_finished": self._finished,',
        '**counts,\n                    **self._evidence_metadata_locked(),\n                    "live_finished": self._finished,',
    )
    text = text.replace(
        '**counts,\n                "live_finished": self._finished,',
        '**counts,\n                **self._evidence_metadata_locked(),\n                "live_finished": self._finished,',
    )
    if text.count("**self._evidence_metadata_locked()") != 4:
        raise RuntimeError("live.py: expected four live_update evidence metadata insertions")
    path.write_text(text, encoding="utf-8")


def patch_view() -> None:
    path = Path("src/execweave/live_view.py")
    replace_once(
        path,
        '#status{border:1px solid var(--border);border-radius:999px;padding:3px 8px;color:var(--causal)}#stats{color:var(--muted);white-space:nowrap}',
        '#status{border:1px solid var(--border);border-radius:999px;padding:3px 8px;color:var(--causal)}#stats{color:var(--muted);white-space:nowrap}#evidence{border:1px solid var(--border);border-radius:999px;padding:3px 8px;color:var(--muted);white-space:nowrap}#evidence.provisional{color:var(--noncausal);border-color:var(--noncausal)}',
    )
    replace_once(
        path,
        '<header><strong>ExecWeave Live</strong><span id="status">LIVE</span><span id="stats">Waiting for events…</span><input id="search"',
        '<header><strong>ExecWeave Live</strong><span id="status">LIVE</span><span id="stats">Waiting for events…</span><span id="evidence">OS 0 · specialized 0</span><input id="search"',
    )
    replace_once(
        path,
        "search=document.getElementById('search'),stats=document.getElementById('stats'),status=document.getElementById('status'),protective=",
        "search=document.getElementById('search'),stats=document.getElementById('stats'),evidence=document.getElementById('evidence'),status=document.getElementById('status'),protective=",
    )
    replace_once(
        path,
        'function updateStats(data){stats.textContent=`${Number(data.node_count)||0} nodes · ${Number(data.edge_count)||0} edges · ${Number(data.event_count)||0} events`}\n',
        'function updateStats(data){stats.textContent=`${Number(data.node_count)||0} nodes · ${Number(data.edge_count)||0} edges · ${Number(data.event_count)||0} events`}\nfunction updateEvidence(data){const counts=data.live_evidence_counts||{},runtime=Number(counts.os_runtime)||0,specialized=Number(counts.specialized)||0,provisional=!!data.live_specialized_provisional;evidence.textContent=`OS ${runtime} · specialized ${specialized}${provisional?" · provisional":""}`;evidence.classList.toggle("provisional",provisional);evidence.title=provisional?"Specialized evidence is provisional until the canonical final merge.":"Observed evidence counts for this live session."}\n',
    )
    replace_once(
        path,
        "const finished=!!data.live_finished;status.textContent=finished?'FINISHED':",
        "updateEvidence(data);const finished=!!data.live_finished;status.textContent=finished?'FINISHED':",
    )


def patch_tests() -> None:
    path = Path("tests/test_v064_live_evidence.py")
    text = path.read_text(encoding="utf-8")
    if "from execweave.live_view import LIVE_HTML" not in text:
        anchor = "from execweave.live import _LiveState, run_live\n"
        if anchor not in text:
            raise RuntimeError("test import anchor not found")
        text = text.replace(anchor, anchor + "from execweave.live_view import LIVE_HTML\n", 1)

    marker = "def test_live_update_reports_evidence_totals_for_all_response_kinds"
    if marker not in text:
        text += r'''


def test_live_update_reports_evidence_totals_for_all_response_kinds(tmp_path: Path) -> None:
    runtime = tmp_path / "events.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    _write_jsonl(runtime, _runtime_records())
    semantic.write_text("", encoding="utf-8")
    state = _LiveState("s1", runtime, semantic)

    initial = state.live_update(-1)
    assert initial["kind"] == "snapshot"
    assert initial["live_evidence_counts"] == {"os_runtime": 2, "specialized": 0}
    assert initial["live_specialized_provisional"] is False

    _write_jsonl(semantic, [_semantic_record()])
    delta = state.live_update(int(initial["sequence"]))
    assert delta["kind"] == "delta"
    assert delta["live_evidence_counts"] == {"os_runtime": 2, "specialized": 1}
    assert delta["live_specialized_provisional"] is True

    noop = state.live_update(int(delta["sequence"]))
    assert noop["kind"] == "noop"
    assert noop["live_evidence_counts"] == {"os_runtime": 2, "specialized": 1}
    assert noop["live_specialized_provisional"] is True


def test_live_viewer_surfaces_specialized_evidence_state() -> None:
    assert 'id="evidence"' in LIVE_HTML
    assert "live_evidence_counts" in LIVE_HTML
    assert "live_specialized_provisional" in LIVE_HTML
    assert "specialized ${specialized}" in LIVE_HTML
'''
    path.write_text(text, encoding="utf-8")


def patch_readme() -> None:
    path = Path("README.md")
    text = path.read_text(encoding="utf-8")
    old = (
        "The Agent rows marked **Yes** mean automatic delivery *after the provider integration has "
        "been configured once*. `execweave live` supplies the per-run `EXECWEAVE_SEMANTIC_SIDECAR`; "
        "configured hooks/plugins inherit it and write directly into that run. ExecWeave does not "
        "silently edit provider settings when `live` starts. Model-runtime and inference-gateway "
        "rows stay **No** until their specialized metadata can be observed automatically rather than "
        "emitted explicitly."
    )
    new = (
        "Agent rows marked **Yes** require the provider hook/plugin to be configured once; "
        "`execweave live` then supplies the per-run `EXECWEAVE_SEMANTIC_SIDECAR` automatically. "
        "Ollama, llama.cpp, and vLLM rows marked **Yes** use automatic loopback model-catalog probes "
        "only when ExecWeave launches the corresponding local server. LM Studio and inference-gateway "
        "rows remain **No** until their specialized metadata can be observed automatically without "
        "inventing evidence."
    )
    if old not in text:
        raise RuntimeError("README.md: stale capability note not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    patch_live()
    patch_view()
    patch_tests()
    patch_readme()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

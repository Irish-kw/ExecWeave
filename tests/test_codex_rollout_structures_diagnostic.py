from __future__ import annotations

import importlib.util
from pathlib import Path

from execweave.codex_rollout_structures import enrich_codex_rollout_structures


def test_codex_structure_enricher_reports_no_internal_error(tmp_path: Path) -> None:
    fixture_path = Path(__file__).with_name("test_codex_rollout_structures.py")
    spec = importlib.util.spec_from_file_location("codex_structure_fixture", fixture_path)
    assert spec is not None and spec.loader is not None
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    root = fixture._bundle(tmp_path)
    result = enrich_codex_rollout_structures(
        trace_root=root,
        semantic_sidecar=tmp_path / "run" / "semantic.jsonl",
    )
    assert not result.errors, result.errors

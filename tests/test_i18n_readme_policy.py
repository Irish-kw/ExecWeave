from __future__ import annotations

import re
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READMES = (
    ROOT / "README.md",
    ROOT / "README.zh-TW.md",
    ROOT / "README.zh-CN.md",
    ROOT / "README.ja.md",
    ROOT / "README.ko.md",
    ROOT / "README.fr.md",
    ROOT / "README.de.md",
    ROOT / "README.ru.md",
)
EXPECTED_STABLE_ANCHORS = (
    "python -m pip install -U execweave",
    "execweave live --open -- cursor",
    "execweave live --open -- opencode",
    "execweave live --open -- ollama serve",
    "execweave top -- codex",
    "conversations.json",
    "LM Studio",
    "LiteLLM Proxy",
    "complete_from_source: true",
    "PolyForm Noncommercial License 1.0.0",
)
HARDCODED_RELEASE_TAG = re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b", re.I)


def test_readme_i18n_policy_uses_stable_product_anchors() -> None:
    namespace = runpy.run_path(str(ROOT / "scripts" / "audit_i18n_parity.py"))
    anchors = tuple(namespace["README_REQUIRED_SNIPPETS"])
    assert anchors == EXPECTED_STABLE_ANCHORS
    assert HARDCODED_RELEASE_TAG.search("\n".join(anchors)) is None
    assert "ev/s" not in "\n".join(anchors).lower()


def test_all_readmes_are_product_docs_not_release_changelogs() -> None:
    for path in READMES:
        text = path.read_text(encoding="utf-8")
        assert HARDCODED_RELEASE_TAG.search(text) is None, path.name
        assert "164,273 ev/s" not in text, path.name
        assert "This README documents" not in text, path.name
        for anchor in EXPECTED_STABLE_ANCHORS:
            assert anchor in text, (path.name, anchor)

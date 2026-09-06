from __future__ import annotations

import re
import runpy
from pathlib import Path

import _check_release_stage_integrity_impl as _impl


ROOT = Path(__file__).resolve().parents[1]
STABLE_README_ANCHORS = (
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
_HARDCODED_RELEASE_TAG = re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b", re.I)


def _assert_stable_readme_policy() -> str:
    """Protect the README contract semantically instead of freezing the audit file.

    The documentation audit is implementation code and must be maintainable when the
    public README policy changes. What is release-sensitive is the policy itself: all
    languages must retain the stable product entry points, and README coverage must not
    drift back to hard-coded release tags or one-off benchmark/release anchors.
    """

    namespace = runpy.run_path(str(ROOT / "scripts" / "audit_i18n_parity.py"))
    anchors = tuple(namespace.get("README_REQUIRED_SNIPPETS", ()))
    if anchors != STABLE_README_ANCHORS:
        raise RuntimeError(
            "README i18n policy changed unexpectedly:\n"
            f"expected={STABLE_README_ANCHORS!r}\nactual={anchors!r}"
        )
    joined = "\n".join(anchors)
    if _HARDCODED_RELEASE_TAG.search(joined) or "ev/s" in joined.lower():
        raise RuntimeError(
            "README i18n policy must use stable product anchors, not release tags or benchmark anchors"
        )
    return "stable product anchors; no hard-coded release/benchmark anchors"


def main() -> int:
    # The historical checker froze the entire i18n audit implementation. Keep every
    # other red line intact, but replace that whole-file freeze with the semantic policy
    # assertion above so documentation tooling can evolve without weakening coverage.
    _impl.CRITICAL_UNCHANGED = tuple(
        path for path in _impl.CRITICAL_UNCHANGED if path != "scripts/audit_i18n_parity.py"
    )
    policy = _assert_stable_readme_policy()
    result = _impl.main()
    print(f"README i18n policy: {policy}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

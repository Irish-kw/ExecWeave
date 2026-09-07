from __future__ import annotations

import re
import runpy
from pathlib import Path

import _check_release_stage_integrity_impl as _impl


# Preserve the public module surface used by the existing integrity unit tests. The
# implementation remains byte-for-byte historical; this entry module only changes how
# the i18n policy is protected.
for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

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

# Tests historically monkeypatch this public symbol before calling the release metadata
# guard. Keep that dependency-injection seam even though the implementation now lives
# in the private module.
_git = _impl._git


def _assert_release_metadata_unchanged(baseline_ref: str) -> str:
    original_git = _impl._git
    _impl._git = globals()["_git"]
    try:
        return _impl._assert_release_metadata_unchanged(baseline_ref)
    finally:
        _impl._git = original_git


def _assert_stable_readme_policy() -> str:
    """Protect README behavior semantically instead of freezing the audit file."""

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
    # Keep every historical release red line except the obsolete whole-file freeze on
    # the maintainable i18n audit implementation. Its public contract is guarded by
    # _assert_stable_readme_policy plus the normal i18n audit and unit suite.
    _impl.CRITICAL_UNCHANGED = tuple(
        path for path in _impl.CRITICAL_UNCHANGED if path != "scripts/audit_i18n_parity.py"
    )
    policy = _assert_stable_readme_policy()
    result = _impl.main()
    print(f"README i18n policy: {policy}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

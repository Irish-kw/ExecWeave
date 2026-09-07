"""Evidence-first result model and self-contained, escaped acceptance reports."""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP_UNAVAILABLE = "SKIP_UNAVAILABLE"


FEATURES = (
    "Launch",
    "Prompt",
    "Final",
    "Tool call",
    "File activity",
    "Process",
    "Network",
    "/root",
    "Multi-agent",
    "Fold state",
    "Live update",
    "Finished viewer",
    "JS console",
    "Cleanup",
)

_REQUIRED_FEATURES_BY_SCENARIO: dict[tuple[str, str], frozenset[str]] = {
    (
        "offline-ollama-fixture",
        "offline",
    ): frozenset(
        {
            "Launch",
            "Prompt",
            "Final",
            "Tool call",
            "/root",
            "Live update",
            "Finished viewer",
            "JS console",
            "Cleanup",
        }
    ),
    (
        "ollama",
        "visible-live",
    ): frozenset(
        {
            "Launch",
            "Prompt",
            "Final",
            "Process",
            "Network",
            "/root",
            "Live update",
            "Finished viewer",
            "JS console",
            "Cleanup",
        }
    ),
    (
        "ollama",
        "interactive-visible",
    ): frozenset(
        {
            "Launch",
            "Prompt",
            "Final",
            "Process",
            "Network",
            "/root",
            "Fold state",
            "Live update",
            "Finished viewer",
            "JS console",
            "Cleanup",
        }
    ),
    (
        "python",
        "native-os-only",
    ): frozenset(
        {
            "Launch",
            "Prompt",
            "Final",
            "Tool call",
            "File activity",
            "Process",
            "Network",
            "Live update",
            "Finished viewer",
            "JS console",
            "Cleanup",
        }
    ),
}

_NEGATIVE_ABSENCE_CHECKS = frozenset(
    {
        ("python", "native-os-only", "Prompt"),
        ("python", "native-os-only", "Final"),
        ("python", "native-os-only", "Tool call"),
    }
)


def redact(text: str) -> str:
    """Defense in depth; never intentionally ingest credentials/config contents."""
    text = re.sub(r"(?i)([?&](?:t|token|api_key)=)[^&#\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(Bearer\s+)[^\s\"']+", r"\1[REDACTED]", text)
    return re.sub(
        r"(?i)((?:api[_-]?key|authorization)\s*[:=]\s*)[^\s,\"']+",
        r"\1[REDACTED]",
        text,
    )


@dataclass
class Check:
    status: Status
    reason: str
    evidence: list[str] = field(default_factory=list)
    evidence_kind: str = "positive_support"


@dataclass
class Result:
    provider: str
    mode: str
    marker: str
    platform: str
    checks: dict[str, Check] = field(default_factory=dict)
    runtime_seconds: float = 0
    observed_requests: int | None = None
    artifacts: str = ""

    @property
    def required_features(self) -> frozenset[str]:
        return _REQUIRED_FEATURES_BY_SCENARIO.get(
            (self.provider.lower(), self.mode.lower()),
            frozenset(),
        )

    def check(
        self,
        feature: str,
        passed: bool,
        reason: str,
        *evidence: str,
        evidence_kind: str | None = None,
    ) -> bool:
        if feature not in FEATURES:
            raise ValueError(f"unknown feature: {feature}")
        previous = self.checks.get(feature)
        # A later successful retry must not erase a failure from this run.
        if previous and previous.status == Status.FAIL:
            return False
        kind = evidence_kind
        if kind is None:
            key = (self.provider.lower(), self.mode.lower(), feature)
            kind = "negative_absence" if key in _NEGATIVE_ABSENCE_CHECKS else "positive_support"
        self.checks[feature] = Check(
            Status.PASS if passed else Status.FAIL,
            redact(reason),
            [redact(str(item)) for item in evidence],
            kind,
        )
        return passed

    def skip(self, feature: str, reason: str) -> None:
        if feature not in FEATURES:
            raise ValueError(f"unknown feature: {feature}")
        if feature not in self.checks:
            lowered = reason.lower()
            kind = (
                "unavailable"
                if any(
                    marker in lowered
                    for marker in ("unavailable", "not found", "missing", "no local ")
                )
                else "scope_exclusion"
            )
            self.checks[feature] = Check(
                Status.SKIP_UNAVAILABLE,
                redact(reason),
                evidence_kind=kind,
            )

    def finish(self) -> None:
        # Unperformed work is not automatically an unavailable capability.
        for feature in FEATURES:
            if feature not in self.checks:
                self.check(feature, False, "Required assertion was not executed")

    @property
    def status(self) -> Status:
        if not self.checks or any(
            check.status == Status.FAIL for check in self.checks.values()
        ):
            return Status.FAIL
        if not any(check.status == Status.PASS for check in self.checks.values()):
            return Status.SKIP_UNAVAILABLE
        for feature in self.required_features:
            check = self.checks.get(feature)
            if check is None or check.status != Status.PASS:
                return Status.FAIL
        return Status.PASS

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "status": self.status.value,
            "required_features": sorted(self.required_features),
        }


def overall_status(results: list[Result], required: set[str]) -> Status:
    if not results or any(result.status == Status.FAIL for result in results):
        return Status.FAIL
    for provider in required:
        selected = [result for result in results if result.provider == provider]
        if not selected or any(result.status != Status.PASS for result in selected):
            return Status.FAIL
    return (
        Status.PASS
        if any(result.status == Status.PASS for result in results)
        else Status.SKIP_UNAVAILABLE
    )


def _run_git(repo_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _source_state() -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[2]
    sha = _run_git(repo_root, "rev-parse", "HEAD")
    status = _run_git(repo_root, "status", "--porcelain=v1", "--untracked-files=normal")
    ref = (
        os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or _run_git(repo_root, "branch", "--show-current")
        or None
    )
    return {
        "sha": sha or None,
        "dirty": None if status is None else bool(status),
        "ref": ref,
    }


def write_report(root: Path, results: list[Result], required: set[str]) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    for result in results:
        result.finish()
    summary = {
        "status": overall_status(results, required).value,
        "required": sorted(required),
        "source": _source_state(),
        "results": [result.to_dict() for result in results],
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    esc = html.escape
    headers = "".join(
        f"<th>{esc(result.provider)}<br>{esc(result.mode)} / {esc(result.platform)}</th>"
        for result in results
    )
    rows = []
    for feature in FEATURES:
        cells = []
        for result in results:
            check = result.checks[feature]
            required_marker = " required" if feature in result.required_features else ""
            cells.append(
                f'<td class="{check.status.value}" '
                f'title="{esc(check.reason, quote=True)}">'
                f"{check.status.value}<br><small>{esc(check.evidence_kind)}{required_marker}</small></td>"
            )
        rows.append(f"<tr><th>{esc(feature)}</th>{''.join(cells)}</tr>")
    details = []
    for result in results:
        checks = "".join(
            f"<li>{esc(feature)}: {check.status.value} "
            f"[{esc(check.evidence_kind)}] — {esc(check.reason)}</li>"
            for feature, check in result.checks.items()
        )
        details.append(
            f"<section><h2>{esc(result.provider)} / {esc(result.mode)}</h2>"
            f"<p>Marker: {esc(result.marker)} · Runtime: {result.runtime_seconds:.2f}s · "
            f"Observed requests: {result.observed_requests if result.observed_requests is not None else 'not measured'}</p>"
            f"<p>Artifacts: {esc(result.artifacts)}</p><ul>{checks}</ul></section>"
        )
    source = summary["source"]
    source_line = (
        f"Source: {esc(str(source.get('sha') or 'unknown'))} · "
        f"ref {esc(str(source.get('ref') or 'unknown'))} · "
        f"dirty {esc(str(source.get('dirty')))}"
    )
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave Dashboard Acceptance</title>
<style>body{{font:15px system-ui;margin:24px;background:#10151d;color:#e4ebf4}}table{{border-collapse:collapse}}th,td{{padding:9px;border:1px solid #536171}}.PASS{{color:#82e2ab}}.FAIL{{color:#ff9292}}.SKIP_UNAVAILABLE{{color:#eed68b}}.matrix{{overflow:auto}}section{{border-top:1px solid #536171;margin-top:24px}}li{{margin:6px 0}}small{{opacity:.8}}</style>
<h1>Dashboard acceptance: {summary["status"]}</h1>
<p>{source_line}</p>
<p>PASS proves only the explicitly executed scenario and platform. Offline fixtures do not prove live providers. A required SKIP is a failure; negative_absence is an invariant check, not semantic support. Hover cells for reasons.</p>
<div class="matrix"><table><thead><tr><th>Feature</th>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>{"".join(details)}</html>"""
    (root / "report.html").write_text(document, encoding="utf-8")
    return summary

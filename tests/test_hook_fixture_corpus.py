from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from typing import Callable

from execweave.claude_adapter import claude_hook_to_semantic_events
from execweave.claude_hook_cli import main as claude_hook_main
from execweave.codex_adapter import codex_hook_to_semantic_events
from execweave.cursor_adapter import cursor_hook_to_semantic_events
from execweave.opencode_adapter import opencode_plugin_to_semantic_events

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "hooks"
FIXED_TIMESTAMP = "2026-08-25T12:00:00Z"

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_HOME_PATH_PATTERNS = (
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
)
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "cookie",
}


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _strings(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            assert str(key).lower() not in _SENSITIVE_KEYS
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)
    elif isinstance(value, str):
        yield value


def _claude(payload: dict) -> list[dict]:
    return claude_hook_to_semantic_events(payload, timestamp=FIXED_TIMESTAMP)


def _codex(payload: dict) -> list[dict]:
    return codex_hook_to_semantic_events(payload, timestamp=FIXED_TIMESTAMP)


def _cursor(payload: dict) -> list[dict]:
    return cursor_hook_to_semantic_events(payload)


def _opencode(payload: dict) -> list[dict]:
    return opencode_plugin_to_semantic_events(payload, timestamp=FIXED_TIMESTAMP)


ADAPTERS: dict[str, Callable[[dict], list[dict]]] = {
    "claude": _claude,
    "codex": _codex,
    "cursor": _cursor,
    "opencode": _opencode,
}


def test_fixture_manifest_is_explicit_about_non_live_provenance() -> None:
    manifest = _load(FIXTURE_ROOT / "manifest.json")

    assert manifest["fixture_manifest_version"] == "0.1"
    assert manifest["corpus_kind"] == "sanitized_representative_regression_schema"
    assert manifest["live_capture"] is False
    assert manifest["contains_real_user_data"] is False
    assert manifest["contains_credentials"] is False

    entries = manifest["entries"]
    assert isinstance(entries, list)
    assert {entry["provider"] for entry in entries} == set(ADAPTERS)
    for entry in entries:
        assert entry["source_kind"] == "existing_regression_schema"
        assert entry["source_paths"]
        assert all(str(path).startswith("tests/test_") for path in entry["source_paths"])
        fixture = _load(FIXTURE_ROOT / entry["path"])
        assert fixture["provider"] == entry["provider"]
        assert len(fixture["payloads"]) == entry["payload_count"]


def test_fixture_corpus_contains_no_credentials_real_emails_or_user_home_paths() -> None:
    manifest = _load(FIXTURE_ROOT / "manifest.json")
    for entry in manifest["entries"]:
        fixture = _load(FIXTURE_ROOT / entry["path"])
        for text in _strings(fixture):
            assert not _EMAIL_PATTERN.search(text), f"email-like identity in {entry['path']}"
            assert not any(pattern.search(text) for pattern in _SECRET_PATTERNS), (
                f"credential-like material in {entry['path']}"
            )
            assert not any(pattern.search(text) for pattern in _HOME_PATH_PATTERNS), (
                f"user-home path in {entry['path']}"
            )


def test_all_sanitized_fixtures_pass_production_semantic_adapters() -> None:
    manifest = _load(FIXTURE_ROOT / "manifest.json")
    for entry in manifest["entries"]:
        fixture = _load(FIXTURE_ROOT / entry["path"])
        adapter = ADAPTERS[entry["provider"]]
        events = [event for payload in fixture["payloads"] for event in adapter(payload)]
        relations = {event["relation"] for event in events}
        assert set(entry["expected_relations"]).issubset(relations), entry["provider"]


def test_claude_fixture_exercises_hook_cli_and_sidecar(
    tmp_path: Path, monkeypatch,
) -> None:
    fixture = _load(FIXTURE_ROOT / "claude.json")
    payload = next(
        item for item in fixture["payloads"] if item["hook_event_name"] == "PreToolUse"
    )
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert claude_hook_main(["--sidecar", str(sidecar), "--strict"]) == 0
    records = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    relations = {record.get("relation") for record in records}
    assert {"REQUESTED_TOOL_CALL", "USES_TOOL", "DECLARED_COMMAND"}.issubset(relations)

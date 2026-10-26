"""Assert that a recorded run actually materialized the conversations it observed.

CI previously ran every provider's record pipeline end to end and never looked at
``conversations.json``. All four provider smokes were producing ``entry_count: 0``
while reporting success, which is how a total conversation collapse reached a tagged
release with green CI.

This checker closes that gap. It reads the final artifact — not an intermediate
preview object — and fails when a run that observed conversational evidence published
none, when an expected agent is missing, when one agent execution is published as
several conversations, or when a message landed in the wrong agent's thread.

Every check walks the real entry list. An earlier version keyed previews by agent path
before running the ownership checks, so a duplicate silently overwrote its twin and the
isolation assertions only ever saw one of them.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _fail(message: str) -> None:
    print(f"conversation record check FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def _load(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "conversations.json"
    if not path.is_file():
        _fail(f"{path} does not exist")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"{path} is not valid JSON: {exc.msg}")
    if not isinstance(payload, dict):
        _fail(f"{path} root must be a JSON object")
    return payload


def _entries_by_agent(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group every materialized preview under its agent path, keeping duplicates."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in document.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        preview = entry.get("conversation_preview")
        if isinstance(preview, dict) and preview.get("agent_path"):
            grouped[str(preview["agent_path"])].append(preview)
    return dict(grouped)


def _texts(preview: dict[str, Any]) -> str:
    return "\n".join(
        str(message.get("text") or "") for message in preview.get("messages") or []
    )


def _describe(agent_path: str, previews: list[dict[str, Any]]) -> str:
    threads = [str(preview.get("thread_id")) for preview in previews]
    return f"{agent_path} -> {len(previews)} entries with thread ids {threads}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a run's materialized conversations.json"
    )
    parser.add_argument("run_dir", type=Path, help="ExecWeave run artifact directory")
    parser.add_argument(
        "--expect-agent",
        action="append",
        default=[],
        metavar="AGENT_PATH",
        help="agent path that must have a conversation entry (repeatable)",
    )
    parser.add_argument(
        "--expect-root-text",
        action="append",
        default=[],
        metavar="TEXT",
        help="text that must appear in the /root thread (repeatable)",
    )
    parser.add_argument(
        "--expect-owned",
        action="append",
        default=[],
        metavar="AGENT_PATH=TEXT",
        help="text that must appear in one agent's thread and nowhere else (repeatable)",
    )
    parser.add_argument(
        "--forbid-agent",
        action="append",
        default=[],
        metavar="AGENT_PATH",
        help="agent path that must NOT exist, e.g. a fabricated child (repeatable)",
    )
    parser.add_argument(
        "--allow-duplicate-agent",
        action="append",
        default=[],
        metavar="AGENT_PATH",
        help=(
            "permit this agent path to hold several conversation entries. Only for a "
            "fixture where one agent genuinely runs several independent conversations; "
            "one execution published twice is a defect, not a configuration choice."
        ),
    )
    parser.add_argument(
        "--min-entries",
        type=int,
        default=1,
        help="minimum number of materialized conversation entries (default: 1)",
    )
    args = parser.parse_args()

    document = _load(args.run_dir)
    grouped = _entries_by_agent(document)
    entry_count = document.get("entry_count")

    if not isinstance(entry_count, int) or entry_count < args.min_entries:
        _fail(
            f"entry_count is {entry_count!r}; expected at least {args.min_entries}. "
            "The run observed conversational evidence but published none."
        )
    if len(grouped) < args.min_entries:
        _fail(f"only {len(grouped)} agents carry a conversation; expected {args.min_entries}")

    # One agent execution must be published exactly once. Evidence that names its
    # thread differently is provenance, not a second conversation.
    allowed_duplicates = set(args.allow_duplicate_agent)
    for agent_path, previews in sorted(grouped.items()):
        if len(previews) > 1 and agent_path not in allowed_duplicates:
            _fail(
                "one agent execution is published as several conversations: "
                + _describe(agent_path, previews)
                + ". Evidence describing the same execution must merge into one entry."
            )

    for agent_path in args.expect_agent:
        if agent_path not in grouped:
            _fail(f"no conversation entry for {agent_path}; found {sorted(grouped)}")
        if not any(preview.get("messages") for preview in grouped[agent_path]):
            _fail(f"{agent_path} materialized an entry with no messages")

    for agent_path in args.forbid_agent:
        if agent_path in grouped:
            _fail(f"{agent_path} was materialized but no evidence establishes it")

    if args.expect_root_text and "/root" not in grouped:
        _fail(f"no /root conversation; found {sorted(grouped)}")
    for text in args.expect_root_text:
        if not any(text in _texts(preview) for preview in grouped.get("/root", [])):
            _fail(f"/root thread is missing expected text {text!r}")

    for spec in args.expect_owned:
        agent_path, separator, text = spec.partition("=")
        if not separator:
            _fail(f"--expect-owned needs AGENT_PATH=TEXT, got {spec!r}")
        if agent_path not in grouped:
            _fail(f"no conversation entry for {agent_path}; found {sorted(grouped)}")
        if not any(text in _texts(preview) for preview in grouped[agent_path]):
            _fail(f"{agent_path} is missing its own content {text!r}")
        # Isolation is checked against every published entry, so a duplicate cannot
        # hide a leak by being overwritten before this runs.
        for other_path, others in grouped.items():
            if other_path == agent_path:
                continue
            for preview in others:
                if text in _texts(preview):
                    _fail(
                        f"content {text!r} owned by {agent_path} leaked into "
                        f"{other_path} (thread {preview.get('thread_id')!r})"
                    )

    # Topology provenance: every parent link must name the evidence behind it, and no
    # entry may claim a parent that has no conversation of its own.
    for agent_path, previews in sorted(grouped.items()):
        for preview in previews:
            parent = preview.get("parent_agent_path")
            if preview.get("is_root"):
                if parent is not None:
                    _fail(f"{agent_path} is root but names parent {parent!r}")
                continue
            if parent is None:
                _fail(f"{agent_path} is not root but names no parent")
            if not preview.get("parent_relation_source"):
                _fail(f"{agent_path} claims parent {parent!r} with no evidence recorded")
            if parent not in grouped:
                _fail(f"{agent_path} names parent {parent!r}, which has no conversation")

    print(
        f"conversation record check passed for {args.run_dir}: "
        f"{entry_count} entries, agents {sorted(grouped)}"
    )
    for agent_path, previews in sorted(grouped.items()):
        for preview in previews:
            evidence = preview.get("evidence_thread_ids") or [preview.get("thread_id")]
            print(
                f"  {agent_path}: {len(preview.get('messages') or [])} messages, "
                f"completeness={preview.get('conversation_completeness')}, "
                f"path_source={preview.get('agent_path_source')}, "
                f"topology={preview.get('topology_state')}, "
                f"thread={preview.get('thread_id')}, "
                f"evidence_threads={len(evidence)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

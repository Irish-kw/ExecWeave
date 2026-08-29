"""Assert that a recorded run actually materialized the conversations it observed.

CI previously ran every provider's record pipeline end to end and never looked at
``conversations.json``. All four provider smokes were producing ``entry_count: 0``
while reporting success, which is how a total conversation collapse reached a tagged
release with green CI.

This checker closes that gap. It reads the final artifact — not an intermediate
preview object — and fails when a run that observed conversational evidence published
none, when an expected agent is missing, or when a message landed in the wrong
agent's thread.
"""

from __future__ import annotations

import argparse
import json
import sys
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


def _previews(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    previews: dict[str, dict[str, Any]] = {}
    for entry in document.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        preview = entry.get("conversation_preview")
        if isinstance(preview, dict) and preview.get("agent_path"):
            previews[str(preview["agent_path"])] = preview
    return previews


def _texts(preview: dict[str, Any]) -> str:
    return "\n".join(
        str(message.get("text") or "") for message in preview.get("messages") or []
    )


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
        help="agent path that must have its own conversation entry (repeatable)",
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
        "--min-entries",
        type=int,
        default=1,
        help="minimum number of materialized conversation entries (default: 1)",
    )
    args = parser.parse_args()

    document = _load(args.run_dir)
    previews = _previews(document)
    entry_count = document.get("entry_count")

    if not isinstance(entry_count, int) or entry_count < args.min_entries:
        _fail(
            f"entry_count is {entry_count!r}; expected at least {args.min_entries}. "
            "The run observed conversational evidence but published none."
        )
    if len(previews) < args.min_entries:
        _fail(f"only {len(previews)} entries carry an agent path; expected {args.min_entries}")

    for agent_path in args.expect_agent:
        if agent_path not in previews:
            _fail(f"no conversation entry for {agent_path}; found {sorted(previews)}")
        if not previews[agent_path].get("messages"):
            _fail(f"{agent_path} materialized an entry with no messages")

    for agent_path in args.forbid_agent:
        if agent_path in previews:
            _fail(f"{agent_path} was materialized but no evidence establishes it")

    root = previews.get("/root")
    if args.expect_root_text and root is None:
        _fail(f"no /root conversation; found {sorted(previews)}")
    for text in args.expect_root_text:
        if text not in _texts(root or {}):
            _fail(f"/root thread is missing expected text {text!r}")

    for spec in args.expect_owned:
        agent_path, separator, text = spec.partition("=")
        if not separator:
            _fail(f"--expect-owned needs AGENT_PATH=TEXT, got {spec!r}")
        if agent_path not in previews:
            _fail(f"no conversation entry for {agent_path}; found {sorted(previews)}")
        if text not in _texts(previews[agent_path]):
            _fail(f"{agent_path} is missing its own content {text!r}")
        for other_path, other in previews.items():
            if other_path == agent_path:
                continue
            if text in _texts(other):
                _fail(
                    f"content {text!r} owned by {agent_path} leaked into {other_path}"
                )

    # Topology provenance: every parent link must name the evidence behind it, and no
    # entry may claim a parent that has no conversation of its own.
    for agent_path, preview in sorted(previews.items()):
        parent = preview.get("parent_agent_path")
        if preview.get("is_root"):
            if parent is not None:
                _fail(f"{agent_path} is root but names parent {parent!r}")
            continue
        if parent is None:
            _fail(f"{agent_path} is not root but names no parent")
        if not preview.get("parent_relation_source"):
            _fail(f"{agent_path} claims parent {parent!r} with no evidence recorded")
        if parent not in previews:
            _fail(f"{agent_path} names parent {parent!r}, which has no conversation")

    print(
        f"conversation record check passed for {args.run_dir}: "
        f"{entry_count} entries, agents {sorted(previews)}"
    )
    for agent_path, preview in sorted(previews.items()):
        print(
            f"  {agent_path}: {len(preview.get('messages') or [])} messages, "
            f"completeness={preview.get('conversation_completeness')}, "
            f"path_source={preview.get('agent_path_source')}, "
            f"topology={preview.get('topology_state')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

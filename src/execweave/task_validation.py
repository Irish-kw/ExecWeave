"""Operator-supplied test evidence, not an oracle or authenticated attestation.

Import an already-produced UTF-8 JUnit report and bind it to one exact recorded
task snapshot. No command is executed and no run/archive bytes are rewritten.
The viewer independently recounts the embedded report before displaying it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_CASES = 10_000
MAX_ELEMENTS = 50_000
MAX_TASK_BYTES = 1024 * 1024
MAX_SUBJECTS = 200
FORMAT = "execweave.external-task-report.v1"


def _text(value: Any, name: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text of at most {limit} characters")
    return value


def _native(node: dict[str, Any]) -> bool:
    a = node.get("attributes")
    return not any(
        o.get(k) is not None and o.get(k) is not False
        for o in (node, a if isinstance(a, dict) else {})
        for k in ("inferred", "viewer_only")
    )


def task_subject(node: dict[str, Any]) -> dict[str, str]:
    """Fingerprint the complete recorded task, not its label or agent name."""
    if node.get("type") != "task" or not _native(node):
        raise ValueError("a native task node is required")
    identity = _text(node.get("id"), "task ID")
    payload = json.dumps(
        node, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    if len(payload) > MAX_TASK_BYTES:
        raise ValueError("task snapshot exceeds the fingerprint budget")
    return {"task_id": identity, "task_snapshot_sha256": hashlib.sha256(payload).hexdigest()}


def assessment_subjects(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Publish bounded fingerprints alongside the metadata-only assessment."""
    result = []
    omitted = 0
    for node in nodes:
        if node.get("type") != "task" or not _native(node):
            continue
        if len(result) >= MAX_SUBJECTS:
            omitted += 1
            continue
        try:
            subject = task_subject(node)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            omitted += 1
            continue
        result.append(subject)
    return {"external_report_subjects": result, "external_report_subjects_omitted": omitted}


def report_summary(xml: str) -> dict[str, Any]:
    """Recount supported JUnit case elements; never trust a 'tests passed' label.

    Only unnamespaced testsuites/testsuite/testcase documents are supported.
    Aggregate counters, when supplied, must match the actual case elements.
    Ambiguous repeated case IDs and nonstandard outcome extensions are rejected.
    """
    if not isinstance(xml, str) or len(xml.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("report exceeds the 2 MiB UTF-8 limit")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", xml, re.I) or "\x00" in xml:
        raise ValueError("DTD, entity declarations and NUL are not supported")
    encoding = re.search(r"<\?xml[^>]*\bencoding\s*=\s*['\"]([^'\"]+)", xml, re.I)
    if encoding and encoding[1].lower() not in ("utf-8", "utf8"):
        raise ValueError("only UTF-8 reports are supported")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("malformed XML report") from exc
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("expected testsuite or testsuites")
    counts = dict(tests=0, passed=0, failures=0, errors=0, skipped=0)
    cases = []
    seen = set()
    elements = 0

    def visit(element: ET.Element, depth: int, parent: str | None) -> dict[str, int]:
        nonlocal elements
        elements += 1
        if elements > MAX_ELEMENTS or depth > 32:
            raise ValueError("XML structure exceeds inspection budget")
        tag = element.tag
        if not isinstance(tag, str) or "}" in tag or ":" in tag:
            raise ValueError("namespaced or unsupported XML is not accepted")
        subtotal = dict.fromkeys(counts, 0)
        if tag == "testcase":
            if parent != "testsuite":
                raise ValueError("testcase must belong directly to a testsuite")
            name = _text(element.get("name"), "testcase name")
            cls = element.get("classname", "")
            if len(cls) > 4096:
                raise ValueError("testcase classname exceeds limit")
            key = (cls, name)
            if key in seen:
                raise ValueError("duplicate testcase identity")
            seen.add(key)
            if len(seen) > MAX_CASES:
                raise ValueError("too many testcases")
            outcomes = [c.tag for c in element if c.tag in ("failure", "error", "skipped")]
            if len(outcomes) > 1:
                raise ValueError("multiple testcase outcomes are ambiguous")
            for child in element:
                if child.tag not in {
                    "failure",
                    "error",
                    "skipped",
                    "system-out",
                    "system-err",
                    "properties",
                }:
                    raise ValueError("unsupported testcase child")
                visit(child, depth + 1, tag)
            status = {"failure": "failures", "error": "errors", "skipped": "skipped"}.get(
                outcomes[0] if outcomes else "", "passed"
            )
            # Some producers encode not-run states as attributes rather than children.
            if element.get("status") not in (None, "run") or element.get("result") is not None:
                raise ValueError("unsupported testcase status/result attribute")
            subtotal["tests"] = 1
            subtotal[status] = 1
            cases.append({"name": name, "classname": cls, "outcome": status})
        elif tag in ("testsuite", "testsuites"):
            if parent not in (None, "testsuite", "testsuites") or (tag == "testsuites" and parent):
                raise ValueError("unsupported suite nesting")
            allowed = {"testsuite", "properties", "system-out", "system-err"}
            if tag == "testsuite":
                allowed.add("testcase")
            for child in element:
                if child.tag not in allowed:
                    raise ValueError("unsupported suite child")
                child_counts = visit(child, depth + 1, tag)
                for key in subtotal:
                    subtotal[key] += child_counts[key]
            for key in ("tests", "failures", "errors", "skipped"):
                declared = element.get(key)
                if declared is not None and (
                    not re.fullmatch(r"[0-9]{1,9}", declared) or int(declared) != subtotal[key]
                ):
                    raise ValueError(f"suite {key} counter disagrees with case records")
        elif tag == "properties":
            if parent not in ("testsuite", "testsuites", "testcase"):
                raise ValueError("unsupported properties location")
            for child in element:
                if child.tag != "property":
                    raise ValueError("unsupported property child")
                visit(child, depth + 1, tag)
        else:
            if tag not in {
                "failure",
                "error",
                "skipped",
                "system-out",
                "system-err",
                "property",
            } or len(element):
                raise ValueError("unsupported XML element")
        return subtotal

    counts = visit(root, 0, None)
    state = (
        "checks_failed"
        if counts["failures"] or counts["errors"]
        else "no_executed_checks"
        if counts["passed"] == 0
        else "partial"
        if counts["skipped"]
        else "checks_passed"
    )
    return {
        "state": state,
        "counts": counts,
        "cases": cases,
        "task_success_implied": False,
        "authority_authenticated": False,
    }


def make_receipt(
    graph: dict[str, Any], task_id: str, xml: str, *, validator: str, criterion: str
) -> dict[str, Any]:
    from .run_assessment import build_run_assessment

    assessment = build_run_assessment(graph)
    session = _text(graph.get("session_id"), "session ID")
    if assessment["inspection"]["state"] != "declared_graph":
        raise ValueError("complete unambiguous raw graph metadata is required")
    matches = [
        s
        for s in assessment["task_validation"]["external_report_subjects"]
        if s["task_id"] == task_id
    ]
    if len(matches) != 1:
        raise ValueError("exact native task identity is missing, ambiguous or outside the budget")
    scope = {"session_id": session}
    for key in ("run_id", "source_path"):
        value = graph.get(key)
        if value is not None:
            _text(value, key)
        scope[key] = value
    summary = report_summary(xml)
    return {
        "format": FORMAT,
        "scope": scope,
        "subject": matches[0],
        "validator": _text(validator, "validator label", 256),
        "criterion": _text(criterion, "criterion", 2048),
        "authority": "operator_supplied_not_authenticated",
        "report": {
            "media_type": "application/xml; charset=utf-8",
            "xml": xml,
            "sha256": hashlib.sha256(xml.encode("utf-8")).hexdigest(),
        },
        "summary": summary,
    }


def _read(path: str, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("input must be a bounded regular file")
        payload = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
        if len(payload) > limit or (before.st_size, before.st_mtime_ns) != (
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("input changed or exceeded its limit while reading")
        return payload


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bind an external JUnit report to one recorded task; no commands are executed."
    )
    for arg in ("graph", "task-id", "junit", "validator", "criterion", "output"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument(
        "--artifact", action="append", default=[], metavar="RELATIVE_NAME=LOCAL_FILE",
        help="Associate explicit artifact bytes with this report; does not prove they were tested.",
    )
    args = parser.parse_args(argv)
    try:
        graph = json.loads(
            _read(args.graph, 64 * 1024 * 1024),
            object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
        )
        if not isinstance(graph, dict):
            raise ValueError("graph must be an object")
        receipt = make_receipt(
            graph,
            args.task_id,
            _read(args.junit, MAX_REPORT_BYTES).decode("utf-8"),
            validator=args.validator,
            criterion=args.criterion,
        )
        if args.artifact:
            from .task_artifacts import bind_artifacts

            receipt = bind_artifacts(receipt, args.artifact)
        # Exclusive creation preserves original evidence and existing derivatives.
        with Path(args.output).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        print(
            json.dumps(
                {
                    "state": receipt["summary"]["state"],
                    "output": args.output,
                    "authority_authenticated": False,
                    "task_success_implied": False,
                }
            )
        )
        return 0
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(f"External task report not created: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

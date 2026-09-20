"""External report evidence is bound and recounted, never universal task truth."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from execweave.task_validation import main, make_receipt, report_summary, task_subject
from execweave.run_assessment import build_run_assessment


def graph():
    return {
        "session_id": "report-session",
        "run_id": "report-run",
        "source_path": "/recorded/events.jsonl",
        "nodes": [
            {
                "id": "task:1",
                "type": "task",
                "name": "Do not confuse with a claim",
                "attributes": {"goal": "test parser"},
            },
            {"id": "agent:1", "type": "agent", "name": "same name"},
        ],
        "edges": [
            {"id": "claim", "source": "agent:1", "target": "task:1", "relation": "TASK_COMPLETED"}
        ],
    }


def xml(outcomes=()):
    items = ['<testcase classname="test_synthetic" name="ok"/>']
    for i, outcome in enumerate(outcomes):
        items.append(
            f'<testcase classname="test_synthetic" name="case-{i}"><{outcome}/></testcase>'
        )
    return "<testsuites><testsuite>" + "".join(items) + "</testsuite></testsuites>"


def receipt(data=None, document=None):
    return make_receipt(
        data or graph(),
        "task:1",
        xml() if document is None else document,
        validator="Operator-chosen local check",
        criterion="Selected test set, not the whole task",
    )


@pytest.mark.parametrize(
    "document,state,counts",
    [
        (xml(), "checks_passed", (1, 1, 0, 0, 0)),
        (xml(["failure"]), "checks_failed", (2, 1, 1, 0, 0)),
        (xml(["error"]), "checks_failed", (2, 1, 0, 1, 0)),
        (xml(["skipped"]), "partial", (2, 1, 0, 0, 1)),
        ("<testsuite/>", "no_executed_checks", (0, 0, 0, 0, 0)),
        (
            '<testsuite><testcase name="skip"><skipped/></testcase></testsuite>',
            "no_executed_checks",
            (1, 0, 0, 0, 1),
        ),
        (
            '<testsuites tests="1"><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite></testsuites>',
            "checks_passed",
            (1, 1, 0, 0, 0),
        ),
        (
            '<testsuite><testsuite><testcase name="nested"/></testsuite></testsuite>',
            "checks_passed",
            (1, 1, 0, 0, 0),
        ),
    ],
    ids=["passing", "failure", "error", "partial", "empty", "all-skipped", "counted", "nested"],
)
def test_explicit_outcomes_not_agent_claims(document, state, counts):
    result = report_summary(document)
    assert result["state"] == state
    assert tuple(result["counts"].values()) == counts
    assert not result["task_success_implied"] and not result["authority_authenticated"]


INVALID = [
    "",
    "<testsuite>",
    "<html/>",
    '<testsuite tests="1"/>',
    '<testsuite tests="0"><testcase name="ok"/></testsuite>',
    '<testsuite failures="false"/>',
    '<testsuite><testcase name="x"/><testcase name="x"/></testsuite>',
    '<testsuite><testcase name="x"><failure/><skipped/></testcase></testsuite>',
    "<testsuite><testcase/></testsuite>",
    '<testsuite><testcase name="x" status="notrun"/></testsuite>',
    '<testsuite><testcase name="x" result="passed"/></testsuite>',
    '<testsuites><testcase name="x"/></testsuites>',
    "<testsuite><unknown/></testsuite>",
    '<testsuite xmlns="unknown"><testcase name="x"/></testsuite>',
    '<!DOCTYPE testsuite [<!ENTITY x "expanded">]><testsuite/>',
    '<!DOCTYPE testsuite SYSTEM "file:///etc/passwd"><testsuite/>',
    '<?xml version="1.0" encoding="utf-16"?><testsuite/>',
    '<testsuite><system-out><testcase name="not-a-test"/></system-out></testsuite>',
    "<testsuite>" * 34 + "</testsuite>" * 34,
]


@pytest.mark.parametrize("document", INVALID, ids=[f"invalid-{i}" for i in range(len(INVALID))])
def test_invalid_reports_fail_closed(document):
    with pytest.raises(ValueError):
        report_summary(document)


def test_report_size_budget_and_case_budget():
    with pytest.raises(ValueError):
        report_summary("<testsuite>" + "x" * (2 * 1024 * 1024) + "</testsuite>")
    with pytest.raises(ValueError):
        report_summary(
            "<testsuite>"
            + "".join(f'<testcase name="c{i}"/>' for i in range(10001))
            + "</testsuite>"
        )


def test_receipt_has_exact_task_snapshot_and_unmodified_graph():
    data = graph()
    before = copy.deepcopy(data)
    result = receipt(data)
    assert data == before
    assert result["scope"] == {k: data[k] for k in ("session_id", "run_id", "source_path")}
    assert result["subject"] == task_subject(data["nodes"][0])
    assert result["report"]["sha256"] == hashlib.sha256(xml().encode()).hexdigest()
    assert build_run_assessment(data)["task_validation"]["state"] == "unverified"
    assert build_run_assessment(data)["task_validation"]["reported_completed"] == 1


@pytest.mark.parametrize(
    "kind", ["unknown", "same-name", "duplicate", "inferred", "projected", "no-session"]
)
def test_receipt_rejects_ambiguous_or_non_native_task(kind):
    data = graph()
    if kind == "unknown":
        data["nodes"][0]["id"] = "other"
    elif kind == "same-name":
        data["nodes"][1]["name"] = "task:1"
        data["nodes"].pop(0)
    elif kind == "duplicate":
        data["nodes"].append({"id": "task:1", "type": "agent"})
    elif kind == "inferred":
        data["nodes"][0]["inferred"] = True
    elif kind == "projected":
        data["viewer_projection"] = {"kind": "filtered"}
    else:
        data.pop("session_id")
    with pytest.raises(ValueError):
        receipt(data)


def test_subject_fingerprint_changes_on_task_change_not_dict_order():
    node = graph()["nodes"][0]
    assert task_subject(node) == task_subject(dict(reversed(list(node.items()))))
    assert task_subject(node) != task_subject({**node, "name": "revised task"})


def test_live_and_static_publish_same_task_fingerprints_before_folding():
    from execweave.viewer_projection import project_viewer_graph

    data = graph()
    expected = build_run_assessment(data)["task_validation"]["external_report_subjects"]
    assert (
        project_viewer_graph(data)["run_assessment"]["task_validation"]["external_report_subjects"]
        == expected
    )


def test_cli_refuses_overwrite_and_preserves_actual_data(tmp_path):
    raw = tmp_path / "graph.json"
    raw.write_text(json.dumps(graph()))
    report = tmp_path / "tests.xml"
    report.write_text(xml(["failure"]))
    output = tmp_path / "receipt.json"
    args = [
        "--graph",
        str(raw),
        "--task-id",
        "task:1",
        "--junit",
        str(report),
        "--validator",
        "local",
        "--criterion",
        "specified test set",
        "--output",
        str(output),
    ]
    assert main(args) == 0  # CLI succeeded in creating a failed-check report.
    result = json.loads(output.read_text())
    assert result["summary"]["state"] == "checks_failed"
    before = output.read_bytes()
    assert main(args) == 2 and output.read_bytes() == before
    assert raw.read_text() == json.dumps(graph()) and report.read_text() == xml(["failure"])


def test_cli_invalid_input_does_not_create_receipt(tmp_path):
    raw = tmp_path / "graph.json"
    raw.write_text('{"session_id":"a","session_id":"b"}')
    output = tmp_path / "receipt.json"
    assert (
        main(
            [
                "--graph",
                str(raw),
                "--task-id",
                "task:1",
                "--junit",
                "not-read",
                "--validator",
                "local",
                "--criterion",
                "not run",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()


def test_real_pytest_report_recount_and_cli_entry(tmp_path):
    suite = tmp_path / "test_external.py"
    suite.write_text(
        'import pytest\ndef test_ok(): assert 2+2==4\ndef test_bad(): assert 2+2==5\n@pytest.mark.skip(reason="not executed")\ndef test_skipped(): pass\n'
    )
    report = tmp_path / "actual.xml"
    child = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(suite), "--junitxml", str(report)],
        cwd=tmp_path,
        capture_output=True,
        timeout=30,
    )
    assert child.returncode == 1
    result = receipt(document=report.read_text())
    assert result["summary"]["counts"] == dict(tests=3, passed=1, failures=1, errors=0, skipped=1)
    env = dict(os.environ, PYTHONPATH=str(__import__("pathlib").Path(__file__).parents[1] / "src"))
    usage = subprocess.run(
        [
            sys.executable,
            "-m",
            "execweave.task_validation",
            "--help",
        ],
        env=env,
        capture_output=True,
        timeout=15,
    )
    assert usage.returncode == 0 and b"--criterion" in usage.stdout

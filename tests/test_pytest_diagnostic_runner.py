"""Real subprocess contracts for the opt-in diagnostic; no product acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import psutil
import pytest

RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_pytest.py"


def run(tmp_path, source, *, budget=15, interval=2):
    case = tmp_path / "case"
    case.mkdir()
    (case / "test_sample.py").write_text(source, encoding="utf-8")
    out = tmp_path / "evidence"
    result = subprocess.run([sys.executable, str(RUNNER), "--output", str(out),
                             "--budget", str(budget), "--stack-interval", str(interval),
                             "--", "test_sample.py"], cwd=case, capture_output=True,
                            text=True, timeout=budget + 15)
    return result, out


def test_pass_preserves_collection_order_and_phase_outcomes(tmp_path):
    result, out = run(tmp_path, "def test_first(): pass\ndef test_second(): pass\n")
    assert result.returncode == 0, result.stderr
    assert json.loads((out / "collection.json").read_text()) == [
        "test_sample.py::test_first", "test_sample.py::test_second"]
    summary = json.loads((out / "summary.json").read_text())
    assert summary["state"] == "completed" and summary["finished_records"] == 2
    assert summary["acceptance"] is False
    rows = [json.loads(s) for s in (out / "progress.jsonl").read_text().splitlines()]
    assert [r["phase"] for r in rows if r["event"] == "phase"] == ["setup", "call", "teardown"] * 2


def test_failure_preserves_pytest_exit_code(tmp_path):
    result, out = run(tmp_path, "def test_bad(): assert False\n")
    assert result.returncode == 1
    summary = json.loads((out / "summary.json").read_text())
    assert summary["state"] == "failed" and summary["session_exit_code"] == 1
    assert 'failures="1"' in (out / "pytest.xml").read_text()


def test_deadline_retains_active_test_stack_and_stops_only_owned_processes(tmp_path):
    sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        result, out = run(tmp_path, "import time\ndef test_stall(): time.sleep(30)\n", budget=3, interval=.3)
        assert result.returncode == 124
        summary = json.loads((out / "summary.json").read_text())
        assert summary["state"] == "deadline" and summary["acceptance"] is False
        assert summary["last_started"] == "test_sample.py::test_stall"
        assert summary["last_finished"] is None and summary["session_exit_code"] is None
        assert 'test_stall' in (out / "stacks.txt").read_text()
        assert json.loads((out / "cleanup.json").read_text())["surviving_owned_pids"] == []
        rows = json.loads((out / "processes-at-deadline.json").read_text())
        assert sentinel.pid not in [r['pid'] for r in rows]
        assert all('cmdline' not in r and 'environ' not in r for r in rows)
        assert sentinel.poll() is None
    finally:
        sentinel.terminate()
        sentinel.wait(timeout=5)


def test_deadline_also_stops_a_descendant_spawned_by_the_test(tmp_path):
    source = ("import subprocess, sys, time\nfrom pathlib import Path\n"
              "def test_stall_child():\n"
              "    p = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])\n"
              "    Path('child.pid').write_text(str(p.pid))\n"
              "    time.sleep(30)\n")
    result, out = run(tmp_path, source, budget=3, interval=.3)
    assert result.returncode == 124
    pid = int((tmp_path / "case" / "child.pid").read_text())
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    assert pid in [r['pid'] for r in json.loads((out / "processes-at-deadline.json").read_text())]


def test_collection_error_cannot_become_success(tmp_path):
    result, out = run(tmp_path, "this is invalid syntax !\n")
    assert result.returncode != 0
    assert json.loads((out / "summary.json").read_text())["state"] == "failed"


def test_existing_diagnostic_is_not_overwritten(tmp_path):
    root = tmp_path / "kept"
    root.mkdir()
    marker = root / "summary.json"
    marker.write_text('original')
    result = subprocess.run([sys.executable, str(RUNNER), "--output", str(root)],
                            capture_output=True, timeout=5)
    assert result.returncode != 0 and marker.read_text() == 'original'


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf'])
def test_invalid_budget_does_not_start_tests(tmp_path, value):
    out = tmp_path / "unused"
    result = subprocess.run([sys.executable, str(RUNNER), '--output', str(out), '--budget', value],
                            capture_output=True, timeout=5)
    assert result.returncode == 2 and not out.exists()


def test_no_tests_collected_is_not_a_passing_diagnostic(tmp_path):
    result, out = run(tmp_path, "# Deliberately no test functions.\n")
    assert result.returncode == 5
    summary = json.loads((out / "summary.json").read_text())
    assert summary["state"] == "failed" and summary["finished_records"] == 0


def test_workflow_keeps_candidate_and_diagnostic_limits_explicit():
    import yaml

    path = RUNNER.parents[1] / '.github/workflows/windows-suite-diagnostic.yml'
    workflow = yaml.safe_load(path.read_text())
    assert workflow['permissions'] == {'contents': 'read'}
    assert workflow['concurrency']['cancel-in-progress'] is False
    job = workflow['jobs']['diagnose']
    assert job['runs-on'] == 'windows-latest' and job['timeout-minutes'] == 40
    steps = job['steps']
    candidate = next(s for s in steps if s.get('name') == 'Check out unchanged product candidate')
    assert candidate['with']['ref'] == 'fc3184e884a39ecd761c719c86672dfc1f957f8a'
    run_step = next(s for s in steps if s.get('name', '').startswith('Diagnose the full'))
    assert '--budget 1500 --stack-interval 120' in run_step['run']
    assert run_step['run'].strip().endswith('exit $LASTEXITCODE')
    assert 'continue-on-error' not in run_step
    upload = next(s for s in steps if s.get('uses') == 'actions/upload-artifact@v4')
    assert upload['if'] == 'always()'

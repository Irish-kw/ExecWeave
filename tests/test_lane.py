from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from execweave import cli
from execweave.lane import backend as lane_backend
from execweave.lane import runner as lane_runner
from execweave.lane import service as lane_service

FIXTURE = Path(__file__).parent / "fixtures" / "lane" / "sequential_calls"
SESSION_ID = "3bc934d2-5c7e-441b-b65f-df02e1f3a0b4"


def _build(tmp_path: Path, lane_dir: Path = FIXTURE) -> dict:
    lane_backend.build(
        sensor_path=lane_dir / "sensor.log",
        ledger_path=lane_dir / "ledger.jsonl",
        pubkey_path=lane_dir / "ledger_pub.pem",
        session_id=SESSION_ID,
        mono_offset_ns=0,
        started_ns_wall=0,
        finished_ns_wall=0,
        agent_name="agent",
        command=[],
        out_events=tmp_path / "events.jsonl",
        out_attr=tmp_path / "lane_attribution.json",
    )
    return json.loads((tmp_path / "lane_attribution.json").read_text())


def test_audit_reproduces_recorded_attribution(tmp_path: Path) -> None:
    expected = json.loads((FIXTURE / "expected_lane_attribution.json").read_text())
    assert _build(tmp_path) == expected


def test_audit_binds_each_call_to_its_launched_root(tmp_path: Path) -> None:
    attribution = _build(tmp_path)
    assert attribution["ledger"]["valid"] is True
    assert attribution["duplicate_call_ids"] == []
    assert len(attribution["tool_calls"]) == 5
    for call in attribution["tool_calls"].values():
        assert call["method"] == "lane_exact"
        assert call["process_id"].startswith(f"process:{SESSION_ID}:")


def test_ledger_verification_detects_modification(tmp_path: Path) -> None:
    assert lane_service.verify_ledger(FIXTURE / "ledger.jsonl", FIXTURE / "ledger_pub.pem")["valid"] is True
    lines = (FIXTURE / "ledger.jsonl").read_text().splitlines()
    record = json.loads(lines[2])
    record["record"]["call_id"] = "another-call"
    lines[2] = json.dumps(record)
    tampered = tmp_path / "ledger.jsonl"
    tampered.write_text("\n".join(lines) + "\n")
    assert lane_service.verify_ledger(tampered, FIXTURE / "ledger_pub.pem")["valid"] is False


def test_sensor_lines_without_the_run_nonce_are_not_records(tmp_path: Path) -> None:
    nonce = (FIXTURE / "sensor.log.nonce").read_text().strip()
    lane_dir = tmp_path / "lane"
    shutil.copytree(FIXTURE, lane_dir)
    forged = '{"ev":"exec","ns":1,"cg":1,"pid":4242,"ppid":1,"uid":0,"filename":"/bin/forged"}\n'
    with open(lane_dir / "sensor.log", "a", encoding="utf-8") as fh:
        fh.write(forged)
    records = lane_backend.parse_sensor(lane_dir / "sensor.log")
    assert nonce
    assert not any(r.get("filename") == "/bin/forged" for r in records)


def test_cli_lane_verify(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["lane", "verify", str(FIXTURE / "ledger.jsonl")]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_cli_lane_audit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["lane", "audit", str(FIXTURE), "--output-dir", str(tmp_path / "out")]) == 0
    attribution = json.loads((tmp_path / "out" / "lane_attribution.json").read_text())
    assert len(attribution["tool_calls"]) == 5


def test_run_lane_requires_agent_user(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["run", "--backend", "lane", "--", "true"])
    assert "--agent-user" in capsys.readouterr().err


def test_lane_backend_is_only_offered_by_run(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["record", "--backend", "lane", "--", "true"])
    assert "execweave run --backend lane" in capsys.readouterr().err


def test_lane_unavailable_without_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lane_runner, "diagnostics", lambda: {"platform": "linux", "root": False, "bpftrace": True})
    with pytest.raises(lane_runner.LaneUnavailable):
        lane_runner.check_available()


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.geteuid() != 0 or shutil.which("bpftrace") is None
    or os.environ.get("EXECWEAVE_LANE_LIVE_USER") is None,
    reason="live lane run needs Linux, root, bpftrace and EXECWEAVE_LANE_LIVE_USER",
)
def test_live_lane_session_binds_routed_calls() -> None:
    import tempfile

    user = os.environ["EXECWEAVE_LANE_LIVE_USER"]
    tmp_path = Path(tempfile.mkdtemp(prefix="execweave-lane-test-"))
    os.chmod(tmp_path, 0o755)
    shutil.chown(tmp_path, user=user)
    script = (
        "import os, subprocess, sys\n"
        "for i in range(3):\n"
        "    subprocess.run([sys.executable, os.environ['EW_LANE_EXEC'], '--sock', os.environ['EW_LANE_SOCK'],\n"
        "                    '--call-id', f'call-{i}', '--', '/bin/sh', '-c', 'true'], check=True)\n"
    )
    agent = tmp_path / "agent.py"
    agent.write_text(script)
    os.chmod(agent, 0o644)
    result = lane_runner.run_session([sys.executable, str(agent)], agent_user=user, watch_root=tmp_path, output_root=tmp_path / "runs")
    attribution = json.loads(result.attribution.read_text())
    assert result.return_code == 0
    assert attribution["ledger"]["valid"] is True
    assert sorted(attribution["tool_calls"]) == ["call-0", "call-1", "call-2"]

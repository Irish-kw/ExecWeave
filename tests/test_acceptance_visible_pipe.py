from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ollama_visible_acceptance as visible  # noqa: E402


def test_pipe_capture_displays_output_before_child_exit(tmp_path, capsys) -> None:
    process = subprocess.Popen(
        [sys.executable, "-u", "-c",
         "import sys; print('READY api_key=private-value',flush=True); input(); print('DONE')"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
    )
    artifact = tmp_path / "client.txt"
    capture = visible._PipeCapture(process.stdout, artifact, label="OLLAMA")
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if artifact.exists() and "READY" in artifact.read_text(encoding="utf-8"):
                break
            time.sleep(0.02)
        assert process.poll() is None
        # Artifact and tee are emitted by one reader; wait briefly for the tee too.
        displayed = ""
        while time.monotonic() < deadline and "READY" not in displayed:
            displayed += capsys.readouterr().out
            time.sleep(0.01)
        assert "[OLLAMA] READY" in displayed
        assert "private-value" not in displayed
        assert "[REDACTED]" in displayed
        process.stdin.write("exit\n")
        process.stdin.flush()
        assert process.wait(timeout=5) == 0
        assert capture.join()
        assert "DONE" in artifact.read_text(encoding="utf-8")
        assert "private-value" not in artifact.read_text(encoding="utf-8")
        assert "DONE" in capture.drain_text()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)
        process.stdin.close()
        capture.join()

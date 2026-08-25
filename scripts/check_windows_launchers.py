from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _write_cmd_shim(path: Path) -> None:
    path.write_text(
        '@echo off\r\n"%EW_TEST_PYTHON%" -c "import time; time.sleep(0.15)"\r\n'
        "exit /b %ERRORLEVEL%\r\n",
        encoding="utf-8",
    )


def _verify_runtime_artifacts(root: Path, output_dir: str) -> None:
    run_dir = root / output_dir
    for name in ("events.jsonl", "graph.json", "viewer.html"):
        path = run_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"missing Windows launcher smoke artifact: {path}")


def _run_cmd(command: str, *, cwd: Path, env: dict[str, str]) -> None:
    comspec = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
    if not comspec:
        raise RuntimeError("cmd.exe is not available")
    subprocess.run([comspec, "/d", "/s", "/c", command], cwd=cwd, env=env, check=True)


def _run_powershell(command: str, *, cwd: Path, env: dict[str, str]) -> None:
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("Windows PowerShell is not available")
    subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-Command", command],
        cwd=cwd,
        env=env,
        check=True,
    )


def main() -> int:
    if os.name != "nt":
        print("Windows launcher smoke skipped on non-Windows host")
        return 0

    with tempfile.TemporaryDirectory(prefix="execweave-win-launch-") as directory:
        root = Path(directory)
        _write_cmd_shim(root / "codex.cmd")
        _write_cmd_shim(root / "cursor.cmd")

        env = os.environ.copy()
        env["PATH"] = f"{root}{os.pathsep}{env.get('PATH', '')}"
        env["EW_TEST_PYTHON"] = sys.executable

        cases = [
            (
                _run_cmd,
                "codex-cmd",
                "execweave-codex-record --backend portable --no-files --no-network "
                "--output-dir codex-cmd -- codex",
            ),
            (
                _run_powershell,
                "codex-powershell",
                "execweave-codex-record --backend portable --no-files --no-network "
                "--output-dir codex-powershell -- codex",
            ),
            (
                _run_cmd,
                "cursor-cmd",
                "execweave-cursor-record --backend portable --no-files --no-network "
                "--output-dir cursor-cmd -- cursor",
            ),
            (
                _run_powershell,
                "cursor-powershell",
                "execweave-cursor-record --backend portable --no-files --no-network "
                "--output-dir cursor-powershell -- cursor",
            ),
        ]

        for runner, output_dir, command in cases:
            runner(command, cwd=root, env=env)
            _verify_runtime_artifacts(root, output_dir)

    print("Windows CMD/PowerShell Codex/Cursor launcher smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import tomllib
import venv
from pathlib import Path


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def _console_script(root: Path, name: str) -> Path:
    scripts = root / ("Scripts" if os.name == "nt" else "bin")
    if os.name == "nt":
        return scripts / f"{name}.exe"
    return scripts / name


def _run(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    expected_version = project["project"]["version"]

    wheels = sorted((repo / "dist").glob("execweave-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one ExecWeave wheel in dist/, found {wheels}")
    wheel = wheels[0].resolve()

    with tempfile.TemporaryDirectory(prefix="execweave-wheel-smoke-") as directory:
        env_root = Path(directory) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_root)
        python = _venv_python(env_root)

        _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=repo)
        _run([str(python), "-m", "pip", "install", str(wheel)], cwd=repo)
        _run(
            [
                str(python),
                "-c",
                (
                    "from importlib.metadata import version; "
                    f"assert version('execweave') == {expected_version!r}; "
                    "print(version('execweave'))"
                ),
            ],
            cwd=repo,
        )

        commands = [
            [str(_console_script(env_root, "execweave")), "--help"],
            [str(_console_script(env_root, "execweave")), "top", "--help"],
            [str(_console_script(env_root, "execweave-scalability")), "--help"],
        ]
        for command in commands:
            if not Path(command[0]).is_file():
                raise RuntimeError(f"installed console script is missing: {command[0]}")
            _run(command, cwd=repo)

    print(f"clean wheel install smoke passed for ExecWeave {expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

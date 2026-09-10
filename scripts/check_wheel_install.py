from __future__ import annotations

import os
import subprocess
import tempfile
import venv
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


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
        root = Path(directory)
        env_root = root / "venv"
        work = root / "work"
        work.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(env_root)
        python = _venv_python(env_root)

        _run([str(python), "-m", "pip", "install", str(wheel)], cwd=work)
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
            cwd=work,
        )
        _run(
            [
                str(python), "-I", "-c",
                (
                    "from pathlib import Path; import execweave; "
                    f"source=Path({str(repo)!r}).resolve(); module=Path(execweave.__file__).resolve(); "
                    "assert not module.is_relative_to(source), (module, source); print(module)"
                ),
            ],
            cwd=work,
        )

        commands = [
            [str(_console_script(env_root, "execweave")), "--help"],
            [str(_console_script(env_root, "execweave")), "top", "--help"],
            [str(_console_script(env_root, "execweave-scalability")), "--help"],
            [str(_console_script(env_root, "execweave-inference-gateway")), "--help"],
            [str(_console_script(env_root, "execweave-openai-compatible")), "--help"],
            [str(_console_script(env_root, "execweave-anthropic")), "--help"],
            [str(_console_script(env_root, "execweave-http-proxy")), "--help"],
            [str(_console_script(env_root, "execweave-litellm-callback")), "--print-callback"],
            [str(_console_script(env_root, "execweave-litellm-callback")), "--print-config"],
        ]
        for command in commands:
            if not Path(command[0]).is_file():
                raise RuntimeError(f"installed console script is missing: {command[0]}")
            _run(command, cwd=work)

        _run([str(python), "-m", "pip", "uninstall", "-y", "execweave"], cwd=work)
        _run([str(python), "-I", "-c", "import importlib.util; assert importlib.util.find_spec('execweave') is None"], cwd=work)
        for name in ("execweave", "execweave-top"):
            if _console_script(env_root, name).exists():
                raise RuntimeError(f"console script remained after uninstall: {name}")
        _run([str(python), "-m", "pip", "install", str(wheel)], cwd=work)
        _run([str(_console_script(env_root, "execweave")), "--help"], cwd=work)

    print(f"clean wheel install/uninstall/reinstall smoke passed for ExecWeave {expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

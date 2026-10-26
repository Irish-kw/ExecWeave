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


def venv_python(root: Path) -> Path:
    return root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def console_script(root: Path, name: str) -> Path:
    scripts = root / ('Scripts' if os.name == 'nt' else 'bin')
    return scripts / (f'{name}.exe' if os.name == 'nt' else name)


def run(command: list[str], cwd: Path) -> None:
    print('+', ' '.join(command))
    subprocess.run(command, cwd=cwd, check=True, timeout=180)


def probe(python: Path, *, version: str, repo: Path, cwd: Path) -> None:
    code = (
        'from pathlib import Path; from importlib.metadata import version; import execweave; '
        f"source=Path({str(repo)!r}).resolve(); module=Path(execweave.__file__).resolve(); "
        'assert not module.is_relative_to(source), (module, source); '
        f"assert version('execweave') == {version!r}; print(module); print(version('execweave'))"
    )
    run([str(python), '-I', '-c', code], cwd)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    version = tomllib.loads((repo / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    archives = sorted((repo / 'dist').glob('execweave-*.tar.gz'))
    if len(archives) != 1:
        raise RuntimeError(f'expected exactly one ExecWeave sdist, found {archives}')
    archive = archives[0].resolve()
    with tempfile.TemporaryDirectory(prefix='execweave-sdist-smoke-') as directory:
        root = Path(directory)
        env_root, work = root / 'venv', root / 'work'
        work.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(env_root)
        python = venv_python(env_root)
        run([str(python), '-m', 'pip', 'install', str(archive)], work)
        probe(python, version=version, repo=repo, cwd=work)
        for name in ('execweave', 'execweave-top', 'execweave-inference-gateway'):
            command = console_script(env_root, name)
            if not command.is_file():
                raise RuntimeError(f'installed console script missing: {command}')
            run([str(command), '--help'], work)
        run([str(python), '-m', 'pip', 'uninstall', '-y', 'execweave'], work)
        run([str(python), '-I', '-c', "import importlib.util; assert importlib.util.find_spec('execweave') is None"], work)
        run([str(python), '-m', 'pip', 'install', str(archive)], work)
        probe(python, version=version, repo=repo, cwd=work)
    print(f'clean sdist install/uninstall/reinstall passed for ExecWeave {version}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

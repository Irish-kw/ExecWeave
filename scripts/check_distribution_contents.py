from __future__ import annotations

import hashlib
import json
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise RuntimeError('distribution contains duplicate archive paths')
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:
            raise RuntimeError(f'unsafe archive path: {name}')
        lowered = name.lower()
        if '__pycache__' in path.parts or lowered.endswith(('.pyc', '.pyo')):
            raise RuntimeError(f'cached Python bytecode leaked into distribution: {name}')
        if '/.git/' in f'/{lowered}/' or '/.execweave/' in f'/{lowered}/':
            raise RuntimeError(f'local repository/runtime state leaked into distribution: {name}')
        if 'source.bundle' in lowered or '/artifacts/' in f'/{lowered}/':
            raise RuntimeError(f'acceptance evidence leaked into distribution: {name}')


def runtime_files(repo: Path) -> dict[str, str]:
    result = {}
    root = repo / 'src' / 'execweave'
    for path in root.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        result[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return result


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    version = tomllib.loads((repo / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    wheel = sorted((repo / 'dist').glob('execweave-*.whl'))
    sdist = sorted((repo / 'dist').glob('execweave-*.tar.gz'))
    if len(wheel) != 1 or len(sdist) != 1:
        raise RuntimeError(f'expected one wheel and one sdist, got wheel={wheel}, sdist={sdist}')
    wheel, sdist = wheel[0], sdist[0]
    expected = runtime_files(repo)

    with zipfile.ZipFile(wheel) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        safe(names)
        noncanonical = [info.filename for info in infos if info.create_system != 3]
        if noncanonical:
            raise RuntimeError(
                'wheel creator-platform metadata is not canonical: '
                + ', '.join(noncanonical[:5])
            )
        wheel_runtime = {
            name.removeprefix('execweave/'): digest(archive.read(name))
            for name in names if name.startswith('execweave/') and not name.endswith('/')
        }
        metadata = [name for name in names if name.endswith('.dist-info/METADATA')]
        record = [name for name in names if name.endswith('.dist-info/RECORD')]
        if len(metadata) != 1 or len(record) != 1:
            raise RuntimeError('wheel must contain exactly one METADATA and RECORD')

    root = f'execweave-{version}/'
    with tarfile.open(sdist, 'r:gz') as archive:
        names = archive.getnames()
        safe(names)
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        sdist_runtime = {}
        prefix = root + 'src/execweave/'
        for name, member in members.items():
            if name.startswith(prefix):
                handle = archive.extractfile(member)
                assert handle is not None
                sdist_runtime[name.removeprefix(prefix)] = digest(handle.read())
        for required in (root + 'pyproject.toml', root + 'README.md', root + 'LICENSE'):
            if required not in members:
                raise RuntimeError(f'sdist missing project metadata: {required}')

    for label, actual in [('wheel', wheel_runtime), ('sdist', sdist_runtime)]:
        missing = sorted(path for path, sha in expected.items() if actual.get(path) != sha)
        extra = sorted(set(actual) - set(expected))
        if missing or extra:
            raise RuntimeError(f'{label} runtime bytes differ from source: missing_or_changed={missing}, extra={extra}')

    report = {
        'version': version,
        'runtime_files': len(expected),
        'wheel_sha256': digest(wheel.read_bytes()),
        'sdist_sha256': digest(sdist.read_bytes()),
        'wheel_source_parity': True,
        'sdist_source_parity': True,
        'wheel_creator_platform_canonical': True,
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

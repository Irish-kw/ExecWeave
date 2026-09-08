"""Archive the exact tracked bytes read by CI before and after acceptance tests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def capture(repo: Path) -> dict:
    def git(*args: str) -> bytes:
        return subprocess.check_output(['git', *args], cwd=repo)
    tracked = git('ls-tree', '-rz', '--full-tree', 'HEAD').split(b'\0')
    files = {}
    for row in tracked:
        if not row:
            continue
        metadata, raw_path = row.split(b'\t', 1)
        mode, kind, object_sha = metadata.decode().split()
        if kind != 'blob':
            continue
        path = raw_path.decode('utf-8')
        local = repo / path
        # Preserve physical checkout hashes; Git object hashes are also archived
        # because Windows autocrlf may intentionally change on-disk line endings.
        content = str(local.readlink()).encode() if local.is_symlink() else local.read_bytes()
        files[path] = {'git_blob': object_sha, 'mode': mode,
                       'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
    dirty = git('status', '--porcelain', '--untracked-files=no').decode().strip()
    assert not dirty, f'tracked source is dirty: {dirty}'
    return {'commit': git('rev-parse', 'HEAD').decode().strip(),
            'tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
            'tracked_files': files, 'tracked_status': dirty}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    result = capture(Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2), encoding='utf-8')
    if args.compare:
        assert result == json.loads(args.compare.read_text(encoding='utf-8')), 'source bytes changed during acceptance'
    print(json.dumps({'commit': result['commit'], 'tree': result['tree'],
                      'files': len(result['tracked_files']), 'source_invariant': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

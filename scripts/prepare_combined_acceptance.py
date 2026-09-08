"""Prepare a local-only, exact-tree acceptance checkout for two unmerged PRs.

No remote ref is written. Both heads must descend from the explicitly pinned main;
merging their histories in either order must produce the same tree. A local merge
commit gives existing source/wheel provenance checks a clean, auditable baseline.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def git(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ['git', *arguments], cwd=repo, text=True, encoding='utf-8', stderr=subprocess.PIPE,
    ).strip()


def prepare(repo: Path, main: str, pr69: str, pr70: str, output: Path) -> dict:
    repo, output = repo.resolve(), output.resolve()
    for name, revision in [('main', main), ('PR69', pr69), ('PR70', pr70)]:
        if not re.fullmatch(r'[0-9a-f]{40}', revision):
            raise ValueError(f'{name} requires an exact 40-character commit SHA')
        if git(repo, 'rev-parse', '--verify', revision + '^{commit}') != revision:
            raise ValueError(f'{name} does not identify the expected commit')
    if output.exists():
        raise ValueError('acceptance output must not already exist; existing work is never removed')
    if output.is_relative_to(repo):
        raise ValueError('acceptance checkout must be outside the source checkout')
    for head in (pr69, pr70):
        git(repo, 'merge-base', '--is-ancestor', main, head)
    # Since main is an ancestor of each tip, main -> tip is a fast-forward;
    # these two merges therefore cover main -> 69 -> 70 and main -> 70 -> 69.
    forward = git(repo, 'merge-tree', '--write-tree', pr69, pr70)
    reverse = git(repo, 'merge-tree', '--write-tree', pr70, pr69)
    if not re.fullmatch(r'[0-9a-f]{40}', forward) or forward != reverse:
        raise ValueError(f'merge-order trees differ: {forward!r} versus {reverse!r}')
    git(repo, 'worktree', 'add', '--detach', str(output), pr70)
    identity = ('-c', 'user.name=ExecWeave RC verifier', '-c', 'user.email=rc-verifier@example.invalid',
                '-c', 'commit.gpgsign=false')
    git(output, *identity, 'merge', '--no-commit', '--no-ff', pr69)
    actual = git(output, 'write-tree')
    if actual != forward:
        raise ValueError('checked-out merge differs from the merge-order proof')
    if (Path(git(output, 'rev-parse', '--git-path', 'MERGE_HEAD'))).is_file():
        git(output, *identity, 'commit', '-m', 'Local-only combined release acceptance; never pushed')
    if git(output, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('combined checkout is not clean')
    if git(output, 'rev-parse', 'HEAD^{tree}') != forward:
        raise ValueError('local acceptance commit does not preserve the combined tree')
    return {'main_sha': main, 'pr69_sha': pr69, 'pr70_sha': pr70,
            'order_69_70_tree': forward, 'order_70_69_tree': reverse,
            'combined_tree': forward, 'local_only_commit': git(output, 'rev-parse', 'HEAD'),
            'checkout': str(output), 'remote_refs_modified': False,
            'merge_order_equal': True, 'source_clean': True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--main', required=True)
    parser.add_argument('--pr69', required=True)
    parser.add_argument('--pr70', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.repo, args.main, args.pr69, args.pr70, args.output)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

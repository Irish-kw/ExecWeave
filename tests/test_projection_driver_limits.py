"""Keep large Unicode fixtures executable under Windows command-line limits."""
from __future__ import annotations

import subprocess

from test_projection_bridge_evidence import project, node, edge


def test_large_projection_program_uses_stdin_without_truncation(monkeypatch):
    run = subprocess.run
    seen = []
    def bounded_argv(argv, *args, **kwargs):
        assert argv[1:] == ['-'], 'the JavaScript must not travel in the command line'
        assert len(subprocess.list2cmdline(argv)) < 512
        assert len(kwargs['input']) > 65536
        seen.append(True)
        return run(argv, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', bounded_argv)
    payload = '長路徑與證據' * 12000
    raw = {'nodes': [node('a', 'agent'), node('hidden', 'provider_session'),
                     node('file', 'file', path=payload)],
           'edges': [edge('owner', 'a', 'hidden'), edge('evidence', 'hidden', 'file')]}
    result = project(raw)
    assert seen == [True]
    assert next(n for n in result['nodes'] if n['id'] == 'file')['attributes']['path'] == payload
    assert any(e['source'] == 'a' and e['target'] == 'file' for e in result['edges'])

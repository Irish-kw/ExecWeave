"""A local negative observation example; no provider, credentials, or elevation.

Run from an installed wheel with ``python -m execweave.observation_demo``.
The task and its independent assertions pass, but observation remains incomplete.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .live import run_live

_WORKLOAD = '''from pathlib import Path
import subprocess, sys
source = "print(' '.join(str(n) for n in range(2, 30) if all(n % d for d in range(2, n))))\\n"
Path('primes.py').write_text(source, encoding='utf-8')
result = subprocess.run([sys.executable, 'primes.py'], capture_output=True, text=True, check=True)
Path('output.txt').write_text(result.stdout, encoding='utf-8')
'''
_EXPECTED = "2 3 5 7 11 13 17 19 23 29"


def run_example(root: Path) -> dict:
    # The example may create its own directory, never reuse a user's prior run.
    root = root.expanduser().absolute()
    root.mkdir(parents=True, exist_ok=False)
    result = run_live([sys.executable, "-c", _WORKLOAD], watch_root=root, output_dir=root,
                      open_browser=False, linger_seconds=0, collect_network=False)
    output = root / "output.txt"
    verified = result.return_code == 0 and output.is_file() and output.read_text().strip() == _EXPECTED
    graph = json.loads(result.graph.read_text(encoding="utf-8"))
    observation = graph["observation_assessment"]
    final = json.loads((root / "finalization.json").read_text(encoding="utf-8"))
    expected_failure = (observation["state"] == "observation_incomplete"
                        and {"unknown_file_writer", "file_snapshot_not_captured"}
                        <= set(observation["reasons"])
                        and final["observation_assessment"] == observation)
    return {
        "example": "successful_task_incomplete_observation", "uses_real_provider": False,
        "ordinary_exit_only_trace": "success" if result.return_code == 0 else "failure",
        "execution": {"return_code": result.return_code, "state": graph["session_outcome"]["execution_state"]},
        "independent_example_task_verification": {"state": "passed" if verified else "failed",
            "method": "exact_expected_primes_output", "expected": _EXPECTED,
            "scope": "This example's assertion, not a general task verifier."},
        "observation": observation,
        "observation_acceptance": "FAIL" if observation["state"] == "observation_incomplete" else "NOT_VERIFIED",
        "example_reproduced": verified and expected_failure,
        "graph": str(result.graph), "viewer": str(result.viewer),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory; must not exist")
    args = parser.parse_args(argv)
    try:
        report = run_example(args.output_dir)
    except (OSError, ValueError) as exc:
        print(json.dumps({"example_reproduced": False, "environment_error": type(exc).__name__}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    # Zero here says that the negative example reproduced; it is not observation PASS.
    return 0 if report["example_reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

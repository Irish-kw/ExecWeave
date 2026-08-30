from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITICAL_UNCHANGED = (
    "src/execweave/http_proxy.py",
    "tests/test_http_proxy.py",
    "scripts/audit_i18n_parity.py",
    "pyproject.toml",
    "src/execweave/__init__.py",
)
SKIP_MARKERS = (
    "pytest.mark.skip",
    "pytest.mark.xfail",
    "pytest.skip(",
)


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], check=check)


def _extract_git_tree(ref: str, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", ref],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        bundle.extractall(destination, filter="data")


def _pytest_node_ids(tree: Path) -> set[str]:
    env = os.environ.copy()
    source = str(tree / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = source if not existing else os.pathsep.join((source, existing))
    completed = _run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=tree,
        env=env,
    )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if "::" in line and line.strip().startswith("tests/")
    }


def _assert_test_identity_floor(baseline_ref: str) -> tuple[int, int]:
    current = _pytest_node_ids(ROOT)
    with tempfile.TemporaryDirectory(prefix="execweave-baseline-") as tmp:
        baseline_tree = Path(tmp)
        _extract_git_tree(baseline_ref, baseline_tree)
        baseline = _pytest_node_ids(baseline_tree)
    if not baseline or not current:
        raise RuntimeError(
            "test node-ID collection returned an empty set; refusing a vacuous subset check: "
            f"baseline={len(baseline)} current={len(current)}"
        )
    missing = sorted(baseline - current)
    if missing:
        preview = "\n".join(missing[:25])
        suffix = "\n..." if len(missing) > 25 else ""
        raise RuntimeError(
            "baseline test node IDs disappeared:\n"
            f"{preview}{suffix}\n"
            f"missing={len(missing)} baseline={len(baseline)} current={len(current)}"
        )
    return len(baseline), len(current)


def _assert_existing_tests_untouched(baseline_ref: str) -> list[str]:
    completed = _git("diff", "--name-status", f"{baseline_ref}...HEAD", "--", "tests")
    added: list[str] = []
    violations: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        status, *paths = line.split("\t")
        if status == "A" and len(paths) == 1:
            added.append(paths[0])
        else:
            violations.append(line)
    if violations:
        raise RuntimeError(
            "existing tests were modified, deleted, or renamed:\n" + "\n".join(violations)
        )
    return added


def _assert_no_new_skip_or_xfail(baseline_ref: str) -> None:
    diff = _git("diff", "--unified=0", f"{baseline_ref}...HEAD", "--", "tests").stdout
    offenders = []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if any(marker in line for marker in SKIP_MARKERS):
            offenders.append(line)
    if offenders:
        raise RuntimeError("new skip/xfail markers are not allowed:\n" + "\n".join(offenders))


def _assert_critical_files_unchanged(baseline_ref: str) -> None:
    completed = _git(
        "diff",
        "--name-only",
        f"{baseline_ref}...HEAD",
        "--",
        *CRITICAL_UNCHANGED,
    )
    changed = [line for line in completed.stdout.splitlines() if line.strip()]
    if changed:
        raise RuntimeError("release red-line files changed:\n" + "\n".join(changed))


def _assert_i18n_audit() -> str:
    completed = _run([sys.executable, "scripts/audit_i18n_parity.py"])
    output = completed.stdout.strip()
    if "failures=0" not in output:
        raise RuntimeError(
            "i18n audit exited successfully but did not report failures=0:\n" + output
        )
    return output.splitlines()[-1] if output else "failures=0"


def _probe(*args: str) -> dict[str, object]:
    completed = _run([sys.executable, "scripts/probe_provider_capability.py", *args])
    return json.loads(completed.stdout)


def _assert_explicit_capability_matrix() -> tuple[int, int]:
    inventory = _probe("--inventory-only")
    matrix = _probe()
    entries = inventory.get("entries")
    rows = matrix.get("rows")
    if not isinstance(entries, list) or not isinstance(rows, list):
        raise RuntimeError("capability probe did not emit machine-readable entries/rows")

    expected: set[tuple[str, str, str, str]] = set()
    expected_tier_a: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("inventory entry is not an object")
        client = entry["client"]
        fields = entry["required_fields"]
        for auth_mode in entry["auth_modes"]:
            for surface in entry["surfaces"]:
                for field in fields:
                    key = (client, auth_mode, surface, field)
                    expected.add(key)
                    if entry["tier"] == "A":
                        expected_tier_a.add(key)

    observed: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("matrix row is not an object")
        key = (row["client"], row["auth_mode"], row["surface"], row["field"])
        if key in observed:
            raise RuntimeError(f"duplicate capability matrix row: {key}")
        observed[key] = row

    missing = sorted(expected - observed.keys())
    unexpected = sorted(observed.keys() - expected)
    if missing or unexpected:
        raise RuntimeError(
            f"capability matrix key mismatch: missing={missing[:10]} unexpected={unexpected[:10]}"
        )

    for key in expected:
        row = observed[key]
        if row.get("availability") != "not_observed":
            raise RuntimeError(f"no-artifact matrix must be explicit not_observed: {key}: {row}")
        if not row.get("notes"):
            raise RuntimeError(f"no-artifact matrix row lacks reason: {key}")
        if row.get("evidence_source") != "probe:no_data":
            raise RuntimeError(f"no-artifact matrix row lacks no-data provenance: {key}: {row}")

    probe = matrix.get("probe")
    if not isinstance(probe, dict) or probe.get("network_used") is not False:
        raise RuntimeError("provider capability probe must remain offline")
    return len(expected_tier_a), len(expected)


def _assert_codex_encrypted_reasoning_boundary() -> None:
    fixture = ROOT / "tests" / "fixtures" / "codex_multi_agent" / "rollout-main.jsonl"
    matrix = _probe("--artifact", f"codex-cli:subscription={fixture}")
    rows = matrix["rows"]
    matches = [
        row
        for row in rows
        if row["client"] == "codex-cli"
        and row["auth_mode"] == "subscription"
        and row["surface"] == "agent"
        and row["field"] == "reasoning"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one Codex reasoning row, got {len(matches)}")
    row = matches[0]
    if row["availability"] != "opaque_encrypted":
        raise RuntimeError(f"Codex encrypted reasoning was overclaimed: {row}")
    if row["decryptability"] != "no_local_decryptor_observed":
        raise RuntimeError(f"Codex decryptability boundary changed: {row}")
    if "server" in str(row.get("notes") or "").lower():
        raise RuntimeError(f"Codex reasoning notes contain a server-side claim: {row}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate ExecWeave release-stage integrity invariants.")
    parser.add_argument(
        "--baseline-ref",
        required=True,
        help="immutable base commit/ref used to reconstruct baseline test node IDs",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    _git("cat-file", "-e", f"{args.baseline_ref}^{{commit}}")

    baseline_count, current_count = _assert_test_identity_floor(args.baseline_ref)
    added_tests = _assert_existing_tests_untouched(args.baseline_ref)
    _assert_no_new_skip_or_xfail(args.baseline_ref)
    _assert_critical_files_unchanged(args.baseline_ref)
    i18n_status = _assert_i18n_audit()
    tier_a_rows, total_rows = _assert_explicit_capability_matrix()
    _assert_codex_encrypted_reasoning_boundary()

    print(
        json.dumps(
            {
                "baseline_ref": args.baseline_ref,
                "baseline_test_node_ids": baseline_count,
                "current_test_node_ids": current_count,
                "baseline_subset_current": True,
                "added_test_files": added_tests,
                "new_skip_or_xfail": False,
                "critical_release_files_unchanged": True,
                "i18n_audit": i18n_status,
                "tier_a_explicit_rows": tier_a_rows,
                "matrix_explicit_rows": total_rows,
                "codex_encrypted_reasoning_boundary": "opaque_encrypted/no_local_decryptor_observed",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

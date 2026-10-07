"""Exact, branch-scoped acceptance-test migrations for PR #112.

Only the listed complete postimages are authorized. The caller also enforces the
unconditional historical node-ID floor before forwarding these explanations to
the existing stage checker. No deletion, rename, skip, or xfail is authorized.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

BASELINE = "142ea1a96c4dfeae9ad204ac04cd8e3c17855192"
BRANCH = "fix/observation-integrity-0.8.35"
CHANGES = {
    "tests/test_agent_bootstrap.py": (
        "865e65b2db1fe8027710f583f7ee66c0a849a2a3d611d796acf3c663b0b9f301",
        "PR #112: configured_unverified and absolute module hooks replace the old active/bare-PATH assertion. Historical parameter IDs, preservation, inertness, and idempotence assertions remain.",
    ),
    "tests/test_antigravity_cursor_launch.py": (
        "7a28a38c3c0340498e3eace17e6c0625de400a6344d59182d929e4d8de2f3b88",
        "PR #112: configured_unverified and interpreter-bound Antigravity hooks reflect explicit user installation, not proof of delivered evidence. Launcher and configuration assertions remain.",
    ),
    "tests/test_audit_closure_20260917.py": (
        "26d6d5aac93e9102bc3d92b1c530ef7254076aa5cd4a8f468a624114d38ab28e",
        "PR #112: require observation_incomplete in addition to preserving the original succeeded assertion on execution_state; process exit no longer implies observation completeness.",
    ),
    "tests/test_investigation_integration.py": (
        "f751e7ccea64d792d5cebbafcf79b2fa54fc3e425aba2854a04052630b21a154",
        "PR #112: require observation_incomplete and retain failed on execution_state; archive/export completion remains a separate assertion.",
    ),
    "tests/test_pypi_0812_regressions.py": (
        "b27d9ad4494cb63a804009192580bb297a513c94128ac3f3edd3c11f0446b101",
        "PR #112: retain the historical test ID but reject whole-output-directory exclusion, the independently reproduced cause of dropped primes.py/output.txt; exact internal artifact exclusions remain required.",
    ),
    "tests/test_live_auth.py": (
        "40f9a95878e3b378d685016563cba2ec153f6f9d83b7d1b389599cc88dca1c21",
        "PR #112: preserve the historical live-auth test IDs while replacing URL query-token bootstrap with one-time POST pairing plus an HttpOnly SameSite cookie; header-token API access, 401 evidence-route protection, and no-persistence assertions remain.",
    ),
    "tests/test_live.py": (
        "7a6f6f61695421c64627c910a651bed3fa6972c8c06430879ec3e96dcddfb7ff",
        "PR #112: preserve the historical live graph test IDs while receiving the API token through the private callback instead of parsing it from the announced URL; snapshot, graph, viewer, finalization, and terminal-result assertions remain.",
    ),
    "tests/test_top_detached.py": (
        "40562dd27b4831e2eb5beb9ee6ae8aea5591664577d445c4b38c36bcc867c86c",
        "PR #112: preserve the historical detached-top test IDs while supplying the localhost API credential through announce_api_token and retaining private token-file, attach-command, cleanup, and dashboard-launch assertions.",
    ),
    "tests/test_conversation_access.py": (
        "aceecde41e02fdefea3cbb5b786799632e29d67dfddcee750138c7b72cb85121",
        "PR #112: preserve the historical conversation-access test IDs while forbidding query-token authentication and browser token JavaScript; authenticated header access, same-origin browser fetches, conversation boundaries, and content-route authorization remain required.",
    ),
    "tests/test_inference_gateway_full_fidelity.py": (
        "5ca999addcf9cc608febac13819c13f2bf88eaf60937345b1e367fb703f4a93d",
        "PR #112: preserve the historical LiteLLM full-fidelity live test ID while making its plaintext capture opt-in explicit; the test still requires complete prompt content references and graph materialization when full capture is requested.",
    ),
}


def allowance_args(root: Path, *, baseline_ref: str, head_ref: str) -> list[str]:
    if head_ref != BRANCH:
        return []
    if baseline_ref != BASELINE:
        raise RuntimeError("PR #112 test migrations require their exact reviewed baseline")
    result = []
    for name, (expected, reason) in CHANGES.items():
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"reviewed test missing or linked: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"unreviewed test postimage: {name}")
        result.extend(("--allow-test-change", f"{name}={reason}"))
    return result

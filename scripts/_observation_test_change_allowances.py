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
    "tests/test_relay_prompt_live_e2e.py": (
        "d1b3af4f7b5503d2581d2655718ddbf79a1303db8cbbae19d47c66ddf8023c92",
        "PR #112: preserve the historical relay/live browser test ID while replacing query-string authentication with the supported X-ExecWeave-Token header; prompt-before-response ordering, live DOM visibility, final parity, and no-duplication checks remain unchanged.",
    ),
    "tests/test_delivery_native_browser.py": (
        "cf31625a1b6a5a68b9cfb8c07a5b4c22e299afec4a801ba8d467dd775b70bf6d",
        "PR #112: preserve the historical native delivery test IDs while authenticating the direct localhost handler through the supported header and replacing CSP-incompatible string-eval waits with bounded locator polling; archive verification and tamper rejection assertions remain unchanged.",
    ),
    "tests/test_live_final_snapshot_e2e.py": (
        "70ae07994e1f9782e99aae404ed9f9632be06317bcf7456e84320c08ef4019ec",
        "PR #112: preserve the historical final-snapshot browser test ID while moving direct-handler authentication to the supported header and replacing CSP-incompatible string-eval waits with bounded locator polling; terminal-delta ordering, polling stop, DOM identity, and reopened-viewer parity remain required.",
    ),
    "tests/test_v079_review_e2e.py": (
        "11a07bd88f10dc7fe188c3804a45381d9e76756bff66f1f742a1c2613996487c",
        "PR #112: preserve all historical v0.7.9 review browser test IDs while replacing query-string live authentication with the supported header; multi-agent evidence states, same-document live behavior, and final-view semantics remain unchanged.",
    ),
    "tests/test_viewer_agent_isolation_e2e.py": (
        "c82c69384cdcb3801dc085a31b19a469d7c719930de89513bd9b6f30478604ba",
        "PR #112: preserve the historical viewer-isolation test IDs while migrating direct live browser and conversation-index requests from query credentials to the supported authentication header; graph isolation, raw evidence, content boundaries, and live/static parity remain unchanged.",
    ),
    "tests/test_dashboard_round_fold_state_e2e.py": (
        "f71e81242840bdf46db9020da08fc93359dcba2170895775a9fd2d85db62650a",
        "PR #112: preserve the historical dashboard round-fold-state test ID while replacing query-string live authentication with the supported header; fold persistence and live/static state behavior remain unchanged.",
    ),
    "tests/test_ollama_visible_acceptance.py": (
        "b649a31b5273dbaf6551f6a8bd33523e2ffddc98c6a9e144da2a75385e376aea",
        "PR #112: preserve the historical Ollama visible-acceptance test ID while changing its URL parser contract to require a credential-free loopback URL plus a separately announced one-time pairing code; provider availability, cleanup, and evidence checks remain unchanged.",
    ),
    "tests/test_live_logs_export.py": (
        "2a2b6a640884e151c01ff39d5a386d2c5f539959d7bbb60236dcb899f48f5d90",
        "PR #112: preserve the historical replay/live-auth test ID while reversing its obsolete browser-secret assertions: the authenticated live shell must not embed the API token or header credential and must use same-origin cookie authentication; final-document replacement prohibitions remain unchanged.",
    ),
    "tests/test_rule_pack.py": (
        "d79ab8a8e1d25cef16ce77570f1bbd3780045227a0a7f636f0a28dd516030758",
        "PR #112: preserve every historical rule-pack test ID while adding the current graph schema version to the synthetic graph fixture so the CLI exercises the new strict versioned reader rather than depending on an invalid versionless artifact.",
    ),
    "tests/test_cursor_lifecycle_handoff.py": (
        "5513ed3187f901c894afb2d60ebf3e826c2070822f0fc5861d0734a9532837d9",
        "PR #112: preserve all historical Cursor handoff test IDs and exact executable/ancestry assertions while extending only the synthetic child lifetime to make the real-process integration deterministic on slower Windows runners; attribution rules are not relaxed.",
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

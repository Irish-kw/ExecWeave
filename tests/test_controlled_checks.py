"""Actual fixed-predicate execution, signatures and pinned-policy verification."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from execweave import controlled_checks as cc
from execweave.viewer_controlled_checks import CONTROLLED_CORE_JS
from execweave.viewer_archive_verifier import ARCHIVE_VERIFIER_JS
from test_task_validation_reports import graph


def setup_case(tmp_path):
    data = graph()
    artifact = tmp_path / "result.json"
    artifact.write_bytes(b'{"status":"ready","count":3,"safe":true}')
    policy = {
        "format": cc.POLICY_FORMAT,
        "name": "Delivery criteria",
        "checks": [
            {
                "id": "bytes",
                "path": "result.json",
                "op": "sha256_equals",
                "expected": cc.digest(artifact.read_bytes()),
            },
            {
                "id": "status",
                "path": "result.json",
                "op": "json_pointer_equals",
                "pointer": "/status",
                "expected": "ready",
            },
            {
                "id": "visible",
                "path": "result.json",
                "op": "utf8_contains",
                "expected": '"count":3',
            },
        ],
    }
    raw = cc.encoded(policy)
    private = Ed25519PrivateKey.generate()
    profile = cc.make_profile(
        private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ),
        raw,
        "Independent QA",
    )
    envelope = cc.execute_checks(data, "task:1", raw, ["result.json=" + str(artifact)], private)
    return data, artifact, policy, raw, private, profile, envelope


def signed(key, payload):
    raw = cc.encoded(payload)
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "format": cc.RECEIPT_FORMAT,
        "key_id": cc.digest(public),
        "payload": raw.decode(),
        "signature_b64": cc._b64(key.sign(cc.DOMAIN + raw)),
    }


def test_actual_predicates_hash_and_sign_same_buffer(tmp_path):
    data, artifact, policy, raw, key, profile, envelope = setup_case(tmp_path)
    before = copy.deepcopy(data)
    result = cc.verify_receipt(envelope, profile, data, "task:1")
    assert result["state"] == "checks_passed" and result["counts"] == dict(
        passed=3, failed=0, error=0
    )
    assert result["signature_verified"] and not result["whole_task_verified"]
    payload = result["payload"]
    assert {r["artifact_sha256"] for r in payload["results"]} == {cc.digest(artifact.read_bytes())}
    assert len(payload["artifacts"]["entries"]) == 1 and data == before
    assert str(tmp_path) not in envelope["payload"]
    assert artifact.read_bytes() == b'{"status":"ready","count":3,"safe":true}'


def test_changes_after_capture_cannot_change_evaluated_bytes(tmp_path, monkeypatch):
    data, artifact, policy, raw, key, profile, _ = setup_case(tmp_path)
    original = cc._read_selected
    captured = artifact.read_bytes()

    def change_after_read(path):
        result = original(path)
        Path(path).write_bytes(b'{"status":"wrong","count":0}')
        return result

    monkeypatch.setattr(cc, "_read_selected", change_after_read)
    envelope = cc.execute_checks(data, "task:1", raw, ["result.json=" + str(artifact)], key)
    result = cc.verify_receipt(envelope, profile, data, "task:1")
    assert result["state"] == "checks_passed"
    assert result["payload"]["artifacts"]["entries"][0]["sha256"] == cc.digest(captured)
    assert cc.digest(artifact.read_bytes()) != cc.digest(captured)


@pytest.mark.parametrize("change", ["payload", "signature", "key", "policy-pin", "self-profile"])
def test_tampered_untrusted_or_unapproved_result_is_rejected(tmp_path, change):
    data, artifact, policy, raw, key, profile, envelope = setup_case(tmp_path)
    if change == "payload":
        envelope["payload"] = envelope["payload"].replace("predicate_true", "predicate_forged", 1)
    elif change == "signature":
        envelope["signature_b64"] = cc._b64(bytes(64))
    elif change == "key":
        other = Ed25519PrivateKey.generate()
        profile = cc.make_profile(
            other.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
            raw,
            "other",
        )
    elif change == "policy-pin":
        profile["policy_sha256"] = "f" * 64
    else:
        envelope["profile"] = profile
    with pytest.raises(ValueError):
        cc.verify_receipt(envelope, profile, data, "task:1")


@pytest.mark.parametrize(
    "change", ["task", "run", "session", "path", "duplicate", "partial", "inferred"]
)
def test_receipt_remains_bound_to_exact_native_task(tmp_path, change):
    data, _, _, _, _, profile, envelope = setup_case(tmp_path)
    if change == "task":
        data["nodes"][0]["name"] = "a different goal"
    elif change == "run":
        data["run_id"] = "other"
    elif change == "session":
        data["session_id"] = "other"
    elif change == "path":
        data["source_path"] = "/other/events.jsonl"
    elif change == "duplicate":
        data["nodes"].append(copy.deepcopy(data["nodes"][0]))
    elif change == "partial":
        data["live_payload_compact"] = True
    else:
        data["nodes"][0]["inferred"] = True
    with pytest.raises(ValueError):
        cc.verify_receipt(envelope, profile, data, "task:1")


@pytest.mark.parametrize(
    "contents,op,pointer,expected,outcome",
    [
        (b"", "sha256_equals", None, cc.digest(b""), "passed"),
        (b"\xff\x00", "sha256_equals", None, cc.digest(b"\xff\x00"), "passed"),
        (b"\xff", "utf8_contains", None, "x", "error"),
        (b'{"x":false}', "json_pointer_equals", "/x", 0, "failed"),
        (b'{"x":1}', "json_pointer_equals", "/x", True, "failed"),
        (b'{"a/b":{"~k":[3]}}', "json_pointer_equals", "/a~1b/~0k/0", 3, "passed"),
        (b'{"x":1,"x":2}', "json_pointer_equals", "/x", 2, "error"),
        (b'{"x":0.5}', "json_pointer_equals", "/x", 1, "error"),
        (b'{"x":null}', "json_pointer_equals", "/x", None, "passed"),
        (b'{"x":[]}', "json_pointer_equals", "/x/01", 1, "failed"),
        (b"{}", "json_pointer_equals", "/missing", True, "failed"),
    ],
)
def test_fixed_predicate_semantics(tmp_path, contents, op, pointer, expected, outcome):
    data, artifact, _, _, key, _, _ = setup_case(tmp_path)
    artifact.write_bytes(contents)
    row = dict(id="a", path="result.json", op=op, expected=expected)
    if pointer is not None:
        row["pointer"] = pointer
    raw = cc.encoded(dict(format=cc.POLICY_FORMAT, name="check", checks=[row]))
    env = cc.execute_checks(data, "task:1", raw, ["result.json=" + str(artifact)], key)
    assert json.loads(env["payload"])["results"][0]["outcome"] == outcome


@pytest.mark.parametrize(
    "bad",
    [
        "empty",
        "duplicate-id",
        "unknown-op",
        "code",
        "absolute",
        "traversal",
        "case-collision",
        "empty-needle",
        "invalid-digest",
        "bad-pointer",
        "object-expected",
        "unknown-field",
    ],
)
def test_invalid_policy_is_rejected_before_reading(tmp_path, monkeypatch, bad):
    data, artifact, policy, _, key, _, _ = setup_case(tmp_path)
    if bad == "empty":
        policy["checks"] = []
    elif bad == "duplicate-id":
        policy["checks"][1]["id"] = "bytes"
    elif bad == "unknown-op":
        policy["checks"][0]["op"] = "execute"
    elif bad == "code":
        policy["command"] = "touch forbidden"
    elif bad == "absolute":
        policy["checks"][0]["path"] = "/result.json"
    elif bad == "traversal":
        policy["checks"][0]["path"] = "../result.json"
    elif bad == "case-collision":
        policy["checks"][1]["path"] = "Result.json"
    elif bad == "empty-needle":
        policy["checks"][2]["expected"] = ""
    elif bad == "invalid-digest":
        policy["checks"][0]["expected"] = "a" * 64 + "\n"
    elif bad == "bad-pointer":
        policy["checks"][1]["pointer"] = "/x~3"
    elif bad == "object-expected":
        policy["checks"][1]["expected"] = {}
    else:
        policy["checks"][0]["authority"] = True
    monkeypatch.setattr(
        cc, "_read_selected", lambda _: pytest.fail("invalid policy authorized a read")
    )
    with pytest.raises(ValueError):
        cc.execute_checks(data, "task:1", cc.encoded(policy), ["result.json=" + str(artifact)], key)


@pytest.mark.parametrize(
    "change",
    [
        "missing-result",
        "result-order",
        "forged-pass",
        "different-artifact",
        "manifest",
        "true-authority",
        "extra-field",
        "empty-results",
    ],
)
def test_even_signed_malformed_results_are_rejected(tmp_path, change):
    data, _, _, _, key, profile, envelope = setup_case(tmp_path)
    payload = json.loads(envelope["payload"])
    if change == "missing-result":
        payload["results"].pop()
    elif change == "result-order":
        payload["results"].reverse()
    elif change == "forged-pass":
        payload["results"][0]["reason"] = "predicate_false"
    elif change == "different-artifact":
        payload["results"][0]["artifact_sha256"] = "a" * 64
    elif change == "manifest":
        payload["artifacts"]["entries"][0]["size_bytes"] += 1
    elif change == "true-authority":
        payload["task_success_implied"] = True
    elif change == "extra-field":
        payload["artifacts"]["entries"][0]["secret"] = "x"
    else:
        payload["results"] = []
    with pytest.raises(ValueError):
        cc.verify_receipt(signed(key, payload), profile, data, "task:1")


def test_exact_selection_coverage_no_files_inferred_from_policy(tmp_path):
    data, artifact, policy, raw, key, profile, env = setup_case(tmp_path)
    for selection in [
        [],
        ["other=" + str(artifact)],
        ["result.json=" + str(artifact), "extra=" + str(artifact)],
    ]:
        with pytest.raises(ValueError):
            cc.execute_checks(data, "task:1", raw, selection, key)


def test_no_program_execution(tmp_path):
    data, artifact, _, _, key, _, _ = setup_case(tmp_path)
    marker = tmp_path / "MUST_NOT_RUN"
    artifact.write_text(f'__import__("pathlib").Path({str(marker)!r}).touch()', encoding="utf-8")
    raw = cc.encoded(
        dict(
            format=cc.POLICY_FORMAT,
            name="inert code",
            checks=[dict(id="text", path="result.json", op="utf8_contains", expected="__import__")],
        )
    )
    env = cc.execute_checks(data, "task:1", raw, ["result.json=" + str(artifact)], key)
    assert json.loads(env["payload"])["results"][0]["outcome"] == "passed"
    assert not marker.exists()


def test_complete_cli_exit_semantics_and_no_overwrites(tmp_path, capsys):
    data, artifact, policy, raw, _, _, _ = setup_case(tmp_path)
    g = tmp_path / "graph.json"
    g.write_bytes(cc.encoded(data))
    p = tmp_path / "policy.json"
    p.write_bytes(raw)
    private = tmp_path / "key.pem"
    profile = tmp_path / "profile.json"
    output = tmp_path / "result-receipt.json"
    args = [
        "keygen",
        "--private-key",
        str(private),
        "--profile",
        str(profile),
        "--policy",
        str(p),
        "--label",
        "QA",
    ]
    assert cc.main(args) == 0
    assert cc.main(args) == 2
    base = [
        "run",
        "--graph",
        str(g),
        "--task-id",
        "task:1",
        "--policy",
        str(p),
        "--private-key",
        str(private),
        "--artifact",
        "result.json=" + str(artifact),
    ]
    assert cc.main(base + ["--output", str(output)]) == 0
    assert cc.main(base + ["--output", str(output)]) == 2
    assert (
        cc.main(
            [
                "verify",
                "--graph",
                str(g),
                "--task-id",
                "task:1",
                "--receipt",
                str(output),
                "--profile",
                str(profile),
            ]
        )
        == 0
    )
    artifact.write_bytes(b"{}")
    failed = tmp_path / "failed.json"
    assert cc.main(base + ["--output", str(failed)]) == 1 and failed.exists()
    assert (
        cc.main(
            [
                "verify",
                "--graph",
                str(g),
                "--task-id",
                "task:1",
                "--receipt",
                str(failed),
                "--profile",
                str(profile),
            ]
        )
        == 1
    )
    assert "BEGIN PRIVATE KEY" not in capsys.readouterr().out
    assert data == json.loads(g.read_bytes())
    if os.name == "posix":
        assert private.stat().st_mode & 0o077 == 0


def test_profile_is_not_embedded_self_authority_and_private_key_not_exported(tmp_path):
    _, _, _, _, key, profile, envelope = setup_case(tmp_path)
    raw = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    assert cc._b64(raw) not in json.dumps([profile, envelope])
    assert "public_key_b64" not in envelope and "profile" not in envelope


def test_real_node_webcrypto_verifies_python_signatures_and_policy_failures(tmp_path):
    data, artifact, policy, raw, key, profile, envelope = setup_case(tmp_path)
    original = json.loads(envelope["payload"])
    missing = copy.deepcopy(original)
    missing["results"].pop()
    tampered = copy.deepcopy(envelope)
    tampered["payload"] = envelope["payload"].replace("predicate_true", "predicate_false", 1)
    wrong_profile = {**profile, "policy_sha256": "f" * 64}
    cases = [
        dict(receipt=envelope, profile=profile, ok=True),
        dict(receipt=tampered, profile=profile, ok=False),
        dict(receipt=envelope, profile=wrong_profile, ok=False),
        dict(receipt=signed(key, missing), profile=profile, ok=False),
    ]
    script = (
        "globalThis.crypto=require('node:crypto').webcrypto;\n"
        + ARCHIVE_VERIFIER_JS
        + "\n"
        + CONTROLLED_CORE_JS
        + """
(async()=>{let input='';for await(const c of process.stdin)input+=c;const cases=JSON.parse(input),out=[];
for(const c of cases){try{const r=await __execweaveControlledCore.verify(c.receipt,c.profile);out.push({ok:true,state:r.state})}catch(e){out.push({ok:false,message:e.message})}}
console.log(JSON.stringify(out));})().catch(e=>{console.error(e);process.exit(2)});
"""
    )
    f = tmp_path / "verify.cjs"
    f.write_text(script)
    r = subprocess.run(
        ["node", str(f)], input=json.dumps(cases), text=True, capture_output=True, timeout=15
    )
    assert r.returncode == 0, r.stderr
    assert [v["ok"] for v in json.loads(r.stdout)] == [v["ok"] for v in cases]
    assert json.loads(r.stdout)[0]["state"] == "checks_passed"


@pytest.mark.parametrize(
    "raw", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":9007199254740993}', "[" * 40 + "0" + "]" * 40]
)
def test_strict_json_limits(raw):
    with pytest.raises(ValueError):
        cc.strict_json(raw)

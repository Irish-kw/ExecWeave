from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from execweave.agent_topology import CONVERSATION_COMPLETENESS
from execweave.evidence_availability import (
    AVAILABLE,
    COMPLETE_FROM_SURFACE,
    DECRYPTABILITY_UNKNOWN,
    EVIDENCE_INFERENCE,
    EVIDENCE_PROVIDER_DOCUMENTATION,
    FIELD_AVAILABILITY,
    NO_LOCAL_DECRYPTOR_OBSERVED,
    NOT_OBSERVED,
    OPAQUE_ENCRYPTED,
    PROVIDER_DOCUMENTED_UNAVAILABLE,
    FieldEvidence,
    readable_availability,
)
from execweave.provider_capability import (
    REQUIRED_CAPABILITY_INVENTORY,
    REQUIRED_FIELDS,
    inventory_entry,
    not_observed_matrix,
    probe_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
CODEX_FIXTURE = ROOT / "tests" / "fixtures" / "codex_multi_agent" / "rollout-main.jsonl"


def _row(rows, *, client: str, auth_mode: str, surface: str, field: str):
    matches = [
        row
        for row in rows
        if row.client == client
        and row.auth_mode == auth_mode
        and row.surface == surface
        and row.field == field
    ]
    assert len(matches) == 1
    return matches[0]


def _probe_codex(path: Path):
    return probe_artifact(
        inventory_entry("codex-cli"),
        path,
        auth_mode="subscription",
        surface="agent",
    )


def test_field_availability_is_separate_from_conversation_completeness() -> None:
    assert set(FIELD_AVAILABILITY).isdisjoint(CONVERSATION_COMPLETENESS)
    assert "provider_transcript" in CONVERSATION_COMPLETENESS
    assert OPAQUE_ENCRYPTED in FIELD_AVAILABILITY


def test_readable_availability_precedence_is_fixed() -> None:
    assert readable_availability(complete_from_surface=False) == AVAILABLE
    assert readable_availability(complete_from_surface=True) == COMPLETE_FROM_SURFACE


def test_documented_unavailable_requires_strong_evidence() -> None:
    with pytest.raises(ValueError, match="provider_documented_unavailable requires"):
        FieldEvidence(
            field="reasoning",
            availability=OPAQUE_ENCRYPTED,
            decryptability=PROVIDER_DOCUMENTED_UNAVAILABLE,
            evidence_strength=EVIDENCE_INFERENCE,
        )

    evidence = FieldEvidence(
        field="reasoning",
        availability=OPAQUE_ENCRYPTED,
        decryptability=PROVIDER_DOCUMENTED_UNAVAILABLE,
        evidence_strength=EVIDENCE_PROVIDER_DOCUMENTATION,
    )
    assert evidence.decryptability == PROVIDER_DOCUMENTED_UNAVAILABLE


def test_required_inventory_has_the_five_release_blocking_clients() -> None:
    assert {entry.client for entry in REQUIRED_CAPABILITY_INVENTORY} == {
        "codex-cli",
        "claude-code",
        "cursor-agent",
        "opencode",
        "ollama",
    }
    assert all(entry.tier == "A" for entry in REQUIRED_CAPABILITY_INVENTORY)
    assert all(entry.required_fields == REQUIRED_FIELDS for entry in REQUIRED_CAPABILITY_INVENTORY)


def test_no_data_matrix_keeps_every_required_row_explicit() -> None:
    rows = not_observed_matrix()
    required = [row for row in rows if row.tier == "A"]
    expected = sum(
        len(entry.auth_modes) * len(entry.surfaces) * len(entry.required_fields)
        for entry in REQUIRED_CAPABILITY_INVENTORY
    )
    assert len(required) == expected
    assert all(row.availability == NOT_OBSERVED for row in required)
    assert all(row.notes for row in required)
    assert all(row.decryptability == DECRYPTABILITY_UNKNOWN for row in required)


def test_codex_encrypted_reasoning_never_claims_server_side_key() -> None:
    rows = probe_artifact(
        inventory_entry("codex-cli"),
        CODEX_FIXTURE,
        auth_mode="subscription",
        surface="agent",
        codex_no_local_decryptor_observed=True,
    )
    reasoning = _row(
        rows,
        client="codex-cli",
        auth_mode="subscription",
        surface="agent",
        field="reasoning",
    )
    assert reasoning.availability == OPAQUE_ENCRYPTED
    assert reasoning.decryptability == NO_LOCAL_DECRYPTOR_OBSERVED
    assert reasoning.client_version == "0.150.1"
    assert "server" not in (reasoning.notes or "").lower()


def test_developer_role_is_not_upgraded_to_system_evidence(tmp_path: Path) -> None:
    artifact = tmp_path / "developer.json"
    artifact.write_text(
        json.dumps({"role": "developer", "content": "provider developer instruction"}),
        encoding="utf-8",
    )
    rows = _probe_codex(artifact)
    system = next(row for row in rows if row.field == "system")
    messages = next(row for row in rows if row.field == "messages")
    assert system.availability == NOT_OBSERVED
    assert messages.availability == AVAILABLE


def test_nested_encrypted_reasoning_is_not_upgraded_to_available(tmp_path: Path) -> None:
    artifact = tmp_path / "reasoning.json"
    artifact.write_text(
        json.dumps({"reasoning": {"encrypted_content": "gAAAAA-test-ciphertext"}}),
        encoding="utf-8",
    )
    reasoning = next(row for row in _probe_codex(artifact) if row.field == "reasoning")
    assert reasoning.availability == OPAQUE_ENCRYPTED


def test_unscoped_arguments_key_is_not_claimed_as_tool_arguments(tmp_path: Path) -> None:
    artifact = tmp_path / "arguments.json"
    artifact.write_text(json.dumps({"arguments": {"ordinary": "metadata"}}), encoding="utf-8")
    tool_arguments = next(row for row in _probe_codex(artifact) if row.field == "tool_arguments")
    assert tool_arguments.availability == NOT_OBSERVED


def test_evidence_source_does_not_expose_supplied_absolute_path(tmp_path: Path) -> None:
    private_dir = tmp_path / "private-user-path"
    private_dir.mkdir()
    artifact = private_dir / "artifact.json"
    artifact.write_text(json.dumps({"prompt": "hello"}), encoding="utf-8")
    prompt = next(row for row in _probe_codex(artifact) if row.field == "prompt")
    assert prompt.availability == AVAILABLE
    assert "artifact.json" in prompt.evidence_source
    assert str(tmp_path) not in prompt.evidence_source


def test_probe_cli_emits_full_matrix_and_codex_observation() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "probe_provider_capability.py"),
            "--artifact",
            f"codex-cli:subscription={CODEX_FIXTURE}",
        ],
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    rows = payload["rows"]
    assert rows
    reasoning = [
        row
        for row in rows
        if row["client"] == "codex-cli"
        and row["auth_mode"] == "subscription"
        and row["surface"] == "agent"
        and row["field"] == "reasoning"
    ]
    assert len(reasoning) == 1
    assert reasoning[0]["availability"] == OPAQUE_ENCRYPTED
    assert reasoning[0]["decryptability"] == NO_LOCAL_DECRYPTOR_OBSERVED
    assert payload["probe"]["network_used"] is False

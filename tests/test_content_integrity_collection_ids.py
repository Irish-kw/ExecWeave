"""Collect the real byte-integrity cases without putting their bytes in test IDs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from execweave import content_integrity

_TARGET = "test_all_captured_bytes_and_duplicate_refs_are_verified_once"
_COLLECT = r'''
import hashlib
import json
from pathlib import Path
import sys

import pytest

class Inventory:
    def pytest_collection_finish(self, session):
        rows = []
        for item in session.items:
            row = {"nodeid": item.nodeid, "function": item.originalname}
            parameters = getattr(item, "callspec", None)
            if parameters is not None and "payload" in parameters.params:
                value = parameters.params["payload"]
                row.update(payload_bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
            rows.append(row)
        Path(sys.argv[1]).write_text(json.dumps(rows), encoding="utf-8")

raise SystemExit(pytest.main(
    ["--collect-only", "-q", "tests/test_content_integrity.py"], plugins=[Inventory()]))
'''


@pytest.fixture(scope="module")
def collected_integrity_cases(tmp_path_factory):
    output = tmp_path_factory.mktemp("integrity-collection") / "cases.json"
    result = subprocess.run(
        [sys.executable, "-c", _COLLECT, str(output)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-2000:]
    return json.loads(output.read_text(encoding="utf-8"))


def test_byte_integrity_collection_uses_short_unique_case_ids(collected_integrity_cases):
    rows = [row for row in collected_integrity_cases if row["function"] == _TARGET]
    assert len(rows) == 7
    identifiers = [row["nodeid"] for row in rows]
    assert len(set(identifiers)) == len(identifiers)
    # A conservative display-name budget; the native failure was above 1 MiB.
    assert max(map(len, identifiers)) <= 200
    assert all(len((identifier + " (teardown)").encode("utf-16-le")) // 2 < 32767
               for identifier in identifiers)
    assert [identifier.rsplit("[", 1)[1].removesuffix("]") for identifier in identifiers] == [
        "empty", "null-literal", "false-literal", "zero-literal", "utf8-text",
        "binary", "cross-chunk-boundary",
    ]


def test_collection_retains_the_original_byte_payloads_and_order(collected_integrity_cases):
    rows = [row for row in collected_integrity_cases if row["function"] == _TARGET]
    expected = [b"", b"null", b"false", b"0", "中文".encode(), b"\x00\xff\xfe",
                b"x" * (content_integrity.CHUNK + 17)]
    assert [(row["payload_bytes"], row["sha256"]) for row in rows] == [
        (len(value), hashlib.sha256(value).hexdigest()) for value in expected
    ]
    assert rows[-1]["payload_bytes"] > content_integrity.CHUNK


def test_completed_historical_diagnostic_requires_explicit_dispatch():
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/windows-suite-diagnostic.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert set(workflow["on"]) == {"workflow_dispatch"}
    # Retiring automatic historical replay must not replace normal head testing.
    acceptance = yaml.load(
        (root / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert "pull_request" in acceptance["on"]

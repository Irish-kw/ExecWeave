"""Operator-selected artifact versions associated with an external report.

Only explicit NAME=FILE arguments authorize reads. Names inside imported reports
are never filesystem capabilities. This is neither an execution attestation nor
an atomic snapshot of a directory changing concurrently with these reads.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any

from .content_integrity import ArchiveReadError, _path_descriptor_stat

FORMAT = "execweave.selected-artifact-versions.v1"
RECEIPT_FORMAT = "execweave.external-task-report.v2"
MAX_FILES = 100
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def artifact_name(value: Any) -> str:
    """Require an unambiguous portable relative name, never normalize silently."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError("artifact name must contain 1 to 512 characters")
    if (
        unicodedata.normalize("NFC", value) != value
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
        or any(c in value for c in '\\:*?"<>|')
    ):
        raise ValueError("artifact name is not portable NFC text")
    if any(
        not p or p in (".", "..") or p.endswith((" ", ".")) or _RESERVED.match(p)
        for p in value.split("/")
    ):
        raise ValueError("artifact name must be a portable relative path")
    return value


def manifest_bytes(entries: list[dict[str, Any]]) -> bytes:
    """Stable array encoding shared with the browser; no object key ordering."""
    return json.dumps(
        [[r["path"], r["size_bytes"], r["sha256"]] for r in entries],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("format") != FORMAT:
        raise ValueError("unsupported artifact manifest")
    entries = value.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
        raise ValueError("artifact manifest requires 1 to 100 explicit files")
    seen: set[str] = set()
    clean = []
    total = 0
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("invalid artifact entry")
        name = artifact_name(item.get("path"))
        folded = name.lower()
        if folded in seen:
            raise ValueError("duplicate or case-colliding artifact name")
        seen.add(folded)
        size, digest = item.get("size_bytes"), item.get("sha256")
        if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
            raise ValueError("artifact file exceeds 8 MiB or has an invalid size")
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            raise ValueError("invalid artifact digest")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("artifact inventory exceeds 64 MiB")
        clean.append({"path": name, "size_bytes": size, "sha256": digest})
    expected = hashlib.sha256(manifest_bytes(clean)).hexdigest()
    if value.get("manifest_sha256") != expected:
        raise ValueError("artifact manifest hash mismatch")
    return {"format": FORMAT, "entries": clean, "manifest_sha256": expected}


def _signature(s: os.stat_result) -> tuple[int, ...]:
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _selected_snapshot(path: str) -> os.stat_result:
    """Use the archive reader's metadata-only handle and link checks."""
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("selected artifact must be a regular file without links")
    try:
        value = _path_descriptor_stat(Path(path))
    except ArchiveReadError as exc:
        raise ValueError("selected artifact must be a regular file without links") from exc
    if value.st_size > MAX_FILE_BYTES:
        raise ValueError("selected artifact must be at most 8 MiB")
    return value


def _read_selected(path: str) -> bytes:
    # Explicit CLI selections authorize reads, never paths inside a report.
    # Compare open-handle metadata on every boundary. Windows path-stat and
    # descriptor-stat timestamps need not agree even when the bytes are stable.
    before = _selected_snapshot(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or _signature(opened) != _signature(before):
            raise ValueError("selected artifact changed before reading")
        payload = handle.read(MAX_FILE_BYTES + 1)
        after = os.fstat(handle.fileno())
        # Keep the data handle open while reopening the selected path. Identity,
        # size and both timestamps remain exact; no rounding or ignored fields.
        if (
            len(payload) != before.st_size
            or _signature(before) != _signature(after)
            or _signature(after) != _signature(_selected_snapshot(path))
        ):
            raise ValueError("selected artifact changed while reading")
    return payload


def bind_artifacts(receipt: dict[str, Any], selections: list[str]) -> dict[str, Any]:
    """Associate selected bytes without claiming the report tested those bytes."""
    if receipt.get("format") != "execweave.external-task-report.v1":
        raise ValueError("expected an unbound v1 external report receipt")
    if not 1 <= len(selections) <= MAX_FILES:
        raise ValueError("select 1 to 100 artifacts")
    parsed = []
    seen = set()
    for selection in selections:
        if not isinstance(selection, str) or "=" not in selection:
            raise ValueError("use --artifact RELATIVE_NAME=LOCAL_FILE")
        name, path = selection.split("=", 1)
        artifact_name(name)
        if not path or name.lower() in seen:
            raise ValueError("empty artifact path or duplicate/case-colliding name")
        seen.add(name.lower())
        parsed.append((name, path))
    # Validate the whole selection first. Never infer further files from XML.
    entries = []
    total = 0
    for name, path in sorted(parsed, key=lambda pair: pair[0].encode("utf-8")):
        payload = _read_selected(str(Path(path)))
        total += len(payload)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("selected artifacts exceed 64 MiB")
        entries.append(
            {
                "path": name,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "format": FORMAT,
        "entries": entries,
        "manifest_sha256": hashlib.sha256(manifest_bytes(entries)).hexdigest(),
    }
    validate_manifest(manifest)
    result = copy.deepcopy(receipt)
    result["format"] = RECEIPT_FORMAT
    result["artifacts"] = manifest
    return result

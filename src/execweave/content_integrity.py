"""Verify declared archive references without inspecting provider payload bodies.

The scope is the exported graph's observed_content nodes and conversation-index
entries, not provider recall or an adversary-resistant log. Payload JSON is a leaf:
strings/dictionaries supplied by agents never become additional filesystem paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

CONTENT_PATH = re.compile(r"content/sha256/([0-9a-f]{64})\.(?:json|txt|bin)")
INDEXES = {"graph.json": "nodes", "conversations.json": "entries"}
EXPORTS = (*INDEXES, "viewer.html")
CHUNK = 1024 * 1024


class ArchiveReadError(Exception):
    """A bounded, content-free archive diagnostic."""


def _signature(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _reject_link(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ArchiveReadError("unsafe_path")  # Includes Windows reparse points.


def _path_descriptor_stat(path: Path) -> os.stat_result:
    """Compare two open-file snapshots, not Windows stat/fstat timestamps.

    Path-based stat and descriptor-based fstat need not expose the same ctime
    semantics on supported Windows/Python versions. Reopening the recorded path
    preserves the identity/size/time comparison without rounding timestamps or
    ignoring changes. This handle is metadata-only and never reads payload bytes.
    """
    _reject_link(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        value = os.fstat(descriptor)
        if not stat.S_ISREG(value.st_mode):
            raise ArchiveReadError("not_regular_file")
        return value
    finally:
        os.close(descriptor)


@contextmanager
def _open_regular(root: Path, relative: str) -> Iterator[Any]:
    if relative not in EXPORTS and CONTENT_PATH.fullmatch(relative) is None:
        raise ArchiveReadError("invalid_reference")
    opened: list[int] = []
    try:
        parts = relative.split("/")
        # Pin every directory on POSIX. O_NOFOLLOW prevents symlink traversal even
        # when a directory entry is replaced between validation and opening.
        if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            parent = os.open(root, flags)
            opened.append(parent)
            for part in parts[:-1]:
                parent = os.open(part, flags, dir_fd=parent)
                opened.append(parent)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        else:
            path = root
            _reject_link(path)
            for part in parts:
                path = path / part
                _reject_link(path)
            # Windows has no Python dir_fd/O_NOFOLLOW equivalent. Reject reparse
            # points before and after reading; do not claim tamper-proof storage.
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ArchiveReadError("not_regular_file")
            yield handle
            after = os.fstat(handle.fileno())
            path = root
            _reject_link(path)
            for part in parts:
                path = path / part
                _reject_link(path)
            if _signature(before) != _signature(after) or _signature(after) != _signature(_path_descriptor_stat(path)):
                raise ArchiveReadError("changed_during_read")
    except FileNotFoundError as exc:
        raise ArchiveReadError("missing_file") from exc
    except OSError as exc:
        # Do not write raw exception messages: paths may contain private data.
        raise ArchiveReadError("unreadable_or_unsafe_path") from exc
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _read(root: Path, relative: str, limit: int, *, collect: bool = False) -> tuple[dict[str, Any], bytes]:
    chunks: list[bytes] = []
    digest = hashlib.sha256()
    size = 0
    with _open_regular(root, relative) as handle:
        if os.fstat(handle.fileno()).st_size > limit:
            raise ArchiveReadError("verification_limit")
        while True:
            chunk = handle.read(min(CHUNK, max(1, limit - size + 1)))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ArchiveReadError("verification_limit")
            digest.update(chunk)
            if collect:
                chunks.append(chunk)
    return {"sha256": digest.hexdigest(), "size_bytes": size}, b"".join(chunks)


def hash_export(root: Path, name: str) -> dict[str, Any]:
    """Hash only a named, regular primary export, with bounded reads."""
    if name not in EXPORTS:
        raise ArchiveReadError("invalid_export")
    return _read(root, name, 1024 * 1024 * 1024)[0]


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("non-finite JSON value")


def audit_content_references(
    run_root: str | Path,
    *,
    max_index_bytes: int = 64 * 1024 * 1024,
    max_content_bytes: int = 1024 * 1024 * 1024,
    max_references: int = 100_000,
) -> dict[str, Any]:
    """Verify registered references; limits and unknown sources never pass silently.

    Missing size metadata on legacy references is accepted but not invented. Source
    completeness is orthogonal: an intact blob of partial provider content can pass
    byte-integrity verification without implying complete provider observation.
    """
    for limit in (max_index_bytes, max_content_bytes, max_references):
        if type(limit) is not int or limit < 0:
            raise ValueError("limits must be nonnegative integers")
    root = Path(run_root).expanduser().absolute()
    report: dict[str, Any] = {
        "schema_version": "0.1",
        "scope": "declared_graph_and_conversation_content",
        "state": "incomplete",
        "reference_count": 0,
        "reference_count_truncated": False,
        "unique_file_count": 0,
        "verified_file_count": 0,
        "error_count": 0,
        "errors": [],
        "errors_truncated": False,
        "index_files": {},
        "verified_files": {},
        "limits": {"index_bytes": max_index_bytes, "content_bytes": max_content_bytes,
                   "references": max_references},
    }

    def fail(code: str, location: str) -> None:
        report["error_count"] += 1
        if len(report["errors"]) < 100:
            report["errors"].append({"code": code, "location": location})
        else:
            report["errors_truncated"] = True

    # None is an unknown legacy size, not zero. A duplicate declaration must agree
    # with every known size; a later valid reference cannot erase a conflict.
    references: dict[str, tuple[str, int | None, str]] = {}
    conflicted: set[str] = set()
    limit_hit = False

    def register(value: Any, location: str) -> None:
        nonlocal limit_hit
        if limit_hit:
            return
        report["reference_count"] += 1
        if report["reference_count"] > max_references:
            limit_hit = True
            report["reference_count_truncated"] = True
            fail("reference_limit", location)
            return
        if not isinstance(value, dict):
            fail("invalid_reference", location)
            return
        path, digest, size = value.get("path"), value.get("sha256"), value.get("size_bytes")
        match = CONTENT_PATH.fullmatch(path) if isinstance(path, str) else None
        if (match is None or match[1] != digest or
                ("size_bytes" in value and (type(size) is not int or size < 0))):
            fail("invalid_reference", location)
            return
        previous = references.get(path)
        if previous and previous[1] is not None and size is not None and previous[1] != size:
            conflicted.add(path)
            fail("conflicting_reference", location)
            return
        if previous is None or previous[1] is None:
            references[path] = (digest, size, location)

    sessions: set[str] = set()
    for name, key in INDEXES.items():
        try:
            fingerprint, raw = _read(root, name, max_index_bytes, collect=True)
            report["index_files"][name] = fingerprint
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys, parse_constant=_constant)
            if not isinstance(data, dict) or not isinstance(data.get(key), list):
                raise ValueError("invalid index shape")
        except ArchiveReadError as exc:
            fail(str(exc), name)
            continue
        except (ValueError, RecursionError):
            fail("invalid_index", name)
            continue
        session = data.get("session_id")
        if isinstance(session, str) and session:
            sessions.add(session)
        for index, item in enumerate(data[key]):
            location = f"{name}/{key}/{index}"
            if not isinstance(item, dict):
                fail("invalid_index_entry", location)
                continue
            if key == "nodes":
                if item.get("type") == "observed_content":
                    register(item.get("attributes"), location)
            else:
                # Conversation entries are reference records. Do not walk preview
                # messages, request objects, or arbitrary nested provider JSON.
                if "path" in item or "sha256" in item:
                    register(item, location)
                else:
                    fail("invalid_reference", location)
        # A projected graph may retain hidden raw nodes under expansion.clusters.
        if key == "nodes" and isinstance(data.get("expansion"), dict):
            clusters = data["expansion"].get("clusters", {})
            if not isinstance(clusters, dict):
                fail("invalid_expansion", f"{name}/expansion/clusters")
                continue
            for cluster_index, cluster in enumerate(clusters.values()):
                location = f"{name}/expansion/clusters/{cluster_index}"
                if not isinstance(cluster, dict) or not isinstance(cluster.get("nodes"), list):
                    fail("invalid_expansion", location)
                    continue
                for index, item in enumerate(cluster["nodes"]):
                    if isinstance(item, dict) and item.get("type") == "observed_content":
                        register(item.get("attributes"), f"{location}/nodes/{index}")
    if len(sessions) > 1:
        fail("index_session_mismatch", "graph.json/conversations.json")
    report["unique_file_count"] = len(references)
    budget = max_content_bytes
    for path, (digest, size, location) in references.items():
        if path in conflicted:
            continue
        try:
            fingerprint, _ = _read(root, path, budget)
            budget -= fingerprint["size_bytes"]
            if fingerprint["sha256"] != digest:
                raise ArchiveReadError("hash_mismatch")
            if size is not None and fingerprint["size_bytes"] != size:
                raise ArchiveReadError("size_mismatch")
            report["verified_files"][path] = fingerprint
        except ArchiveReadError as exc:
            fail(str(exc), location)
    report["verified_file_count"] = len(report["verified_files"])
    report["completed_read_bytes"] = max_content_bytes - budget
    if report["error_count"] == 0:
        report["state"] = "complete"
    return report

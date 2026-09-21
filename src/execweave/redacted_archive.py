"""Create and verify content-aware redacted derivative run archives.

The source archive is never modified. A derivative receives new content hashes,
new primary-export hashes and an explicit lineage manifest. The policy is hashed
but not copied into the derivative because literal redaction terms can themselves
be sensitive. This is a sharing derivative, not an anonymity guarantee or a
cryptographically authenticated audit log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from .content_integrity import (
    ArchiveReadError,
    CONTENT_PATH,
    _read as _integrity_read,
    audit_content_references,
    hash_export,
)
from .content_store import FullFidelityContentStore
from .dashboard_shell import render_static_dashboard_html
from .delivery_status import summarize_finalization
from .finalization import REQUIRED_EXPORTS, record_finalization

POLICY_FORMAT = "execweave.redaction-policy.v1"
LINEAGE_FORMAT = "execweave.redacted-lineage.v1"
DERIVATIVE_FORMAT = "execweave.redacted-archive.v1"
MAX_POLICY_BYTES = 128 * 1024
MAX_FINALIZATION_BYTES = 16 * 1024 * 1024
MAX_LINEAGE_BYTES = 32 * 1024 * 1024
MAX_INDEX_BYTES = 64 * 1024 * 1024
MAX_CONTENT_BYTES = 1024 * 1024 * 1024
MAX_DERIVATIVE_FILE_BYTES = 64 * 1024 * 1024
MAX_DERIVATIVE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_RULES = 100
MAX_STRING_BYTES = 4096
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_RESERVED_REDACT_KEYS = frozenset(
    {
        "id",
        "type",
        "relation",
        "event_type",
        "graph_schema_version",
        "schema_version",
        "sha256",
        "path",
        "session_id",
        "source_path",
        "content_kind",
        "media_type",
        "representation",
        "provider",
        "backend",
        "evidence_source",
        "attribution",
        "observed_field",
    }
)
_CONTROL_STRING_KEYS = frozenset(
    {
        "type",
        "relation",
        "event_type",
        "graph_schema_version",
        "schema_version",
        "content_kind",
        "media_type",
        "representation",
        "provider",
        "backend",
        "evidence_source",
        "attribution",
        "observed_field",
        "sha256",
        "path",
    }
)


class RedactedArchiveError(Exception):
    """Bounded derivative-archive diagnostic without private file paths."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _bad_constant(_value: str) -> None:
    raise ValueError("nonfinite JSON value")


def _strict_json(raw: bytes, limit: int) -> Any:
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise ValueError("JSON exceeds its byte limit")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_bad_constant)


def _canonical(value: Any, *, newline: bool = True) -> bytes:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _fingerprint(raw: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def _validate_fingerprint(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"sha256", "size_bytes"}
        and isinstance(value.get("sha256"), str)
        and _HASH.fullmatch(value["sha256"]) is not None
        and type(value.get("size_bytes")) is int
        and value["size_bytes"] >= 0
    )


def _read_named_regular(root: Path, name: str, limit: int) -> bytes:
    """Read one fixed top-level metadata file without following links/reparse points."""
    if name not in {"finalization.json", "lineage.json"}:
        raise RedactedArchiveError("invalid_metadata_file")
    path = root / name
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RedactedArchiveError("unsafe_metadata_file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise RedactedArchiveError("metadata_file_limit")
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = os.read(fd, min(1024 * 1024, max(1, limit - size + 1)))
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise RedactedArchiveError("metadata_file_limit")
                chunks.append(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        final = path.lstat()
        if stat.S_ISLNK(final.st_mode) or getattr(final, "st_file_attributes", 0) & 0x400:
            raise RedactedArchiveError("unsafe_metadata_file")

        def signature(value):
            return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)

        if signature(before) != signature(after) or signature(after) != signature(final):
            raise RedactedArchiveError("metadata_changed_during_read")
        return b"".join(chunks)
    except FileNotFoundError as exc:
        raise RedactedArchiveError("missing_metadata_file") from exc
    except RedactedArchiveError:
        raise
    except OSError as exc:
        raise RedactedArchiveError("unreadable_metadata_file") from exc


def _read_policy(path: Path) -> bytes:
    """Bound a policy before materializing it in memory."""
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RedactedArchiveError("unsafe_policy")
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_POLICY_BYTES:
            raise RedactedArchiveError("policy_limit")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = os.read(fd, min(64 * 1024, max(1, MAX_POLICY_BYTES - size + 1)))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_POLICY_BYTES:
                    raise RedactedArchiveError("policy_limit")
                chunks.append(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise RedactedArchiveError("policy_changed_during_read")
        return b"".join(chunks)
    except RedactedArchiveError:
        raise
    except (FileNotFoundError, OSError) as exc:
        raise RedactedArchiveError("unreadable_policy") from exc


def _pointer(value: str) -> list[str]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_STRING_BYTES:
        raise ValueError("invalid JSON pointer")
    if value and not value.startswith("/"):
        raise ValueError("invalid JSON pointer")
    if re.search(r"~(?![01])", value):
        raise ValueError("invalid JSON pointer escape")
    parts = [] if not value else value[1:].split("/")
    if len(parts) > 32:
        raise ValueError("JSON pointer exceeds 32 steps")
    return [p.replace("~1", "/").replace("~0", "~") for p in parts]


def policy_document(raw: bytes) -> tuple[dict[str, Any], bytes, str]:
    try:
        value = _strict_json(raw, MAX_POLICY_BYTES)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RedactedArchiveError("invalid_policy") from exc
    fields = {"format", "name", "replacement", "literals", "json_pointers", "redact_keys", "binary"}
    if not isinstance(value, dict) or set(value) != fields or value.get("format") != POLICY_FORMAT:
        raise RedactedArchiveError("invalid_policy")
    for field in ("name", "replacement"):
        item = value[field]
        if not isinstance(item, str) or not item or len(item.encode("utf-8")) > MAX_STRING_BYTES:
            raise RedactedArchiveError("invalid_policy")
    for field in ("literals", "json_pointers", "redact_keys"):
        if not isinstance(value[field], list) or len(value[field]) > MAX_RULES:
            raise RedactedArchiveError("invalid_policy")
        if len(set(value[field])) != len(value[field]):
            raise RedactedArchiveError("invalid_policy")
    for literal in value["literals"]:
        if not isinstance(literal, str) or not literal or len(literal.encode("utf-8")) > 1024:
            raise RedactedArchiveError("invalid_policy")
    try:
        for pointer in value["json_pointers"]:
            _pointer(pointer)
    except ValueError as exc:
        raise RedactedArchiveError("invalid_policy") from exc
    for key in value["redact_keys"]:
        if (
            not isinstance(key, str)
            or _KEY.fullmatch(key) is None
            or key.lower() in _RESERVED_REDACT_KEYS
        ):
            raise RedactedArchiveError("invalid_policy")
    if value["binary"] != "drop":
        raise RedactedArchiveError("invalid_policy")
    canonical = _canonical(value, newline=False)
    return value, canonical, hashlib.sha256(canonical).hexdigest()


def _replace_literals(text: str, policy: dict[str, Any]) -> tuple[str, int]:
    count = 0
    for literal in policy["literals"]:
        occurrences = text.count(literal)
        if occurrences:
            text = text.replace(literal, policy["replacement"])
            count += occurrences
    return text, count


def _set_pointer(document: Any, pointer: str, replacement: str) -> bool:
    parts = _pointer(pointer)
    if not parts:
        return False  # Replacing the entire document would destroy its type/shape.
    current = document
    for part in parts[:-1]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    leaf = parts[-1]
    if isinstance(current, dict) and leaf in current:
        current[leaf] = replacement
        return True
    if isinstance(current, list) and leaf.isdigit() and int(leaf) < len(current):
        current[int(leaf)] = replacement
        return True
    return False


def _redact_json_value(
    value: Any, policy: dict[str, Any], *, key: str | None = None
) -> tuple[Any, int]:
    if key is not None and key.lower() in {k.lower() for k in policy["redact_keys"]}:
        return policy["replacement"], 1
    if isinstance(value, str):
        return _replace_literals(value, policy)
    if isinstance(value, list):
        result, count = [], 0
        for item in value:
            transformed, used = _redact_json_value(item, policy)
            result.append(transformed)
            count += used
        return result, count
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        count = 0
        for child_key, child in value.items():
            transformed, used = _redact_json_value(child, policy, key=child_key)
            result[child_key] = transformed
            count += used
        return result, count
    return value, 0


def _redact_content(
    raw: bytes, suffix: str, media_type: str, policy: dict[str, Any]
) -> tuple[bytes, str, list[str]]:
    actions: list[str] = []
    if suffix == ".json" or media_type.lower().startswith("application/json"):
        try:
            document = _strict_json(raw, MAX_CONTENT_BYTES)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise RedactedArchiveError("invalid_json_content") from exc
        document, count = _redact_json_value(document, policy)
        if count:
            actions.append(f"literal_or_key_replacements:{count}")
        pointer_count = 0
        for pointer in policy["json_pointers"]:
            if _set_pointer(document, pointer, policy["replacement"]):
                pointer_count += 1
        if pointer_count:
            actions.append(f"json_pointer_replacements:{pointer_count}")
        return (
            _canonical(document, newline=False),
            "application/json",
            actions or ["canonicalized_json"],
        )
    if suffix == ".txt" or media_type.lower().startswith("text/"):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RedactedArchiveError("invalid_utf8_text_content") from exc
        text, count = _replace_literals(text, policy)
        if count:
            actions.append(f"literal_replacements:{count}")
        return (
            text.encode("utf-8"),
            media_type or "text/plain; charset=utf-8",
            actions or ["text_unchanged"],
        )
    # V1 never copies opaque binary into a sharing derivative.
    return b"", "application/octet-stream", ["binary_dropped"]


def _source_reference_map(
    graph: dict[str, Any], conversations: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}

    def register(value: Any) -> None:
        if not isinstance(value, dict):
            return
        path, digest = value.get("path"), value.get("sha256")
        if isinstance(path, str) and isinstance(digest, str) and CONTENT_PATH.fullmatch(path):
            refs.setdefault(path, value)

    def nodes(items: Any) -> None:
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("type") == "observed_content":
                    register(item.get("attributes"))

    nodes(graph.get("nodes"))
    expansion = graph.get("expansion")
    if isinstance(expansion, dict) and isinstance(expansion.get("clusters"), dict):
        for cluster in expansion["clusters"].values():
            if isinstance(cluster, dict):
                nodes(cluster.get("nodes"))
    for entry in (
        conversations.get("entries", []) if isinstance(conversations.get("entries"), list) else []
    ):
        register(entry)
    return refs


def _rewrite_index(
    value: Any,
    *,
    policy: dict[str, Any],
    refs: dict[str, dict[str, Any]],
    id_map: dict[str, str],
    parent_key: str | None = None,
) -> Any:
    if isinstance(value, list):
        return [
            _rewrite_index(item, policy=policy, refs=refs, id_map=id_map, parent_key=parent_key)
            for item in value
        ]
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and value["path"] in refs and value.get("sha256"):
            replacement = dict(value)
            derived = refs[value["path"]]
            replacement.update(derived)
            replacement["redacted_derivative"] = True
            replacement["complete_from_source"] = value.get("complete_from_source", True)
            return replacement
        result: dict[str, Any] = {}
        redact_keys = {k.lower() for k in policy["redact_keys"]}
        for key, child in value.items():
            if key == "source_path":
                result[key] = None
            elif key == "session_id" and isinstance(child, str):
                result[key] = id_map.get(child, child)
            elif key == "id" and isinstance(child, str):
                result[key] = id_map.get(child, child)
            elif key in ("source", "target") and isinstance(child, str):
                result[key] = id_map.get(child, child)
            elif key.lower() in redact_keys and key.lower() not in _RESERVED_REDACT_KEYS:
                result[key] = policy["replacement"]
            else:
                result[key] = _rewrite_index(
                    child, policy=policy, refs=refs, id_map=id_map, parent_key=key
                )
        return result
    if isinstance(value, str):
        if value in id_map:
            return id_map[value]
        if parent_key in _CONTROL_STRING_KEYS:
            return value
        return _replace_literals(value, policy)[0]
    return value


def _identity_map(
    graph: dict[str, Any],
    conversations: dict[str, Any],
    policy: dict[str, Any],
    derived_session: str,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    source_session = graph.get("session_id")
    if isinstance(source_session, str) and source_session:
        mapping[source_session] = derived_session
    identities: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            if key in {"id", "source", "target"} and isinstance(child, str) and child:
                identities.add(child)
            else:
                collect(child)

    collect(graph)
    collect(conversations)
    transformed: dict[str, str] = {}
    for identity in sorted(identities):
        new = _replace_literals(identity, policy)[0]
        transformed[identity] = new
    reverse: dict[str, str] = {}
    for old, new in transformed.items():
        previous = reverse.get(new)
        if previous is not None and previous != old:
            raise RedactedArchiveError("identity_collision")
        reverse[new] = old
        if old != new:
            mapping[old] = new
    return mapping


def _load_source(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes, dict[str, Any]]:
    integrity = audit_content_references(
        root, max_index_bytes=MAX_INDEX_BYTES, max_content_bytes=MAX_CONTENT_BYTES
    )
    if integrity.get("state") != "complete":
        raise RedactedArchiveError("source_archive_incomplete")
    final_raw = _read_named_regular(root, "finalization.json", MAX_FINALIZATION_BYTES)
    try:
        report = _strict_json(final_raw, MAX_FINALIZATION_BYTES)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RedactedArchiveError("invalid_source_finalization") from exc
    if summarize_finalization(report).get("state") != "complete":
        raise RedactedArchiveError("source_finalization_incomplete")
    for name in REQUIRED_EXPORTS:
        if hash_export(root, name) != report.get("artifacts", {}).get(name):
            raise RedactedArchiveError("source_primary_changed")
    try:
        graph_fp, graph_raw = _integrity_read(root, "graph.json", MAX_INDEX_BYTES, collect=True)
        conversations_fp, conversations_raw = _integrity_read(
            root, "conversations.json", MAX_INDEX_BYTES, collect=True
        )
        if graph_fp != report.get("artifacts", {}).get(
            "graph.json"
        ) or conversations_fp != report.get("artifacts", {}).get("conversations.json"):
            raise RedactedArchiveError("source_primary_changed")
        graph = _strict_json(graph_raw, MAX_INDEX_BYTES)
        conversations = _strict_json(conversations_raw, MAX_INDEX_BYTES)
    except RedactedArchiveError:
        raise
    except (ArchiveReadError, ValueError, UnicodeError, RecursionError) as exc:
        raise RedactedArchiveError("invalid_source_index") from exc
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise RedactedArchiveError("invalid_source_index")
    if not isinstance(conversations, dict) or not isinstance(conversations.get("entries"), list):
        raise RedactedArchiveError("invalid_source_index")
    return graph, conversations, report, final_raw, integrity


def _write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".execweave-redacted-", dir=path.parent)
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def create_redacted_archive(
    source: str | Path, destination: str | Path, policy_path: str | Path
) -> dict[str, Any]:
    source_root = Path(source).expanduser().absolute()
    destination = Path(destination).expanduser().absolute()
    if destination.exists():
        raise RedactedArchiveError("destination_exists")
    policy_raw = _read_policy(Path(policy_path).expanduser().absolute())
    policy, _policy_canonical, policy_sha = policy_document(policy_raw)
    graph, conversations, source_report, source_final_raw, source_integrity = _load_source(
        source_root
    )
    source_primary = {name: hash_export(source_root, name) for name in REQUIRED_EXPORTS}
    source_graph_sha = source_primary["graph.json"]["sha256"]
    derived_session = "redacted-" + source_graph_sha[:24]
    identity_map = _identity_map(graph, conversations, policy, derived_session)
    source_refs = _source_reference_map(graph, conversations)

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".execweave-redacted-", dir=parent))
    store = FullFidelityContentStore(temporary)
    mapped: dict[str, dict[str, Any]] = {}
    lineage_rows: list[dict[str, Any]] = []
    try:
        completed_source_bytes = 0
        for path in sorted(source_refs):
            ref = source_refs[path]
            remaining = MAX_DERIVATIVE_TOTAL_BYTES - completed_source_bytes
            if remaining < 0:
                raise RedactedArchiveError("derivative_content_limit")
            try:
                fp, raw = _integrity_read(
                    source_root, path, min(MAX_DERIVATIVE_FILE_BYTES, remaining), collect=True
                )
            except ArchiveReadError as exc:
                raise RedactedArchiveError("source_content_unreadable") from exc
            completed_source_bytes += len(raw)
            if fp.get("sha256") != ref.get("sha256") or (
                "size_bytes" in ref
                and ref.get("size_bytes") is not None
                and fp.get("size_bytes") != ref.get("size_bytes")
            ):
                raise RedactedArchiveError("source_content_changed")
            suffix = Path(path).suffix
            media = (
                ref.get("media_type")
                if isinstance(ref.get("media_type"), str)
                else (
                    "application/json"
                    if suffix == ".json"
                    else "text/plain; charset=utf-8"
                    if suffix == ".txt"
                    else "application/octet-stream"
                )
            )
            payload, derived_media, actions = _redact_content(raw, suffix, media, policy)
            content_kind = (
                ref.get("content_kind")
                if isinstance(ref.get("content_kind"), str) and ref.get("content_kind")
                else "redacted_content"
            )
            derived = store.put_bytes(
                payload,
                content_kind=content_kind,
                media_type=derived_media,
                representation="redacted_derivative",
            ).to_dict()
            mapped[path] = derived
            lineage_rows.append(
                {
                    "source": {"path": path, "sha256": ref["sha256"], "size_bytes": len(raw)},
                    "derived": {
                        "path": derived["path"],
                        "sha256": derived["sha256"],
                        "size_bytes": derived["size_bytes"],
                    },
                    "actions": actions,
                    "changed": raw != payload,
                }
            )

        new_graph = _rewrite_index(graph, policy=policy, refs=mapped, id_map=identity_map)
        new_conversations = _rewrite_index(
            conversations, policy=policy, refs=mapped, id_map=identity_map
        )
        derivative_meta = {
            "format": DERIVATIVE_FORMAT,
            "policy_sha256": policy_sha,
            "source_graph_sha256": source_graph_sha,
            "lineage_file": "lineage.json",
            "limitation": "Redaction follows the approved explicit policy; this is not an anonymity guarantee or proof that no other sensitive values remain.",
        }
        new_graph["redacted_derivative"] = derivative_meta
        new_conversations["redacted_derivative"] = derivative_meta
        graph_raw = _canonical(new_graph)
        conversations_raw = _canonical(new_conversations)
        _write_bytes(temporary / "graph.json", graph_raw)
        _write_bytes(temporary / "conversations.json", conversations_raw)
        viewer = render_static_dashboard_html(
            new_graph, conversation_entries=new_conversations["entries"]
        )
        _write_bytes(temporary / "viewer.html", viewer.encode("utf-8"))
        derived_primary = {name: hash_export(temporary, name) for name in REQUIRED_EXPORTS}
        lineage = {
            "format": LINEAGE_FORMAT,
            "policy": {"name": policy["name"], "sha256": policy_sha},
            "source": {
                "finalization": _fingerprint(source_final_raw),
                "artifacts": source_primary,
                "content_file_count": source_integrity["verified_file_count"],
            },
            "derived": {
                "session_id": derived_session,
                "artifacts": derived_primary,
                "content_file_count": len({row["derived"]["path"] for row in lineage_rows}),
            },
            "mappings": lineage_rows,
            "limitations": [
                "Source archive bytes are not included solely for lineage verification.",
                "The policy body is not included because redaction terms can themselves be sensitive.",
                "A complete derivative integrity check does not prove anonymization, source authenticity, provider recall, or task correctness.",
            ],
        }
        lineage_raw = _canonical(lineage)
        _write_bytes(temporary / "lineage.json", lineage_raw)
        report = record_finalization(temporary, state="complete")
        report["derivation"] = {
            "format": DERIVATIVE_FORMAT,
            "lineage": _fingerprint(lineage_raw),
            "policy_sha256": policy_sha,
            "source_finalization_sha256": hashlib.sha256(source_final_raw).hexdigest(),
        }
        _write_bytes(
            temporary / "finalization.json",
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            + b"\n",
        )
        verified = verify_redacted_archive(temporary, source_root=source_root)
        if verified["state"] != "complete" or verified["source_state"] != "complete":
            raise RedactedArchiveError("derivative_verification_failed")
        os.replace(temporary, destination)
        return verified
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _validate_lineage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "format",
        "policy",
        "source",
        "derived",
        "mappings",
        "limitations",
    }:
        raise RedactedArchiveError("invalid_lineage")
    if value.get("format") != LINEAGE_FORMAT:
        raise RedactedArchiveError("invalid_lineage")
    policy = value.get("policy")
    if (
        not isinstance(policy, dict)
        or set(policy) != {"name", "sha256"}
        or not isinstance(policy["name"], str)
        or _HASH.fullmatch(str(policy["sha256"])) is None
    ):
        raise RedactedArchiveError("invalid_lineage")
    for side in ("source", "derived"):
        item = value.get(side)
        if not isinstance(item, dict) or not isinstance(item.get("artifacts"), dict):
            raise RedactedArchiveError("invalid_lineage")
        for name in REQUIRED_EXPORTS:
            if not _validate_fingerprint(item["artifacts"].get(name)):
                raise RedactedArchiveError("invalid_lineage")
    source = value["source"]
    if (
        not _validate_fingerprint(source.get("finalization"))
        or type(source.get("content_file_count")) is not int
        or source["content_file_count"] < 0
    ):
        raise RedactedArchiveError("invalid_lineage")
    derived = value["derived"]
    if (
        not isinstance(derived.get("session_id"), str)
        or not derived["session_id"]
        or type(derived.get("content_file_count")) is not int
        or derived["content_file_count"] < 0
    ):
        raise RedactedArchiveError("invalid_lineage")
    mappings = value.get("mappings")
    if not isinstance(mappings, list) or len(mappings) > 100_000:
        raise RedactedArchiveError("invalid_lineage")
    seen_source: set[str] = set()
    for row in mappings:
        if not isinstance(row, dict) or set(row) != {"source", "derived", "actions", "changed"}:
            raise RedactedArchiveError("invalid_lineage")
        if (
            type(row["changed"]) is not bool
            or not isinstance(row["actions"], list)
            or not all(isinstance(x, str) for x in row["actions"])
        ):
            raise RedactedArchiveError("invalid_lineage")
        for side in ("source", "derived"):
            ref = row[side]
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "size_bytes"}:
                raise RedactedArchiveError("invalid_lineage")
            if (
                not isinstance(ref["path"], str)
                or CONTENT_PATH.fullmatch(ref["path"]) is None
                or _HASH.fullmatch(str(ref["sha256"])) is None
                or type(ref["size_bytes"]) is not int
                or ref["size_bytes"] < 0
            ):
                raise RedactedArchiveError("invalid_lineage")
            if CONTENT_PATH.fullmatch(ref["path"])[1] != ref["sha256"]:
                raise RedactedArchiveError("invalid_lineage")
        if row["source"]["path"] in seen_source:
            raise RedactedArchiveError("invalid_lineage")
        seen_source.add(row["source"]["path"])
    if not isinstance(value["limitations"], list) or not all(
        isinstance(x, str) for x in value["limitations"]
    ):
        raise RedactedArchiveError("invalid_lineage")
    return value


def verify_redacted_archive(
    derived_root: str | Path, *, source_root: str | Path | None = None
) -> dict[str, Any]:
    root = Path(derived_root).expanduser().absolute()
    try:
        report_raw = _read_named_regular(root, "finalization.json", MAX_FINALIZATION_BYTES)
        report = _strict_json(report_raw, MAX_FINALIZATION_BYTES)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RedactedArchiveError("invalid_finalization") from exc
    if summarize_finalization(report).get("state") != "complete":
        raise RedactedArchiveError("derivative_incomplete")
    integrity = audit_content_references(
        root, max_index_bytes=MAX_INDEX_BYTES, max_content_bytes=MAX_CONTENT_BYTES
    )
    if integrity.get("state") != "complete":
        raise RedactedArchiveError("derivative_incomplete")
    for name in REQUIRED_EXPORTS:
        if hash_export(root, name) != report.get("artifacts", {}).get(name):
            raise RedactedArchiveError("derivative_primary_changed")
    derivation = report.get("derivation")
    if (
        not isinstance(derivation, dict)
        or set(derivation) != {"format", "lineage", "policy_sha256", "source_finalization_sha256"}
        or derivation.get("format") != DERIVATIVE_FORMAT
        or not _validate_fingerprint(derivation.get("lineage"))
        or _HASH.fullmatch(str(derivation.get("policy_sha256"))) is None
        or _HASH.fullmatch(str(derivation.get("source_finalization_sha256"))) is None
    ):
        raise RedactedArchiveError("invalid_derivation_receipt")
    lineage_raw = _read_named_regular(root, "lineage.json", MAX_LINEAGE_BYTES)
    if _fingerprint(lineage_raw) != derivation["lineage"]:
        raise RedactedArchiveError("lineage_hash_mismatch")
    try:
        lineage = _validate_lineage(_strict_json(lineage_raw, MAX_LINEAGE_BYTES))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RedactedArchiveError("invalid_lineage") from exc
    if lineage["policy"]["sha256"] != derivation["policy_sha256"]:
        raise RedactedArchiveError("lineage_policy_mismatch")
    current_primary = {name: hash_export(root, name) for name in REQUIRED_EXPORTS}
    if lineage["derived"]["artifacts"] != current_primary:
        raise RedactedArchiveError("lineage_derived_mismatch")
    try:
        _graph_fp, graph_raw = _integrity_read(root, "graph.json", MAX_INDEX_BYTES, collect=True)
        graph = _strict_json(graph_raw, MAX_INDEX_BYTES)
    except (ArchiveReadError, ValueError, UnicodeError, RecursionError) as exc:
        raise RedactedArchiveError("invalid_derivative_index") from exc
    marker = graph.get("redacted_derivative") if isinstance(graph, dict) else None
    if (
        not isinstance(marker, dict)
        or marker.get("format") != DERIVATIVE_FORMAT
        or marker.get("policy_sha256") != derivation["policy_sha256"]
        or marker.get("lineage_file") != "lineage.json"
    ):
        raise RedactedArchiveError("lineage_graph_marker_mismatch")
    mapping_paths = set()
    for row in lineage["mappings"]:
        d = row["derived"]
        fingerprint = integrity["verified_files"].get(d["path"])
        if fingerprint != {"sha256": d["sha256"], "size_bytes": d["size_bytes"]}:
            raise RedactedArchiveError("lineage_content_mismatch")
        mapping_paths.add(d["path"])
    if mapping_paths != set(integrity["verified_files"]):
        raise RedactedArchiveError("lineage_content_inventory_mismatch")
    if lineage["derived"]["content_file_count"] != len(mapping_paths):
        raise RedactedArchiveError("lineage_content_inventory_mismatch")

    source_state = "not_checked"
    if source_root is not None:
        source_path = Path(source_root).expanduser().absolute()
        source_graph, source_conversations, source_report, source_final_raw, source_integrity = (
            _load_source(source_path)
        )
        del source_graph, source_conversations, source_report
        if (
            _fingerprint(source_final_raw) != lineage["source"]["finalization"]
            or hashlib.sha256(source_final_raw).hexdigest()
            != derivation["source_finalization_sha256"]
        ):
            raise RedactedArchiveError("lineage_source_finalization_mismatch")
        source_primary = {name: hash_export(source_path, name) for name in REQUIRED_EXPORTS}
        if source_primary != lineage["source"]["artifacts"]:
            raise RedactedArchiveError("lineage_source_artifact_mismatch")
        if source_integrity["verified_file_count"] != lineage["source"]["content_file_count"]:
            raise RedactedArchiveError("lineage_source_inventory_mismatch")
        for row in lineage["mappings"]:
            s = row["source"]
            if source_integrity["verified_files"].get(s["path"]) != {
                "sha256": s["sha256"],
                "size_bytes": s["size_bytes"],
            }:
                raise RedactedArchiveError("lineage_source_content_mismatch")
        source_state = "complete"
    return {
        "state": "complete",
        "source_state": source_state,
        "policy_sha256": derivation["policy_sha256"],
        "mapping_count": len(lineage["mappings"]),
        "derived_content_file_count": len(mapping_paths),
        "lineage": derivation["lineage"],
        "limitation": "Derivative integrity and lineage declarations are verified; anonymization, source authenticity and task correctness are not established.",
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or verify a redacted ExecWeave derivative archive"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("source")
    create.add_argument("destination")
    create.add_argument("--policy", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("derived")
    verify.add_argument("--source")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_redacted_archive(args.source, args.destination, args.policy)
        else:
            result = verify_redacted_archive(args.derived, source_root=args.source)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (RedactedArchiveError, ArchiveReadError, ValueError, OSError) as exc:
        print(json.dumps({"state": "failed", "code": str(exc)}), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())

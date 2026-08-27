from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "integrity.json"
SCHEMA_VERSION = "0.1"
HASH_ALGORITHM = "sha256"
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class IntegrityResult:
    valid: bool
    run_root: str
    manifest_path: str
    sealed_file_count: int
    checked_file_count: int
    manifest_body_sha256: str | None
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["errors"] = list(self.errors)
        return data


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest_path(run_root: Path) -> Path:
    return run_root / MANIFEST_FILENAME


def _inventory(run_root: Path) -> list[dict[str, object]]:
    if not run_root.is_dir():
        raise ValueError(f"run directory does not exist: {run_root}")

    manifest_path = _manifest_path(run_root)
    entries: list[dict[str, object]] = []
    for path in sorted(run_root.rglob("*"), key=lambda item: item.as_posix()):
        if path == manifest_path:
            continue
        if path.is_symlink():
            raise ValueError(f"run integrity does not seal symbolic links: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(run_root).as_posix()
        entries.append(
            {
                "path": relative,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return entries


def _manifest_body(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "hash_algorithm": HASH_ALGORITHM,
        "trust_model": {
            "scope": "local_post_seal_corruption_detection",
            "malicious_writer_resistance": False,
            "external_trust_anchor": False,
        },
        "sealed_file_count": len(entries),
        "files": entries,
    }


def seal_run_integrity(run_root: str | Path) -> dict[str, object]:
    root = Path(run_root).expanduser().resolve()
    manifest_path = _manifest_path(root)
    if manifest_path.exists():
        raise FileExistsError(f"run integrity manifest already exists: {manifest_path}")

    body = _manifest_body(_inventory(root))
    body_digest = _sha256_bytes(_canonical_bytes(body))
    manifest = {**body, "manifest_body_sha256": body_digest}
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"

    fd, temp_name = tempfile.mkstemp(prefix=".execweave-integrity-", dir=root)
    temp_path = Path(temp_name)
    try:
        if os.name != "nt":
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(manifest_path)
        if os.name != "nt":
            try:
                manifest_path.chmod(0o600)
            except OSError:
                pass
    finally:
        temp_path.unlink(missing_ok=True)
    return manifest


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("manifest file path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or value != candidate.as_posix():
        raise ValueError(f"unsafe manifest file path: {value!r}")
    if value == MANIFEST_FILENAME:
        raise ValueError("manifest cannot seal itself")
    return value


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"run integrity manifest not found: {path}")
    if path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise ValueError("run integrity manifest exceeds size limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("run integrity manifest must be a JSON object")
    return value


def verify_run_integrity(run_root: str | Path) -> IntegrityResult:
    root = Path(run_root).expanduser().resolve()
    manifest_path = _manifest_path(root)
    errors: list[str] = []
    body_digest: str | None = None
    sealed_count = 0
    checked_count = 0

    try:
        manifest = _load_manifest(manifest_path)
        expected_keys = {
            "schema_version",
            "hash_algorithm",
            "trust_model",
            "sealed_file_count",
            "files",
            "manifest_body_sha256",
        }
        if set(manifest) != expected_keys:
            raise ValueError("run integrity manifest has unknown or missing top-level fields")
        if manifest["schema_version"] != SCHEMA_VERSION:
            raise ValueError(f"unsupported run integrity schema: {manifest['schema_version']!r}")
        if manifest["hash_algorithm"] != HASH_ALGORITHM:
            raise ValueError(f"unsupported hash algorithm: {manifest['hash_algorithm']!r}")

        trust_model = manifest["trust_model"]
        expected_trust = {
            "scope": "local_post_seal_corruption_detection",
            "malicious_writer_resistance": False,
            "external_trust_anchor": False,
        }
        if trust_model != expected_trust:
            raise ValueError("run integrity trust model does not match the schema contract")

        files = manifest["files"]
        if not isinstance(files, list):
            raise ValueError("manifest files must be a list")
        sealed_count = len(files)
        if manifest["sealed_file_count"] != sealed_count:
            raise ValueError("sealed_file_count does not match files")

        body = {key: manifest[key] for key in expected_keys if key != "manifest_body_sha256"}
        body_digest = _sha256_bytes(_canonical_bytes(body))
        if manifest["manifest_body_sha256"] != body_digest:
            errors.append("manifest body digest mismatch")

        expected_paths: set[str] = set()
        for entry in files:
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size_bytes"}:
                raise ValueError("manifest file entry has invalid fields")
            relative = _safe_relative_path(entry["path"])
            if relative in expected_paths:
                raise ValueError(f"duplicate manifest file path: {relative}")
            expected_paths.add(relative)
            expected_hash = entry["sha256"]
            expected_size = entry["size_bytes"]
            if (
                not isinstance(expected_hash, str)
                or len(expected_hash) != 64
                or any(character not in "0123456789abcdef" for character in expected_hash)
            ):
                raise ValueError(f"invalid sha256 for {relative}")
            if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size < 0:
                raise ValueError(f"invalid size for {relative}")

            path = root / Path(relative)
            if path.is_symlink():
                errors.append(f"symbolic link replaced sealed file: {relative}")
                continue
            if not path.is_file():
                errors.append(f"missing sealed file: {relative}")
                continue
            checked_count += 1
            actual_size = path.stat().st_size
            if actual_size != expected_size:
                errors.append(
                    f"size mismatch for {relative}: expected {expected_size}, got {actual_size}"
                )
                continue
            actual_hash = _sha256_file(path)
            if actual_hash != expected_hash:
                errors.append(f"sha256 mismatch for {relative}")

        try:
            current_entries = _inventory(root)
            current_paths = {str(entry["path"]) for entry in current_entries}
            for unexpected in sorted(current_paths - expected_paths):
                errors.append(f"unsealed file present: {unexpected}")
        except ValueError as exc:
            errors.append(str(exc))
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        errors.append(str(exc))

    return IntegrityResult(
        valid=not errors,
        run_root=str(root),
        manifest_path=str(manifest_path),
        sealed_file_count=sealed_count,
        checked_file_count=checked_count,
        manifest_body_sha256=body_digest,
        errors=tuple(errors),
    )

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_CONTENT_DIR = "content"
_HASH_ALGORITHM = "sha256"
_COPY_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ContentReference:
    """Reference to one complete locally stored observation.

    ``complete_from_source`` means ExecWeave stored the complete value supplied by
    the integration point. It does not claim the provider exposed hidden stages.
    """

    sha256: str
    path: str
    media_type: str
    size_bytes: int
    content_kind: str
    representation: str
    complete_from_source: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FullFidelityContentStore:
    """Content-addressed storage for prompt, response, tool, and provider evidence."""

    def __init__(self, run_root: str | Path) -> None:
        self.run_root = Path(run_root).expanduser().resolve()

    def put_bytes(
        self,
        payload: bytes,
        *,
        content_kind: str,
        media_type: str = "application/octet-stream",
        representation: str = "raw_bytes",
    ) -> ContentReference:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if not content_kind:
            raise ValueError("content_kind must not be empty")
        digest = hashlib.sha256(payload).hexdigest()
        suffix = _suffix_for_media_type(media_type)
        relative = Path(_CONTENT_DIR) / _HASH_ALGORITHM / f"{digest}{suffix}"
        self._write_once(self.run_root / relative, payload)
        return ContentReference(
            sha256=digest,
            path=relative.as_posix(),
            media_type=media_type,
            size_bytes=len(payload),
            content_kind=content_kind,
            representation=representation,
        )

    def put_text(
        self,
        text: str,
        *,
        content_kind: str,
        media_type: str = "text/plain; charset=utf-8",
        representation: str = "raw_utf8",
    ) -> ContentReference:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        return self.put_bytes(
            text.encode("utf-8"),
            content_kind=content_kind,
            media_type=media_type,
            representation=representation,
        )

    def put_json(
        self,
        value: Any,
        *,
        content_kind: str,
        media_type: str = "application/json",
        representation: str = "parsed_json_canonical",
    ) -> ContentReference:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self.put_bytes(
            payload,
            content_kind=content_kind,
            media_type=media_type,
            representation=representation,
        )

    def put_file(
        self,
        source: str | Path,
        *,
        content_kind: str,
        media_type: str = "application/octet-stream",
        representation: str = "source_file_snapshot",
    ) -> ContentReference:
        """Stream one provider-declared file into the run-local content store.

        The source is stat-checked before and after the copy. If it changes while
        being read, no reference is returned and the temporary snapshot is removed.
        """
        if not content_kind:
            raise ValueError("content_kind must not be empty")
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        destination_dir = self.run_root / _CONTENT_DIR / _HASH_ALGORITHM
        destination_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                destination_dir.chmod(0o700)
            except OSError:
                pass

        before = source_path.stat()
        fd, temp_name = tempfile.mkstemp(prefix=".execweave-content-", dir=destination_dir)
        temp_path = Path(temp_name)
        digest = hashlib.sha256()
        size = 0
        try:
            if os.name != "nt":
                try:
                    os.fchmod(fd, 0o600)
                except OSError:
                    pass
            with source_path.open("rb") as source_handle, os.fdopen(
                fd, "wb", closefd=True
            ) as destination_handle:
                while True:
                    chunk = source_handle.read(_COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    destination_handle.write(chunk)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())

            after = source_path.stat()
            before_signature = (before.st_size, before.st_mtime_ns)
            after_signature = (after.st_size, after.st_mtime_ns)
            if before_signature != after_signature or size != after.st_size:
                raise RuntimeError(f"source changed while archiving content: {source_path}")

            digest_hex = digest.hexdigest()
            suffix = _suffix_for_media_type(media_type)
            relative = Path(_CONTENT_DIR) / _HASH_ALGORITHM / f"{digest_hex}{suffix}"
            destination = self.run_root / relative
            if destination.exists():
                if destination.stat().st_size != size or self._file_sha256(destination) != digest_hex:
                    raise RuntimeError(f"content hash collision at {destination}")
            else:
                temp_path.replace(destination)
            if os.name != "nt":
                try:
                    destination.chmod(0o600)
                except OSError:
                    pass
            return ContentReference(
                sha256=digest_hex,
                path=relative.as_posix(),
                media_type=media_type,
                size_bytes=size,
                content_kind=content_kind,
                representation=representation,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _write_once(self, destination: Path, payload: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                destination.parent.chmod(0o700)
            except OSError:
                pass
        if destination.exists():
            if destination.read_bytes() != payload:
                raise RuntimeError(f"content hash collision at {destination}")
            return

        fd, temp_name = tempfile.mkstemp(prefix=".execweave-content-", dir=destination.parent)
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
            try:
                temp_path.replace(destination)
            except OSError:
                if destination.exists() and destination.read_bytes() == payload:
                    temp_path.unlink(missing_ok=True)
                else:
                    raise
            if os.name != "nt":
                try:
                    destination.chmod(0o600)
                except OSError:
                    pass
        finally:
            temp_path.unlink(missing_ok=True)


def _suffix_for_media_type(media_type: str) -> str:
    normalized = media_type.split(";", 1)[0].strip().lower()
    if normalized == "application/json" or normalized.endswith("+json"):
        return ".json"
    if normalized.startswith("text/"):
        return ".txt"
    return ".bin"

"""Canonicalize creator-platform metadata in pure-Python wheel ZIP archives."""
from __future__ import annotations

import argparse
import hashlib
import struct
import zipfile
from pathlib import Path

_EOCD_SIGNATURE = b"PK\x05\x06"
_CENTRAL_SIGNATURE = b"PK\x01\x02"
_EOCD = struct.Struct("<4s4H2LH")


def _member_fingerprint(path: Path) -> list[tuple[str, int, int, str]]:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"wheel contains a corrupt member: {bad}")
        return [
            (
                info.filename,
                info.CRC,
                info.file_size,
                hashlib.sha256(archive.read(info)).hexdigest(),
            )
            for info in archive.infolist()
        ]


def canonicalize_wheel(path: Path) -> None:
    """Set only ZIP creator-platform bytes to the Unix value used by Linux/macOS."""
    if path.suffix != ".whl":
        raise RuntimeError(f"not a wheel: {path}")
    before = _member_fingerprint(path)
    data = bytearray(path.read_bytes())
    start = max(0, len(data) - (65535 + _EOCD.size))
    eocd_offset = data.rfind(_EOCD_SIGNATURE, start)
    if eocd_offset < 0:
        raise RuntimeError(f"wheel has no end-of-central-directory record: {path}")
    (
        signature,
        disk,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        comment_len,
    ) = _EOCD.unpack_from(data, eocd_offset)
    if signature != _EOCD_SIGNATURE:
        raise RuntimeError(f"invalid EOCD signature: {path}")
    if disk or central_disk or disk_entries != total_entries:
        raise RuntimeError(f"multi-disk ZIP is not supported for wheels: {path}")
    if total_entries == 0xFFFF or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF:
        raise RuntimeError(f"ZIP64 wheel is not supported by this canonicalizer: {path}")
    if eocd_offset + _EOCD.size + comment_len != len(data):
        raise RuntimeError(f"wheel EOCD/comment length is inconsistent: {path}")

    position = central_offset
    for index in range(total_entries):
        if data[position : position + 4] != _CENTRAL_SIGNATURE:
            raise RuntimeError(f"invalid central-directory entry {index} in {path}")
        # Byte 5 is the creator-OS byte of the central `version made by` field.
        # This is the only byte that differed in the verified Windows wheel.
        data[position + 5] = 3
        filename_len, extra_len, entry_comment_len = struct.unpack_from(
            "<HHH", data, position + 28
        )
        position += 46 + filename_len + extra_len + entry_comment_len
    if position != central_offset + central_size:
        raise RuntimeError(f"central-directory size mismatch in {path}")

    path.write_bytes(data)
    after = _member_fingerprint(path)
    if after != before:
        raise RuntimeError(f"canonicalization changed wheel member bytes: {path}")
    with zipfile.ZipFile(path) as archive:
        noncanonical = [info.filename for info in archive.infolist() if info.create_system != 3]
    if noncanonical:
        raise RuntimeError(
            f"wheel still contains non-canonical creator metadata: {noncanonical[:5]}"
        )


def _wheel_paths(arguments: list[str]) -> list[Path]:
    result: list[Path] = []
    for raw in arguments:
        path = Path(raw)
        if path.is_dir():
            result.extend(sorted(path.glob("*.whl")))
        else:
            result.append(path)
    unique = list(dict.fromkeys(path.resolve() for path in result))
    if not unique:
        raise RuntimeError("no wheel files found")
    return unique


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="wheel files or directories containing wheels")
    args = parser.parse_args()
    for path in _wheel_paths(args.paths):
        canonicalize_wheel(path)
        print(f"canonical wheel: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

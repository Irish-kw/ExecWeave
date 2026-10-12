"""Reader provenance for CLI JSON, separate from the recorded producer version."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def reader_identity() -> dict[str, str]:
    try:
        installed = version("execweave")
    except PackageNotFoundError:
        from . import __version__
        installed = __version__
    return {"name": "execweave", "version": installed}

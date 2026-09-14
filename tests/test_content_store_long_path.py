from __future__ import annotations

import os
from pathlib import Path

from execweave.content_store import FullFidelityContentStore


def test_content_store_supports_windows_long_run_roots(tmp_path: Path) -> None:
    long_root = tmp_path / ("execweave-long-root-" + "x" * 110)
    long_root.mkdir()
    store = FullFidelityContentStore(long_root)

    reference = store.put_json({"status": "ok"}, content_kind="long_path")

    assert reference.size_bytes > 0
    if os.name == "nt":
        from execweave.content_store import _filesystem_path

        assert _filesystem_path(long_root / reference.path).is_file()

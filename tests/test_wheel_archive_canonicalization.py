from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path


def _write(path: Path, create_system: int) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in [
            ("execweave/__init__.py", b"x=1\n"),
            ("execweave-0.dist-info/RECORD", b"record\n"),
        ]:
            info = zipfile.ZipInfo(name, (2024, 1, 2, 3, 4, 6))
            info.create_system = create_system
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)


def test_wheel_creator_platform_is_canonicalized_without_member_changes(tmp_path: Path) -> None:
    unix = tmp_path / "unix.whl"
    windows = tmp_path / "windows.whl"
    _write(unix, 3)
    _write(windows, 0)
    assert unix.read_bytes() != windows.read_bytes()

    script = Path(__file__).resolve().parents[1] / "scripts" / "canonicalize_wheel.py"
    subprocess.run([sys.executable, str(script), str(unix), str(windows)], check=True)

    assert unix.read_bytes() == windows.read_bytes()
    with zipfile.ZipFile(windows) as archive:
        assert all(info.create_system == 3 for info in archive.infolist())
        assert archive.read("execweave/__init__.py") == b"x=1\n"
        assert archive.read("execweave-0.dist-info/RECORD") == b"record\n"

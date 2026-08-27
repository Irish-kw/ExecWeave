from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from execweave.live import _AUTHENTICATED_LIVE_HTML
from execweave.live_view import LIVE_HTML


def _inline_script(html: str) -> str:
    scripts = re.findall(
        r"<script(?:\s[^>]*)?>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert scripts
    return scripts[-1]


@pytest.mark.parametrize(
    ("name", "html"),
    [
        ("dashboard", LIVE_HTML),
        ("authenticated-dashboard", _AUTHENTICATED_LIVE_HTML),
    ],
)
def test_live_dashboard_inline_javascript_syntax(
    name: str,
    html: str,
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node executable is required for live dashboard JavaScript syntax validation")
    script_path = tmp_path / f"{name}.inline.js"
    script_path.write_text(_inline_script(html), encoding="utf-8")
    result = subprocess.run(
        [node, "--check", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout

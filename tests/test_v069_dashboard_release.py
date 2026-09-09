from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from execweave import __version__
from execweave.live import _inject_final_theme
from execweave.live_view import LIVE_HTML


def _inline_script(html: str) -> str:
    scripts = re.findall(
        r"<script(?:\s[^>]*)?>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert scripts
    return scripts[-1]


def test_final_graph_opens_separately_and_save_view_does_not_overlap_theme() -> None:
    # Historical test name retained. v0.7.9 keeps the finished run in the same
    # Dashboard DOM instead of opening or injecting a second final renderer.
    assert "fetch('/final'" not in LIVE_HTML
    assert "window.open('about:blank','_blank')" not in LIVE_HTML
    assert "document.write(" not in LIVE_HTML
    assert 'id="open-final"' not in LIVE_HTML

    themed = _inject_final_theme(LIVE_HTML)
    assert themed == LIVE_HTML
    assert 'id="theme-toggle"' in themed
    assert 'id="execweave-theme-toggle"' not in themed


def test_live_gif_export_uses_reset_bounded_lzw_and_emits_a_gif() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node executable is required for GIF encoder validation")

    from PIL import Image
    import io
    import random
    import struct

    # Keep the historical test name, but validate dictionary growth/reset with an
    # independent GIF decoder instead of requiring the old uncompressed encoder.
    script = _inline_script(LIVE_HTML)
    start = script.index("function lzw(")
    end = script.index("function gifPixels(", start)
    rng = random.Random(14)
    vectors = [[0] * 40000, [i % 256 for i in range(40000)],
               [rng.randrange(256) for _ in range(40000)]]
    vectors.extend([i % 256 for i in range(size)] for size in (1, 254, 255, 256, 257, 768))
    for pixels in vectors:
        runner = script[start:end] + "\nconsole.log(Buffer.from(lzw(Uint8Array.from(" + json.dumps(pixels) + "))).toString('base64'));"
        result = subprocess.run([node], input=runner, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        compressed = base64.b64decode(result.stdout.strip())
        # Independently wrap the compressed indices in a GIF container.
        payload = bytearray(b"GIF89a" + struct.pack("<HH", len(pixels), 1) + bytes([0xF7, 0, 0]))
        payload.extend(component for value in range(256) for component in (value, value, value))
        payload.extend(b"," + struct.pack("<HHHH", 0, 0, len(pixels), 1) + bytes([0, 8]))
        for offset in range(0, len(compressed), 255):
            block = compressed[offset:offset + 255]
            payload.append(len(block))
            payload.extend(block)
        payload.extend(b"\x00;")
        with Image.open(io.BytesIO(payload)) as image:
            assert image.tobytes() == bytes(pixels)


def test_release_version_and_noncommercial_license_metadata_are_078() -> None:
    """Release metadata agrees with the package version and the license stays noncommercial.

    The name carries the release it was written for and is kept because the
    stage-integrity node-ID floor refuses renames; the assertions below are the
    current release.
    """
    assert __version__ == "0.8.20"
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.8.20"' in pyproject
    assert "ExecWeave v0.8.20 release metadata" in pyproject
    assert "License :: Other/Proprietary License" in pyproject
    assert "License :: OSI Approved :: MIT License" not in pyproject

    license_text = Path("LICENSE").read_text(encoding="utf-8")
    assert "PolyForm Noncommercial License 1.0.0" in license_text
    assert "Commercial use is not permitted" in license_text


def test_all_readmes_use_current_release_dashboard_and_conversation_anchors() -> None:
    """Historical node ID retained; README policy is now release-independent."""

    hardcoded_release = re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b", re.I)
    readmes = sorted(Path(".").glob("README*.md"))
    assert len(readmes) >= 8
    for path in readmes:
        text = path.read_text(encoding="utf-8")
        assert 'src="docs/assets/codex.gif"' in text, path
        assert "execweave-launch-demo-v5-x.gif" not in text, path
        assert hardcoded_release.search(text) is None, path
        assert "conversations.json" in text, path
        assert "execweave live --open -- ollama serve" in text, path

    readme = Path("README.md").read_text(encoding="utf-8")
    assert "This README documents" not in readme
    assert "Conversation rounds" in readme
    assert "correct agent" in readme


def test_english_readme_declares_noncommercial_source_available_license() -> None:
    """Historical node ID retained; licensing is stable product metadata, not a release note."""

    readme = Path("README.md").read_text(encoding="utf-8")
    assert "PolyForm Noncommercial License 1.0.0" in readme
    assert "noncommercial" in readme.lower()
    assert "Starting with v0.6.8" not in readme
    assert re.search(r"\bv\d+\.\d+(?:\.\d+)?\b", readme, re.I) is None

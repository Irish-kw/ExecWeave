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


def _unpack_fixed_9bit_codes(payload: bytes) -> list[int]:
    buffer = 0
    bits = 0
    codes: list[int] = []
    for value in payload:
        buffer |= value << bits
        bits += 8
        while bits >= 9:
            codes.append(buffer & 0x1FF)
            buffer >>= 9
            bits -= 9
    return codes


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

    script = _inline_script(LIVE_HTML)
    start = script.index("function palette()")
    end = script.index("function nodeHex(")
    gif_functions = script[start:end]
    runner = f"""
{gif_functions}
(async()=>{{
  const pixels=Uint8Array.from(Array.from({{length:300}},(_,i)=>i%216));
  const compressed=lzw(pixels,8);
  const frame=Uint8Array.from([0,1,2,3]);
  const blob=gifBlob([frame],2,2,12);
  const gif=new Uint8Array(await blob.arrayBuffer());
  console.log(JSON.stringify({{
    lzw:Buffer.from(compressed).toString('base64'),
    gif:Buffer.from(gif).toString('base64')
  }}));
}})().catch(err=>{{console.error(err);process.exit(1)}});
"""
    result = subprocess.run(
        [node, "-e", runner],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    generated = json.loads(result.stdout.strip())

    codes = _unpack_fixed_9bit_codes(base64.b64decode(generated["lzw"]))
    assert codes[0] == 256
    assert codes[-1] == 257
    assert codes.count(256) >= 2
    assert max(codes) <= 257

    gif = base64.b64decode(generated["gif"])
    assert gif.startswith(b"GIF89a")
    assert gif.endswith(b"\x3b")
    assert len(gif) > 800


def test_release_version_and_noncommercial_license_metadata_are_078() -> None:
    """Release metadata agrees with the package version and the license stays noncommercial.

    The name carries the release it was written for and is kept because the
    stage-integrity node-ID floor refuses renames; the assertions below are the
    current release.
    """
    assert __version__ == "0.8.11"
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.8.11"' in pyproject
    assert "ExecWeave v0.8.11 release metadata" in pyproject
    assert "License :: Other/Proprietary License" in pyproject
    assert "License :: OSI Approved :: MIT License" not in pyproject

    license_text = Path("LICENSE").read_text(encoding="utf-8")
    assert "PolyForm Noncommercial License 1.0.0" in license_text
    assert "Commercial use is not permitted" in license_text


def test_all_readmes_use_current_release_dashboard_and_conversation_anchors() -> None:
    readmes = sorted(Path(".").glob("README*.md"))
    assert len(readmes) >= 8
    for path in readmes:
        text = path.read_text(encoding="utf-8")
        assert 'src="docs/assets/codex.gif"' in text, path
        assert "execweave-launch-demo-v5-x.gif" not in text, path
        assert "v0.6.5" not in text, path
        assert "v0.6.6" not in text, path
        assert "v0.6.7" not in text, path
        assert f"v{__version__}" in text, path
        assert "conversations.json" in text, path

    readme = Path("README.md").read_text(encoding="utf-8")
    assert f"This README documents **v{__version__}**." in readme
    assert "subagent responses remain attributed to the agent that produced them" in readme


def test_english_readme_declares_noncommercial_source_available_license() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "source-available" in readme
    assert "PolyForm Noncommercial License 1.0.0" in readme
    assert "Commercial use requires a separate written commercial license" in readme
    assert "Starting with v0.6.8" in readme

from __future__ import annotations

from pathlib import Path

import pytest

from execweave.opencode_plugin_cli import install_plugin, plugin_text


def test_opencode_plugin_omits_tool_output_and_sanitizes_args() -> None:
    text = plugin_text()
    assert '"tool.execute.before"' in text
    assert '"tool.execute.after"' in text
    assert "callID" in text
    assert "safeArgs" in text
    assert "output.output" not in text
    assert "output.metadata" not in text
    assert "parts:" not in text


def test_opencode_plugin_installer_refuses_overwrite(tmp_path: Path) -> None:
    target = install_plugin(tmp_path)
    assert target == tmp_path / ".opencode" / "plugins" / "execweave.ts"
    assert target.exists()
    with pytest.raises(FileExistsError):
        install_plugin(tmp_path)
    install_plugin(tmp_path, force=True)

from __future__ import annotations

from pathlib import Path

import pytest

from execweave.opencode_plugin_cli import install_plugin, plugin_text


def test_opencode_plugin_forwards_full_observable_surface() -> None:
    text = plugin_text()
    assert '"tool.execute.before"' in text
    assert '"tool.execute.after"' in text
    assert '"chat.message"' in text
    assert '"chat.params"' in text
    assert '"experimental.chat.messages.transform"' in text
    assert '"experimental.chat.system.transform"' in text
    assert '"experimental.text.complete"' in text
    assert "event: async" in text
    assert "output.args" in text
    assert "result: output" in text
    assert "output.message" in text
    assert "output.parts" in text
    assert "safeArgs" not in text
    assert '"shell.env"' not in text


def test_opencode_plugin_filters_transport_headers_before_emitting() -> None:
    text = plugin_text()
    assert "withoutTransportCredentials(output.headers)" in text
    assert '"authorization"' in text
    assert '"cookie"' in text


def test_opencode_plugin_installer_refuses_overwrite(tmp_path: Path) -> None:
    target = install_plugin(tmp_path)
    assert target == tmp_path / ".opencode" / "plugins" / "execweave.ts"
    assert target.exists()
    with pytest.raises(FileExistsError):
        install_plugin(tmp_path)
    install_plugin(tmp_path, force=True)

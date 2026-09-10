from __future__ import annotations

from pathlib import Path


def test_cross_platform_ci_covers_minimum_supported_python_on_all_three_os() -> None:
    text = Path('.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert 'systems = ["ubuntu-latest", "macos-latest", "windows-latest"]' in text
    assert 'versions = ["3.10", "3.12"] if cross_platform else ["3.12"]' in text


def test_publish_blocks_distribution_comparison_on_three_os_python310_gate() -> None:
    text = Path('.github/workflows/publish.yml').read_text(encoding='utf-8')
    assert 'minimum-python:' in text
    assert 'python-version: "3.10"' in text
    assert 'os: [ubuntu-latest, windows-latest, macos-latest]' in text
    assert 'needs: [verify, minimum-python]' in text


def test_python310_tomllib_backport_is_declared_for_test_and_release_tooling() -> None:
    text = Path('pyproject.toml').read_text(encoding='utf-8')
    assert '"tomli>=2.0; python_version < \'3.11\'"' in text

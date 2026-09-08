from __future__ import annotations

import tomllib
from pathlib import Path


def workflow() -> str:
    return Path('.github/workflows/publish.yml').read_text(encoding='utf-8')


def test_publish_has_no_pull_request_trigger_and_requires_three_os_verification() -> None:
    text = workflow()
    assert 'pull_request:' not in text
    assert 'os: [ubuntu-latest, windows-latest, macos-latest]' in text
    assert 'needs: verify' in text
    assert 'git merge-base --is-ancestor HEAD origin/main' in text
    assert 'python scripts/check_installed_dashboard.py' in text
    assert 'python scripts/check_sdist_install.py' in text
    assert 'python scripts/check_distribution_contents.py' in text
    assert 'python scripts/canonicalize_wheel.py dist dist-repro' in text


def test_pypi_job_uses_only_the_verified_ubuntu_distribution_artifact() -> None:
    text = workflow()
    assert 'name: python-package-distributions-${{ matrix.os }}' in text
    assert 'name: python-package-distributions-ubuntu-latest' in text
    assert 'id-token: write' in text
    assert 'pypa/gh-action-pypi-publish@release/v1' in text
    assert 'gh release view "$RELEASE_TAG"' in text
    assert 'already exists on PyPI' in text
    assert 'compare-distributions:' in text
    assert 'needs: compare-distributions' in text
    assert 'wheel hashes' in text
    assert 'info.create_system != 3' in text


def test_release_version_bump_is_deferred_to_release_only_stage() -> None:
    project = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
    init = Path('src/execweave/__init__.py').read_text(encoding='utf-8')
    version = project['project']['version']
    assert f'__version__ = "{version}"' in init
    # The stage-integrity gate, rather than this product test, decides when the
    # version may advance. That lets the same assertion remain valid after the
    # final metadata-only release/* PR bumps 0.8.16 to 0.8.17.
    integrity = Path('.github/workflows/provider-capability-stage-integrity.yml').read_text(
        encoding='utf-8'
    )
    assert 'release/*' in integrity
    assert "release tag {tag_version!r} does not match package version" in workflow()


def test_platform_independent_wheel_source_is_forced_to_lf() -> None:
    attrs = Path('.gitattributes').read_text(encoding='utf-8')
    assert '* text=auto eol=lf' in attrs
    assert "git ls-files --eol src/execweave | grep -q 'w/crlf'" in workflow()
    assert Path('scripts/canonicalize_wheel.py').is_file()


def test_sdist_is_allowlisted_away_from_acceptance_artifacts() -> None:
    pyproject = Path('pyproject.toml').read_text(encoding='utf-8')
    assert '[tool.hatch.build.targets.sdist]' in pyproject
    for required in ('/src/execweave', '/pyproject.toml', '/README.md', '/LICENSE'):
        assert f'"{required}"' in pyproject

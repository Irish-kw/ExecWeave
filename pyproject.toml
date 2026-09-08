from __future__ import annotations

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


def test_pypi_job_uses_only_the_verified_ubuntu_distribution_artifact() -> None:
    text = workflow()
    assert 'name: python-package-distributions-${{ matrix.os }}' in text
    assert 'name: python-package-distributions-ubuntu-latest' in text
    assert 'id-token: write' in text
    assert 'pypa/gh-action-pypi-publish@release/v1' in text
    assert 'gh release view "$RELEASE_TAG"' in text
    assert 'already exists on PyPI' in text


def test_release_version_bump_is_deferred_to_release_only_stage() -> None:
    pyproject = Path('pyproject.toml').read_text(encoding='utf-8')
    init = Path('src/execweave/__init__.py').read_text(encoding='utf-8')
    # Feature RC remains on the published baseline. The integrity gate explicitly
    # requires the version bump to land in a later release/* metadata-only PR.
    assert 'version = "0.8.16"' in pyproject
    assert '__version__ = "0.8.16"' in init
    assert 'release/*' in Path('.github/workflows/provider-capability-stage-integrity.yml').read_text(encoding='utf-8')
    assert "release tag {tag_version!r} does not match package version" in workflow()


def test_platform_independent_wheel_source_is_forced_to_lf() -> None:
    attrs = Path('.gitattributes').read_text(encoding='utf-8')
    assert '* text=auto eol=lf' in attrs
    assert "git ls-files --eol src/execweave | grep -q 'w/crlf'" in workflow()


def test_sdist_is_allowlisted_away_from_acceptance_artifacts() -> None:
    pyproject = Path('pyproject.toml').read_text(encoding='utf-8')
    assert '[tool.hatch.build.targets.sdist]' in pyproject
    for required in ('/src/execweave', '/pyproject.toml', '/README.md', '/LICENSE'):
        assert f'"{required}"' in pyproject

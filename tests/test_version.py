from importlib.metadata import version

import execweave


def test_package_version_matches_installed_metadata() -> None:
    assert execweave.__version__ == version("execweave")

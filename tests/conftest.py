from __future__ import annotations

import sys

try:
    import tomllib  # noqa: F401
except ModuleNotFoundError:  # Python 3.10
    import tomli

    sys.modules["tomllib"] = tomli

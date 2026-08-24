from unittest.mock import patch

import pytest

from execweave.backends import resolve_backend


def test_auto_prefers_strace_when_available() -> None:
    with patch("execweave.backends.strace_available", return_value=True):
        assert resolve_backend("auto") == "strace"


def test_auto_falls_back_to_portable() -> None:
    with patch("execweave.backends.strace_available", return_value=False):
        assert resolve_backend("auto") == "portable"


def test_requested_strace_fails_when_missing() -> None:
    with patch("execweave.backends.strace_available", return_value=False):
        with pytest.raises(RuntimeError):
            resolve_backend("strace")

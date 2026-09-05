from __future__ import annotations

from . import _http_proxy_base as _base
from ._http_proxy_stage import *  # noqa: F403


def _safe_http_reason(message: str | None) -> str | None:
    """Return a single-line HTTP reason phrase that BaseHTTPRequestHandler can encode."""
    if message is None:
        return None
    single_line = " ".join(str(message).splitlines())
    return single_line.encode("latin-1", errors="replace").decode("latin-1")


class ExecWeaveHTTPProxyHandler(_base.ExecWeaveHTTPProxyHandler):
    """Security-equivalent handler used by the staged acceptance relay."""

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        # BaseHTTPRequestHandler writes the status line as latin-1. Windows socket
        # errors can be localized (for example WinError 10061 in Chinese), so a raw
        # exception string here can turn a recoverable 502 into UnicodeEncodeError
        # and an EOF at the client. Preserve the diagnostic shape but fail closed to
        # an encodable, single-line reason phrase.
        super().send_error(code, _safe_http_reason(message), explain)

    def do_CONNECT(self) -> None:
        self.send_error(405, "CONNECT is disabled; ExecWeave does not perform TLS MITM")

    def _relay(self) -> None:
        # The product default uses file-backed response capture so raw full-fidelity
        # evidence does not require retaining the entire provider response in RAM.
        # Explicit custom recorders keep the historical bytes callback contract.
        if self.server.recorder is _base.record_exchange_fail_open:
            from ._http_proxy_bounded import relay_default

            relay_default(self)
            return
        super()._relay()


# The base server resolves this module global when each server instance is created.
# Point it at the handler whose CONNECT refusal is visible to the release red-line
# guard, so the checked implementation and the runtime implementation are the same.
_base.ExecWeaveHTTPProxyHandler = ExecWeaveHTTPProxyHandler


def __getattr__(name: str):
    from . import _http_proxy_stage as _stage

    return getattr(_stage, name)

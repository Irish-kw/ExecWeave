from __future__ import annotations

from . import _http_proxy_base as _base
from ._http_proxy_stage import *  # noqa: F403


class ExecWeaveHTTPProxyHandler(_base.ExecWeaveHTTPProxyHandler):
    """Security-equivalent handler used by the staged acceptance relay."""

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

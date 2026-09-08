"""Conservative Winsock fallback for a timed-out pre-launch loopback connect."""
from __future__ import annotations

import ipaddress
import socket
import sys
from contextlib import ExitStack


def windows_exclusive_endpoint_available(host: str, port: int) -> bool:
    """Require exclusive binds, not a timeout, as evidence of unused addresses.

    A short Windows connect can time out before an unused port reports refusal.
    SO_EXCLUSIVEADDRUSE prevents taking over an existing bind. Every resolved
    loopback address must be exclusively bindable at the same instant; sockets
    are closed before the real relay/child starts. No listener is created and no
    SO_REUSEADDR is enabled. This proves availability only at the launch boundary,
    not ownership of an unrelated service started later.
    """
    exclusive = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
    if sys.platform != 'win32' or exclusive is None or not 0 < port <= 65535:
        return False
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM,
                                       proto=socket.IPPROTO_TCP)
        seen = set()
        with ExitStack() as stack:
            for family, kind, protocol, _, address in addresses:
                if family not in (socket.AF_INET, socket.AF_INET6):
                    return False
                if not ipaddress.ip_address(address[0]).is_loopback:
                    return False
                key = (family, address)
                if key in seen:
                    continue
                seen.add(key)
                reservation = stack.enter_context(socket.socket(family, kind, protocol))
                reservation.setsockopt(socket.SOL_SOCKET, exclusive, 1)
                if family == socket.AF_INET6:
                    reservation.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                reservation.bind(address)
        return bool(seen)
    except (OSError, ValueError):
        return False

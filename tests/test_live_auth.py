from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import pytest

from execweave.live import (
    _AUTHENTICATED_LIVE_HTML,
    _LiveState,
    _LocalThreadingHTTPServer,
    _handler_factory,
    run_live,
)


def test_live_handler_requires_token_for_all_evidence_routes(tmp_path: Path) -> None:
    state = _LiveState("s1", tmp_path / "events.jsonl")
    token = "secret-token"
    server = _LocalThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(state, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        for path in ("/", "/graph.json", "/live.json?after=-1", "/final"):
            with pytest.raises(HTTPError) as exc_info:
                urlopen(base + path, timeout=1)
            assert exc_info.value.code == 401

        with pytest.raises(HTTPError) as exc_info:
            urlopen(Request(base + "/graph.json", headers={"X-ExecWeave-Token": "wrong"}), timeout=1)
        assert exc_info.value.code == 401

        with urlopen(base + "/?t=secret-token", timeout=1) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert "X-ExecWeave-Token" in html

        request = Request(base + "/graph.json", headers={"X-ExecWeave-Token": token})
        with urlopen(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["session_id"] == "s1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_client_reset_during_live_response_is_a_clean_disconnect(tmp_path: Path) -> None:
    state = _LiveState("disconnect", tmp_path / "events.jsonl")
    token = "disconnect-token"

    class RecordingServer(_LocalThreadingHTTPServer):
        unexpected: list[tuple[type[BaseException], BaseException]] = []

        def handle_error(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
            error_type, error, _ = sys.exc_info()
            if error_type is not None and error is not None and not isinstance(
                error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
            ):
                self.unexpected.append((error_type, error))
            super().handle_error(request, client_address)

    server = RecordingServer(("127.0.0.1", 0), _handler_factory(state, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(8):
            client = socket.create_connection(server.server_address, timeout=2)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256)
            client.sendall(
                f"GET /?t={token} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
            )
            # Winsock exposes ``linger`` as two unsigned shorts; POSIX uses two
            # ints. Supplying the four-byte Winsock layout to Linux/macOS is an
            # invalid socket option even though the reset behavior is portable.
            linger_format = "HH" if os.name == "nt" else "ii"
            client.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_LINGER,
                struct.pack(linger_format, 1, 0),
            )
            client.close()
        time.sleep(0.25)
        assert server.unexpected == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_live_viewer_bootstrap_keeps_token_in_memory_and_uses_headers() -> None:
    """The token is read once, erased from the URL, and sent as a header.

    v0.7.9 keeps authentication on the live evidence channel and nothing else:
    completion no longer fetches or renders a separate ``/final`` document, so the
    authenticated page a reader ends on is the one they were already looking at.
    """
    assert "new URLSearchParams(location.search).get('t')" in _AUTHENTICATED_LIVE_HTML
    assert "history.replaceState(null,'',location.pathname)" in _AUTHENTICATED_LIVE_HTML
    assert "'X-ExecWeave-Token':liveAuthToken" in _AUTHENTICATED_LIVE_HTML

    assert "fetch('/final'" not in _AUTHENTICATED_LIVE_HTML
    assert "location.href='/final'" not in _AUTHENTICATED_LIVE_HTML
    assert "document.write(" not in _AUTHENTICATED_LIVE_HTML


def test_run_live_announces_token_but_does_not_persist_it(tmp_path: Path) -> None:
    announced = threading.Event()
    observed: dict[str, object] = {}

    def announce(url: str) -> None:
        observed["url"] = url
        announced.set()

    def worker() -> None:
        try:
            observed["result"] = run_live(
                [sys.executable, "-c", "import time; time.sleep(0.35)"],
                watch_root=tmp_path,
                output_dir=tmp_path / "live-auth-run",
                poll_interval=0.05,
                collect_filesystem=False,
                collect_network=False,
                port=0,
                open_browser=False,
                linger_seconds=0.05,
                announce=announce,
            )
        except BaseException as exc:
            observed["error"] = exc
            announced.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    assert announced.wait(timeout=5)
    if "error" in observed:
        raise observed["error"]  # type: ignore[misc]

    authenticated_url = str(observed["url"])
    parsed = urlsplit(authenticated_url)
    values = parse_qs(parsed.query).get("t", [])
    assert len(values) == 1 and values[0]
    token = values[0]
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    request = Request(base + "live.json?after=-1", headers={"X-ExecWeave-Token": token})
    with urlopen(request, timeout=1) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["kind"] == "snapshot"

    thread.join(timeout=8)
    assert not thread.is_alive()
    if "error" in observed:
        raise observed["error"]  # type: ignore[misc]

    result = observed["result"]
    assert result.live_url == base  # type: ignore[union-attr]
    assert "?t=" not in result.to_dict()["live_url"]  # type: ignore[union-attr]
    for artifact in (
        result.event_stream,  # type: ignore[union-attr]
        result.graph,  # type: ignore[union-attr]
        result.viewer,  # type: ignore[union-attr]
    ):
        assert token not in artifact.read_text(encoding="utf-8")

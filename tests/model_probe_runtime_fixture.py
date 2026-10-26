"""Hermetic server child: positive catalog tests must really start a new endpoint."""
from __future__ import annotations

import socket
import sys
from pathlib import Path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def owned_server_command(tmp_path: Path, *, payload: dict, model: str,
                         endpoint: str | None = None) -> list[str]:
    script = tmp_path / ('server-' + str(free_port()) + '.py')
    config = {'payload': payload, 'model': model, 'endpoint': endpoint}
    script.write_text('CONFIG = ' + repr(config) + '\n' + r'''
import json, os, socketserver, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

endpoint = urlsplit(CONFIG['endpoint'] or os.environ['OLLAMA_HOST'])
class Server(HTTPServer):
    def server_bind(self):
        # No external getfqdn lookup in this loopback-only fixture.
        socketserver.TCPServer.server_bind(self)
        self.server_name = 'localhost'
        self.server_port = self.server_address[1]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        payload = json.dumps(CONFIG['payload']).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

with Server((endpoint.hostname, endpoint.port), Handler) as server:
    server.timeout = .05
    deadline = time.monotonic() + 8
    sidecar = Path(os.environ['EXECWEAVE_SEMANTIC_SIDECAR'])
    while time.monotonic() < deadline:
        server.handle_request()
        if sidecar.exists():
            try:
                records = [json.loads(line) for line in sidecar.read_text().splitlines()]
            except (ValueError, OSError):
                continue
            if any(r.get('target', {}).get('name') == CONFIG['model'] for r in records):
                break
    else:
        raise SystemExit('owned server catalog was not captured')
''', encoding='utf-8')
    return [sys.executable, str(script)]

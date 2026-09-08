"""Bounded native HTTP acceptance worker; copied outside the checkout by its launcher."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


WORKLOAD = r'''
from pathlib import Path
import socket, threading, time
root=Path(__file__).parent
limit=time.monotonic()+45
while not (root/'release.signal').exists() and time.monotonic()<limit: time.sleep(.05)
with socket.socket() as server:
    server.bind(('127.0.0.1',0)); server.listen(); server.settimeout(5)
    def respond():
        try:
            connection,_=server.accept()
            with connection: connection.recv(16);connection.sendall(b'ok')
        except OSError: pass
    thread=threading.Thread(target=respond,daemon=True);thread.start()
    with socket.create_connection(server.getsockname(),timeout=5) as client:
        client.sendall(b'hello');client.recv(16)
    thread.join(timeout=5)
for i in range(6):
    p=root/f'observed-{i}.txt';p.write_text(str(i));p.read_text();time.sleep(.15)
print('WORKLOAD_COMPLETE',flush=True)
'''


def native_probe(browser, cli: Path, out: Path, export_and_decode) -> dict:
    work = out / 'work'
    work.mkdir()
    (work / 'agent.py').write_text(WORKLOAD, encoding='utf-8')
    run = out / 'live-run'
    command = [str(cli), 'live', '--watch-root', str(work), '--output-dir', str(run),
               '--interval', '.05', '--linger', '20', '--port', '0', '--', sys.executable,
               '-u', str(work / 'agent.py')]
    lines = []
    proc = subprocess.Popen(command, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    def consume():
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    page = None
    try:
        deadline = time.monotonic() + 25
        url = None
        while time.monotonic() < deadline:
            match = re.search(r'http://127\.0\.0\.1:\d+/\?t=[A-Za-z0-9_-]+', ''.join(lines))
            if match:
                url = match.group(0)
                break
            if proc.poll() is not None:
                break
            time.sleep(.05)
        assert url, 'no authenticated live URL found'
        parsed = urllib.parse.urlsplit(url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        token = urllib.parse.parse_qs(parsed.query)['t'][0]
        try:
            urllib.request.urlopen(origin + '/live.json?after=-1', timeout=5)
            raise AssertionError('unauthenticated live.json was accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 401
        request = urllib.request.Request(origin + '/live.json?after=-1', headers={'X-ExecWeave-Token': token})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        errors, requests = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
        page.on('request', lambda req: requests.append(urllib.parse.urlsplit(req.url).path))
        page.goto(url)  # True product server, no interception/fulfillment.
        page.wait_for_selector('.node')
        assert not urllib.parse.urlsplit(page.url).query, 'token remained in browser URL'
        (work / 'release.signal').write_text('go', encoding='utf-8')
        page.wait_for_function("document.getElementById('status').textContent.includes('FINISHED')", timeout=30000)
        page.wait_for_timeout(1000)
        polls = requests.count('/live.json')
        page.wait_for_timeout(1200)
        assert requests.count('/live.json') == polls, 'polling continued after finish'
        assert '/final' not in requests
        live_graph = page.evaluate('window.__execweaveCore.getGraph()')
        (out / 'completed-live-graph.json').write_text(json.dumps(live_graph, indent=2), encoding='utf-8')
        live_ids = sorted(n['id'] for n in live_graph['nodes'])
        result = {'live': export_and_decode(page, out / 'native-live'), 'live_nodes': live_ids,
                  'auth_401': True, 'header_auth_200': True, 'token_removed': True, 'polling_stopped': True}
        assert (run / 'viewer.html').is_file() and (run / 'graph.json').is_file()
        page.goto((run / 'viewer.html').as_uri())
        page.wait_for_selector('.node')
        reopened = page.evaluate('window.__execweaveCore.getGraph()')
        (out / 'reopened-graph.json').write_text(json.dumps(reopened, indent=2), encoding='utf-8')
        assert sorted(n['id'] for n in reopened['nodes']) == live_ids
        for kind in ('nodes', 'edges'):
            assert sorted(reopened[kind], key=lambda row: row['id']) == sorted(live_graph[kind], key=lambda row: row['id']), f'{kind} final evidence differs'
        result['reopened'] = export_and_decode(page, out / 'native-reopened')
        assert not errors, errors
        result['js_errors'] = errors
        proc.wait(timeout=35)
        assert proc.returncode == 0
        return result
    finally:
        # The bounded workload is ours; release its wait even on a browser failure.
        (work / 'release.signal').write_text('cleanup', encoding='utf-8')
        if page:
            page.close()
        try:
            proc.wait(timeout=40)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        reader.join(timeout=2)
        log = re.sub(r'([?&]t=)[A-Za-z0-9_-]+', r'\1REDACTED', ''.join(lines))
        (out / 'native-cli.log').write_text(log, encoding='utf-8')


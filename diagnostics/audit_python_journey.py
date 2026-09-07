"""Native plain-Python OS evidence audit, deliberately without semantic hooks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import psutil
from playwright.sync_api import sync_playwright


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / ".execweave-acceptance" / "python-audit" / uuid4().hex[:8]
    work, run = out / "workspace 空白", out / "run"
    work.mkdir(parents=True)
    marker = "EW-PYTHON-" + uuid4().hex[:8].upper()
    code = """
import socket, threading, time
from pathlib import Path
print('READY', flush=True)
while not Path('continue.signal').exists(): time.sleep(.1)
path = Path('acceptance.txt')
path.write_text(MARKER, encoding='utf-8')
assert path.read_text(encoding='utf-8') == MARKER
with socket.socket() as server:
    server.bind(('127.0.0.1',0)); server.listen()
    def receive():
        peer, _ = server.accept()
        with peer:
            assert peer.recv(4096).decode() == MARKER
            time.sleep(2)
            peer.sendall(b'OK')
    worker = threading.Thread(target=receive); worker.start()
    with socket.create_connection(server.getsockname()) as client:
        client.sendall(MARKER.encode()); assert client.recv(2) == b'OK'
    worker.join()
print(MARKER + '-DONE', flush=True)
time.sleep(4)
""".replace("MARKER", repr(marker))
    # Keep synthetic command text out of the expected semantic evidence: the OS
    # process node legitimately includes argv, but that is not an observed prompt.
    argv = [
        str(Path(sys.executable).parent / ("execweave.exe" if os.name == "nt" else "execweave")),
        "live",
        "--watch-root",
        str(work),
        "--output-dir",
        str(run),
        "--linger",
        "3",
        "--",
        sys.executable,
        "-u",
        "-c",
        code,
    ]
    result: dict = {"marker": marker, "status": "FAIL", "console_errors": []}
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    text: list[str] = []
    owned: dict[int, float] = {}
    stop = threading.Event()
    proc = subprocess.Popen(
        argv,
        cwd=work,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    owned[proc.pid] = psutil.Process(proc.pid).create_time()

    def collect():
        with (out / "execweave.log").open("w", encoding="utf-8") as log:
            for line in proc.stdout:
                text.append(line)
                log.write(line)
                log.flush()

    def track():
        while not stop.wait(0.05):
            for pid, created in list(owned.items()):
                try:
                    parent = psutil.Process(pid)
                    if parent.create_time() == created:
                        for child in parent.children(recursive=True):
                            owned[child.pid] = child.create_time()
                except psutil.Error:
                    pass

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    tracker = threading.Thread(target=track, daemon=True)
    tracker.start()
    try:
        deadline = time.monotonic() + 25
        match = None
        while time.monotonic() < deadline:
            match = re.search(r"ExecWeave live: (http://\S+)", "".join(text))
            if match and "READY" in "".join(text):
                break
            if proc.poll() is not None:
                raise RuntimeError("ExecWeave exited before provider readiness")
            time.sleep(0.1)
        assert match, "live URL unavailable"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            try:
                page = browser.new_page(viewport={"width": 1366, "height": 768})
                page.on("pageerror", lambda error: result["console_errors"].append(str(error)))
                page.goto(match.group(1))
                page.wait_for_selector(".node")
                result["initial_nodes"] = page.locator(".node").count()
                page.screenshot(path=str(out / "00-start.png"))
                (work / "continue.signal").touch()
                page.wait_for_function(
                    "n => document.querySelectorAll('.node').length > n",
                    arg=result["initial_nodes"],
                    timeout=15000,
                )
                result["grown_nodes"] = page.locator(".node").count()
                page.screenshot(path=str(out / "01-live-growth.png"))
                result["exit_code"] = proc.wait(timeout=30)
                page.goto((run / "viewer.html").as_uri())
                page.wait_for_selector(".node")
                graph = json.loads((run / "graph.json").read_text(encoding="utf-8"))
                result["node_types"] = sorted({node["type"] for node in graph["nodes"]})
                events = [
                    json.loads(line)
                    for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()
                    if line
                ]
                result["event_types"] = sorted({event.get("event_type", "") for event in events})
                result["file_content_correct"] = (work / "acceptance.txt").read_text(
                    encoding="utf-8"
                ) == marker
                result["semantic_present"] = (run / "semantic.jsonl").exists() and (
                    run / "semantic.jsonl"
                ).stat().st_size > 0
                result["actual_clicks"] = []
                result["unrendered_raw_ids"] = []
                for kind in ("process", "file", "network_endpoint"):
                    candidate = next(
                        (node for node in graph["nodes"] if node["type"] == kind), None
                    )
                    assert candidate, f"missing {kind} graph evidence"
                    target = page.locator(
                        ".node[data-id=" + json.dumps(candidate["id"], ensure_ascii=False) + "]"
                    )
                    if target.count():
                        target.click(timeout=5000)
                        assert page.locator("#details").inner_text().strip()
                        result["actual_clicks"].append(kind)
                    else:
                        result["unrendered_raw_ids"].append(candidate["id"])
                result["rendered_node_clicks"] = []
                for target in page.locator(".node").all():
                    target.click(timeout=5000)
                    detail_text = page.locator("#details").inner_text()
                    assert detail_text.strip()
                    result["rendered_node_clicks"].append(
                        {
                            "id": target.get_attribute("data-id"),
                            "label": target.text_content(),
                            "details": detail_text[:2000],
                        }
                    )
                page.screenshot(path=str(out / "02-finished.png"))
                assert not result["semantic_present"], "plain Python unexpectedly emitted semantics"
                assert result["file_content_correct"] and result["exit_code"] == 0
                assert not result["console_errors"]
                result["status"] = "PASS"
            finally:
                browser.close()
    except Exception as error:
        result["failure"] = f"{type(error).__name__}: {error}"
    finally:
        stop.set()
        tracker.join(timeout=2)
        remaining = []
        for pid, created in reversed(list(owned.items())):
            try:
                child = psutil.Process(pid)
                if child.create_time() == created and child.is_running():
                    child.terminate()
                    remaining.append(child)
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(remaining, timeout=3)
        for child in alive:
            try:
                child.kill()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=3)
        result["remaining_owned"] = [child.pid for child in alive]
        if alive:
            result["status"] = "FAIL"
        reader.join(timeout=3)
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(out), **result}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

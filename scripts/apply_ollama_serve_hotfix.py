from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one guarded match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


collector = Path("src/execweave/collector.py")
replace_once(
    collector,
    "import psutil\n\nfrom .auto_specialized import (",
    "import psutil\n\nfrom . import __version__\nfrom .auto_specialized import (",
)
replace_once(
    collector,
    '''            attributes={
                "command": command,
                "cwd": str(self.watch_root),
                "backend": self.backend_name,
            },''',
    '''            attributes={
                "command": command,
                "cwd": str(self.watch_root),
                "backend": self.backend_name,
                "execweave_version": __version__,
            },''',
)
replace_once(
    collector,
    '                attributes={"collector_pid": os.getpid(), "backend": self.backend_name},',
    '''                attributes={
                    "collector_pid": os.getpid(),
                    "backend": self.backend_name,
                    "execweave_version": __version__,
                },''',
)
old_run = '''        process: subprocess.Popen[bytes] | None = None
        return_code = 1
        post_command_probe = prepare_post_command_specialized_probe(command)
        try:
            with auto_specialized_launch(command, server_relay=True) as launch_environment:
                process = subprocess.Popen(
                    launch_command,
                    cwd=str(self.watch_root),
                    env=launch_environment,
                )
                root = psutil.Process(process.pid)
                snapshot = _safe_process_snapshot(root)
                if snapshot is not None:
                    self._record_process_start(snapshot, parent=session, relation="LAUNCHED")

                with auto_specialized_probe(command):
                    while process.poll() is None:
                        self._sample_process_tree(root)
                        time.sleep(self.poll_interval)

                    self._sample_process_tree(root)
                    self._mark_disappeared_processes(set())
                return_code = int(process.returncode or 0)
            run_post_command_specialized_probe(
                post_command_probe,
                return_code=return_code,
            )
            return return_code
        finally:'''
new_run = '''        process: subprocess.Popen[bytes] | None = None
        return_code = 1
        interrupted = False
        post_command_probe = prepare_post_command_specialized_probe(command)
        try:
            try:
                with auto_specialized_launch(
                    command,
                    server_relay=True,
                ) as launch_environment:
                    process = subprocess.Popen(
                        launch_command,
                        cwd=str(self.watch_root),
                        env=launch_environment,
                    )
                    root = psutil.Process(process.pid)
                    snapshot = _safe_process_snapshot(root)
                    if snapshot is not None:
                        self._record_process_start(snapshot, parent=session, relation="LAUNCHED")

                    with auto_specialized_probe(command):
                        while process.poll() is None:
                            self._sample_process_tree(root)
                            time.sleep(self.poll_interval)

                        self._sample_process_tree(root)
                        self._mark_disappeared_processes(set())
                    return_code = int(process.returncode or 0)
            except KeyboardInterrupt:
                interrupted = True
                return_code = 130
                if process is not None:
                    self._terminate_process_tree(process)
            if not interrupted:
                run_post_command_specialized_probe(
                    post_command_probe,
                    return_code=return_code,
                )
            return return_code
        finally:'''
replace_once(collector, old_run, new_run)
replace_once(
    collector,
    '''                    attributes={
                        "return_code": return_code,
                        "root_pid": process.pid if process is not None else None,
                        "backend": self.backend_name,
                    },''',
    '''                    attributes={
                        "return_code": return_code,
                        "root_pid": process.pid if process is not None else None,
                        "backend": self.backend_name,
                        "interrupted": interrupted,
                        "execweave_version": __version__,
                    },''',
)
replace_once(
    collector,
    "    def _sample_process_tree(self, root: psutil.Process) -> None:\n",
    '''    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
        descendants: list[psutil.Process] = []
        try:
            root = psutil.Process(process.pid)
            descendants = root.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

        for child in reversed(descendants):
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

        if descendants:
            _, alive = psutil.wait_procs(descendants, timeout=2.0)
            for child in alive:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                return
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass

    def _sample_process_tree(self, root: psutil.Process) -> None:
''',
)

auto_specialized = Path("src/execweave/auto_specialized.py")
replace_once(
    auto_specialized,
    "import socket\nimport threading",
    "import socket\nimport sys\nimport threading",
)
old_bind = '''    try:
        server = ExecWeaveHTTPProxyServer(
            (listen_host, listen_port),
            ProxyConfig(upstream=upstream, sidecar=sidecar, mode="ollama"),
            recorder=_record_ollama_inference_exchange,
        )
    except OSError:
        # Fail open: preserve the child command's normal bind/error behavior.
        yield environment
        return
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name="execweave-ollama-serve-relay",
        daemon=True,
    )
    thread.start()
    environment["OLLAMA_HOST"] = upstream
'''
new_bind = '''    server: ExecWeaveHTTPProxyServer | None = None
    last_bind_error: OSError | None = None
    for attempt in range(5):
        try:
            server = ExecWeaveHTTPProxyServer(
                (listen_host, listen_port),
                ProxyConfig(upstream=upstream, sidecar=sidecar, mode="ollama"),
                recorder=_record_ollama_inference_exchange,
            )
            break
        except OSError as exc:
            last_bind_error = exc
            if attempt < 4:
                time.sleep(0.05)
    if server is None:
        public_endpoint = f"http://{listen_host}:{listen_port}"
        raise RuntimeError(
            "ExecWeave could not reserve the Ollama endpoint "
            f"{public_endpoint} for transparent conversation capture. "
            "Stop any existing Ollama server using that endpoint or set "
            "OLLAMA_HOST to a free loopback port before starting "
            "`execweave live -- ollama serve`."
        ) from last_bind_error
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name="execweave-ollama-serve-relay",
        daemon=True,
    )
    thread.start()
    environment["OLLAMA_HOST"] = upstream
    print(
        "ExecWeave Ollama relay: "
        f"http://{listen_host}:{listen_port} -> {upstream}",
        file=sys.stderr,
    )
'''
replace_once(auto_specialized, old_bind, new_bind)

strace = Path("src/execweave/strace_backend.py")
replace_once(
    strace,
    "            with auto_specialized_launch(command) as launch_environment:",
    '''            with auto_specialized_launch(
                command,
                server_relay=True,
            ) as launch_environment:''',
)

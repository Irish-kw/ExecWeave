from __future__ import annotations

import threading
from dataclasses import dataclass

import psutil


@dataclass(frozen=True, order=True, slots=True)
class ProcessIdentity:
    """PID plus creation time, so PID reuse never grants ownership."""

    pid: int
    create_time: float


@dataclass(frozen=True, slots=True)
class CleanupReport:
    terminated: tuple[ProcessIdentity, ...]
    killed: tuple[ProcessIdentity, ...]
    remaining: tuple[ProcessIdentity, ...]


def identity_for_pid(pid: int) -> ProcessIdentity | None:
    """Capture a process identity if the PID currently exists and is readable."""

    try:
        process = psutil.Process(int(pid))
        return ProcessIdentity(process.pid, process.create_time())
    except (psutil.Error, OSError, ValueError):
        return None


def identity_is_alive(identity: ProcessIdentity) -> bool:
    """Return True only when the same process instance still owns the PID."""

    process = _matching_process(identity)
    return process is not None and process.is_running()


def _matching_process(identity: ProcessIdentity) -> psutil.Process | None:
    try:
        process = psutil.Process(identity.pid)
        if process.create_time() != identity.create_time:
            return None
        return process
    except (psutil.Error, OSError, ValueError):
        return None


class OwnedProcessTracker:
    """Track only explicitly seeded process trees and clean them up with bounds.

    A background scan records descendant PID/create-time identities while their
    parents are alive. Once an orphaned child has been observed, it remains owned
    even after the parent exits. Cleanup never adopts a process by executable name,
    command line, or a reused PID.
    """

    def __init__(self, *, poll_interval: float = 0.05) -> None:
        self._poll_interval = max(0.01, float(poll_interval))
        self._owned: set[ProcessIdentity] = set()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def track_pid(self, pid: int) -> ProcessIdentity:
        identity = identity_for_pid(pid)
        if identity is None:
            raise ProcessLookupError(f"process {pid} is not available")
        self.track_identity(identity)
        return identity

    def track_identity(self, identity: ProcessIdentity) -> None:
        with self._lock:
            self._owned.add(identity)

    def identities(self) -> tuple[ProcessIdentity, ...]:
        with self._lock:
            return tuple(sorted(self._owned))

    def is_tracked(self, pid: int) -> bool:
        with self._lock:
            return any(identity.pid == int(pid) for identity in self._owned)

    def scan_once(self) -> None:
        with self._lock:
            seeds = tuple(self._owned)
        discovered: set[ProcessIdentity] = set()
        for identity in seeds:
            parent = _matching_process(identity)
            if parent is None:
                continue
            try:
                children = parent.children(recursive=True)
            except psutil.Error:
                continue
            for child in children:
                try:
                    discovered.add(ProcessIdentity(child.pid, child.create_time()))
                except psutil.Error:
                    continue
        if discovered:
            with self._lock:
                self._owned.update(discovered)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.scan_once()
        self._thread = threading.Thread(
            target=self._track_loop,
            name="execweave-owned-process-tracker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))

    def _track_loop(self) -> None:
        while not self._stop.wait(self._poll_interval):
            self.scan_once()

    def cleanup(
        self,
        *,
        grace_seconds: float = 0.25,
        terminate_timeout: float = 2.0,
        kill_timeout: float = 2.0,
    ) -> CleanupReport:
        """Bound cleanup to matching owned identities; never wait indefinitely."""

        self.scan_once()
        self.stop()
        alive = self._matching_owned_processes()
        if alive and grace_seconds > 0:
            _, alive = psutil.wait_procs(alive, timeout=max(0.0, grace_seconds))

        terminated: list[ProcessIdentity] = []
        terminate_targets: list[psutil.Process] = []
        for process in alive:
            identity = self._owned_identity_for_process(process)
            if identity is None:
                continue
            try:
                process.terminate()
            except psutil.Error:
                continue
            terminated.append(identity)
            terminate_targets.append(process)

        alive_after_terminate: list[psutil.Process] = []
        if terminate_targets:
            _, alive_after_terminate = psutil.wait_procs(
                terminate_targets,
                timeout=max(0.0, terminate_timeout),
            )

        killed: list[ProcessIdentity] = []
        kill_targets: list[psutil.Process] = []
        for process in alive_after_terminate:
            identity = self._owned_identity_for_process(process)
            if identity is None:
                continue
            try:
                process.kill()
            except psutil.Error:
                continue
            killed.append(identity)
            kill_targets.append(process)

        if kill_targets:
            psutil.wait_procs(kill_targets, timeout=max(0.0, kill_timeout))

        remaining = tuple(
            identity
            for identity in self.identities()
            if identity_is_alive(identity)
        )
        return CleanupReport(
            terminated=tuple(sorted(set(terminated))),
            killed=tuple(sorted(set(killed))),
            remaining=remaining,
        )

    def _matching_owned_processes(self) -> list[psutil.Process]:
        processes: list[psutil.Process] = []
        for identity in self.identities():
            process = _matching_process(identity)
            if process is not None and process.is_running():
                processes.append(process)
        return processes

    def _owned_identity_for_process(
        self, process: psutil.Process
    ) -> ProcessIdentity | None:
        try:
            identity = ProcessIdentity(process.pid, process.create_time())
        except psutil.Error:
            return None
        with self._lock:
            return identity if identity in self._owned else None

"""Exercise Winsock admission without turning unknown or occupied ports into PASS."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import execweave.auto_specialized as auto
import execweave.runtime_endpoint_availability as availability


class Reservation:
    def __init__(self, log, fail=None):
        self.log, self.fail = log, fail
    def __enter__(self):
        self.log.append('open')
        return self
    def __exit__(self, *args):
        self.log.append('close')
    def setsockopt(self, *args):
        self.log.append(('option', args))
    def bind(self, address):
        self.log.append(('bind', address))
        if self.fail:
            raise self.fail


def winsock(monkeypatch, *, occupied=False, hosts=('127.0.0.1', '::1')):
    log = []
    sockets = []
    def make(*args):
        sock = Reservation(log, OSError('occupied') if occupied else None)
        sockets.append(sock)
        return sock
    fake = SimpleNamespace(SO_EXCLUSIVEADDRUSE=123, SOL_SOCKET=1, SOCK_STREAM=1,
                           IPPROTO_TCP=6, IPPROTO_IPV6=41, IPV6_V6ONLY=26,
                           AF_INET=2, AF_INET6=10, socket=make,
                           getaddrinfo=lambda *a, **k: [(10 if ':' in h else 2, 1, 6, '',
                              (h, 12345, 0, 0) if ':' in h else (h, 12345)) for h in hosts])
    monkeypatch.setattr(availability, 'socket', fake)
    monkeypatch.setattr(availability, 'sys', SimpleNamespace(platform='win32'))
    return log, sockets


def test_all_addresses_exclusively_reserved_together_and_released(monkeypatch):
    log, sockets = winsock(monkeypatch)
    assert availability.windows_exclusive_endpoint_available('localhost', 12345)
    assert len(sockets) == 2
    assert log.count(('option', (1, 123, 1))) == 2
    assert ('option', (41, 26, 1)) in log
    assert log[-2:] == ['close', 'close']
    assert log.index(('bind', ('::1', 12345, 0, 0))) < log.index('close')


def test_occupied_bind_is_not_taken_over(monkeypatch):
    log, _ = winsock(monkeypatch, occupied=True)
    assert not availability.windows_exclusive_endpoint_available('localhost', 12345)
    assert log[-1] == 'close'


@pytest.mark.parametrize('hosts', [(), ('192.0.2.1',), ('127.0.0.1', '192.0.2.2')])
def test_empty_or_non_loopback_resolution_abstains_and_releases(monkeypatch, hosts):
    log, _ = winsock(monkeypatch, hosts=hosts)
    assert not availability.windows_exclusive_endpoint_available('localhost', 12345)
    assert log.count('open') == log.count('close')


def test_duplicate_resolution_does_not_conflict_with_own_reservation(monkeypatch):
    _, sockets = winsock(monkeypatch, hosts=('127.0.0.1', '127.0.0.1'))
    assert availability.windows_exclusive_endpoint_available('localhost', 12345)
    assert len(sockets) == 1


def test_non_windows_does_not_attempt_a_windows_bind(monkeypatch):
    _, sockets = winsock(monkeypatch)
    monkeypatch.setattr(availability, 'sys', SimpleNamespace(platform='linux'))
    assert not availability.windows_exclusive_endpoint_available('127.0.0.1', 12345)
    assert not sockets


@pytest.mark.parametrize('error', [PermissionError('denied'), OSError('unavailable')])
def test_resolution_or_bind_error_never_authorizes(monkeypatch, error):
    winsock(monkeypatch)
    def fail(*a, **k):
        raise error
    monkeypatch.setattr(availability.socket, 'getaddrinfo', fail)
    assert not availability.windows_exclusive_endpoint_available('localhost', 12345)


@pytest.mark.parametrize('bind_proven', [True, False])
def test_connect_timeout_requires_independent_bind_proof(monkeypatch, tmp_path, bind_proven):
    monkeypatch.setenv('EXECWEAVE_SEMANTIC_SIDECAR', str(tmp_path/'semantic.jsonl'))
    monkeypatch.setenv('OLLAMA_HOST', '127.0.0.1:12345')
    def timeout(*a, **k):
        raise TimeoutError('refusal not delivered within connect deadline')
    monkeypatch.setattr(auto.socket, 'create_connection', timeout)
    calls = []
    def prove(host, port):
        calls.append((host, port))
        return bind_proven
    monkeypatch.setattr(auto, 'windows_exclusive_endpoint_available', prove)
    assert (auto.prepare_live_specialized_probe(['ollama', 'serve']).spec is not None) == bind_proven
    assert calls == [('127.0.0.1', 12345)]


def test_permission_error_never_uses_timeout_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv('EXECWEAVE_SEMANTIC_SIDECAR', str(tmp_path/'semantic.jsonl'))
    def denied(*a, **k):
        raise PermissionError('denied')
    monkeypatch.setattr(auto.socket, 'create_connection', denied)
    monkeypatch.setattr(auto, 'windows_exclusive_endpoint_available',
                        lambda *a: pytest.fail('permission failure must not be bypassed'))
    assert auto.prepare_live_specialized_probe(['ollama', 'serve']).spec is None

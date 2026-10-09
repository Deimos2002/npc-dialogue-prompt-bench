"""Test-wide guards.

protocol: no model call in CI. Every test runs with network sockets disabled, so any
accidental provider call fails loudly instead of spending money. Only connections to a
literal loopback address are allowed: asyncio's event loop wakes itself through one on
Windows, and in-process ASGI test clients need an event loop. DNS is always blocked.
"""

import socket

import pytest


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a network connection."""


_LOOPBACK = frozenset({"127.0.0.1", "::1"})
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _blocked(*args, **kwargs):
    raise NetworkBlockedError("Network access is disabled in tests (protocol).")


def _is_loopback(address) -> bool:
    return isinstance(address, tuple) and address[0] in _LOOPBACK


def _connect(self, address):
    if not _is_loopback(address):
        _blocked()
    return _real_connect(self, address)


def _connect_ex(self, address):
    if not _is_loopback(address):
        _blocked()
    return _real_connect_ex(self, address)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)

import socket

import pytest

from tests.conftest import NetworkBlockedError


def test_opening_a_connection_fails():
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("example.com", 443), timeout=1)


def test_dns_lookup_fails():
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.com", 443)


def test_connecting_to_an_external_address_fails_even_without_dns():
    with socket.socket() as sock, pytest.raises(NetworkBlockedError):
        sock.connect(("93.184.216.34", 443))

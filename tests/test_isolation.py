"""Tests for test isolation, environment sandboxing, and loopback socket allowances."""
import asyncio
import socket

import pytest


def test_outside_socket_connect_is_blocked():
    """Connecting to a non-loopback address raises RuntimeError."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="network access is not allowed in tests"):
            s.connect(("203.0.113.1", 80))
    finally:
        s.close()


def test_outside_create_connection_is_blocked():
    """socket.create_connection to a non-loopback address raises RuntimeError."""
    with pytest.raises(RuntimeError, match="network access is not allowed in tests"):
        socket.create_connection(("203.0.113.1", 80), timeout=1.0)


def test_socketpair_works():
    """socket.socketpair() succeeds because it connects over loopback."""
    s1, s2 = socket.socketpair()
    try:
        s1.sendall(b"ping")
        data = s2.recv(4)
        assert data == b"ping"
    finally:
        s1.close()
        s2.close()


def test_asyncio_sleep_works():
    """asyncio event loop works cleanly without being blocked by network guard."""
    asyncio.run(asyncio.sleep(0))


def test_provider_and_key_env_removed_for_every_test():
    """conftest strips PLANOGRAM_PROVIDER and GEMINI_API_KEY so the shell cannot change test results."""
    import os

    assert "PLANOGRAM_PROVIDER" not in os.environ
    assert "GEMINI_API_KEY" not in os.environ

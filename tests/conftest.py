import ipaddress
import socket
from pathlib import Path

import pytest

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    h = str(host).strip().lower()
    if h in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "live: marks tests that make live network calls")


@pytest.fixture(autouse=True)
def isolate_environment_and_block_network(monkeypatch, request):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    if request.node.get_closest_marker("live") is None:
        orig_connect = socket.socket.connect
        orig_create_connection = socket.create_connection

        def patched_connect(self, address, *args, **kwargs):
            host = address[0] if isinstance(address, tuple) and len(address) >= 1 else None
            if not is_loopback(host):
                raise RuntimeError("network access is not allowed in tests")
            return orig_connect(self, address, *args, **kwargs)

        def patched_create_connection(address, *args, **kwargs):
            host = address[0] if isinstance(address, tuple) and len(address) >= 1 else None
            if not is_loopback(host):
                raise RuntimeError("network access is not allowed in tests")
            return orig_create_connection(address, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", patched_connect)
        monkeypatch.setattr(socket, "create_connection", patched_create_connection)

from planogram_agent.data_loader import load_dataset
from planogram_agent.graph import build_graph

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="session")
def dataset():
    return load_dataset(DATA)


@pytest.fixture(scope="session")
def graph_data(dataset):
    return dataset.graph


@pytest.fixture(scope="session")
def G(graph_data):
    return build_graph(graph_data)

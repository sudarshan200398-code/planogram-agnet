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
    monkeypatch.delenv("PLANOGRAM_PROVIDER", raising=False)
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


import sys


class FakeGenaiContext:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.calls = []

    def make_modules(self):
        ctx = self

        class FakeHttpOptions:
            def __init__(self, timeout=None):
                self.timeout = timeout

        class FakeConfig:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeModels:
            def generate_content(self, model, contents, config):
                ctx.call_count += 1
                ctx.calls.append({"model": model, "contents": contents, "config": config})
                if not ctx.responses:
                    raise RuntimeError("No more scripted fake genai responses")
                resp = ctx.responses.pop(0)
                if isinstance(resp, Exception):
                    raise resp
                if isinstance(resp, type) and issubclass(resp, Exception):
                    raise resp("Scripted error")

                class FakeResponse:
                    text = str(resp)

                return FakeResponse()

        class FakeClient:
            def __init__(self, api_key=None, http_options=None):
                self.api_key = api_key
                self.http_options = http_options
                self.models = FakeModels()

        import types as py_types

        fake_genai = py_types.ModuleType("google.genai")
        fake_genai.Client = FakeClient

        fake_types = py_types.ModuleType("google.genai.types")
        fake_types.HttpOptions = FakeHttpOptions
        fake_types.GenerateContentConfig = FakeConfig
        fake_genai.types = fake_types

        fake_google = py_types.ModuleType("google")
        fake_google.genai = fake_genai

        return fake_google, fake_genai, fake_types


@pytest.fixture
def fake_genai_env(monkeypatch):
    def _setup(responses):
        ctx = FakeGenaiContext(responses)
        fake_google, fake_genai, fake_types = ctx.make_modules()
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
        return ctx

    return _setup

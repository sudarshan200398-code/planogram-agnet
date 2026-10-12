from pathlib import Path

import pytest

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

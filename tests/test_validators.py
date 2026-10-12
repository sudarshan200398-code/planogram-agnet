"""Validators must accept the sample data and catch deliberately broken data."""
import pytest
from pydantic import ValidationError

from planogram_agent.data_loader import load_dataset
from planogram_agent.schemas import (Connector, Edge, GraphData, Node,
                                     PlanogramEntry, StockItem)
from planogram_agent.validators import (DataValidationError, assert_valid,
                                        validate_graph_data,
                                        validate_inventory,
                                        validate_planogram)


def clone(gd: GraphData, **changes) -> GraphData:
    return gd.model_copy(update=changes, deep=True)


def test_sample_data_is_valid(dataset):
    assert validate_graph_data(dataset.graph) == []
    assert validate_planogram(dataset.planogram, dataset.products, dataset.graph) == []
    assert validate_inventory(dataset.inventory, dataset.products) == []


def test_load_dataset_validates(tmp_path, dataset):
    assert len(dataset.products) == len(dataset.planogram) == len(dataset.inventory)


def test_duplicate_node_id(graph_data):
    bad = clone(graph_data, nodes=graph_data.nodes + [graph_data.nodes[0]])
    assert any("duplicate node ids" in i for i in validate_graph_data(bad))


def test_edge_to_unknown_node(graph_data):
    bad = clone(graph_data, edges=graph_data.edges + [Edge(a="L1_ENTRANCE", b="NOPE")])
    assert any("unknown node NOPE" in i for i in validate_graph_data(bad))


def test_walk_edge_crossing_floors(graph_data):
    bad = clone(graph_data, edges=graph_data.edges + [Edge(a="L1_PRODUCE", b="L2_TOYS")])
    assert any("crosses floors" in i for i in validate_graph_data(bad))


def test_self_loop_and_duplicate_edge(graph_data):
    e0 = graph_data.edges[0]
    bad = clone(graph_data, edges=graph_data.edges + [Edge(a="L1_PRODUCE", b="L1_PRODUCE"),
                                                       Edge(a=e0.b, b=e0.a)])
    issues = validate_graph_data(bad)
    assert any("self loop" in i for i in issues)
    assert any("duplicate edge" in i for i in issues)


def test_zero_distance_rejected_by_schema():
    with pytest.raises(ValidationError):
        Edge(a="a", b="b", distance=0)
    with pytest.raises(ValidationError):
        Edge(a="a", b="b", distance=-3)


def test_orphan_node_is_unreachable(graph_data):
    orphan = Node(id="L1_ORPHAN", floor=1, x=1, y=1, type="zone_front", label="Orphan")
    bad = clone(graph_data, nodes=graph_data.nodes + [orphan])
    assert any("L1_ORPHAN is not reachable" in i for i in validate_graph_data(bad))


def test_disconnected_floor_when_connectors_removed(graph_data):
    bad = clone(graph_data, connectors=[])
    issues = validate_graph_data(bad)
    assert any("L2_TOYS is not reachable" in i for i in issues)


def test_connector_same_floor(graph_data):
    bad = clone(graph_data, connectors=graph_data.connectors + [
        Connector(a="L1_ESC", b="L1_ELV", type="escalator", cost=5, accessible=False)])
    assert any("both ends on floor" in i for i in validate_graph_data(bad))


def test_connector_node_type_mismatch(graph_data):
    bad = clone(graph_data, connectors=[
        Connector(a="L1_ESC", b="L2_ELV", type="escalator", cost=15, accessible=False)])
    assert any("expected escalator" in i for i in validate_graph_data(bad))


def test_accessible_mode_needs_an_accessible_connector(graph_data):
    only_stairs = [c for c in graph_data.connectors if c.type.value != "elevator"]
    bad = clone(graph_data, connectors=only_stairs)
    assert any("accessible-only" in i for i in validate_graph_data(bad))


def test_node_out_of_bounds(graph_data):
    n = graph_data.nodes[0].model_copy(update={"id": "FAR", "x": 999})
    bad = clone(graph_data, nodes=graph_data.nodes + [n])
    assert any("outside map bounds" in i for i in validate_graph_data(bad))


def test_node_on_unknown_floor(graph_data):
    n = graph_data.nodes[0].model_copy(update={"id": "F9", "floor": 9})
    bad = clone(graph_data, nodes=graph_data.nodes + [n])
    assert any("floor 9" in i for i in validate_graph_data(bad))


def test_no_entrance(graph_data):
    nodes = [n.model_copy(update={"type": "junction"}) if n.type.value == "entrance" else n
             for n in graph_data.nodes]
    assert validate_graph_data(clone(graph_data, nodes=nodes)) == ["no entrance node defined"]


def test_planogram_unknown_node_and_sku(dataset):
    base = dataset.planogram[0]
    bad = [base.model_copy(update={"node_id": "NOPE", "position": 90}),
           base.model_copy(update={"sku": "NO-SKU", "position": 91})]
    issues = validate_planogram(bad, dataset.products, dataset.graph)
    assert any("unknown node NOPE" in i for i in issues)
    assert any("NO-SKU not in product table" in i for i in issues)


def test_planogram_floor_mismatch_and_junction(dataset):
    base = dataset.planogram[0]
    wrong_floor = base.model_copy(update={"floor": 2, "position": 90})
    on_junction = base.model_copy(update={"node_id": "L1_B1", "position": 91})
    issues = validate_planogram([wrong_floor, on_junction], dataset.products, dataset.graph)
    assert any("but node" in i for i in issues)
    assert any("junction" in i for i in issues)


def test_planogram_slot_collision(dataset):
    e = dataset.planogram[0]
    issues = validate_planogram([e, e], dataset.products, dataset.graph)
    assert any("share slot" in i for i in issues)


def test_planogram_schema_bounds():
    with pytest.raises(ValidationError):
        PlanogramEntry(sku="x", floor=1, zone="z", bay="E", shelf_level=1, position=1, node_id="n")
    with pytest.raises(ValidationError):
        PlanogramEntry(sku="x", floor=1, zone="z", bay="A", shelf_level=9, position=1, node_id="n")


def test_inventory_unknown_and_duplicate(dataset):
    sku = dataset.products[0].sku
    issues = validate_inventory([StockItem(sku="GHOST", quantity=1),
                                 StockItem(sku=sku, quantity=1),
                                 StockItem(sku=sku, quantity=2)], dataset.products)
    assert any("unknown sku GHOST" in i for i in issues)
    assert any("duplicate sku" in i for i in issues)


def test_assert_valid_raises():
    with pytest.raises(DataValidationError) as exc:
        assert_valid(["a problem"])
    assert exc.value.issues == ["a problem"]
    assert_valid([])  # no raise


def test_load_dataset_raises_on_corrupt_data(tmp_path):
    import shutil
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "data"
    for f in src.iterdir():
        if f.is_file():
           shutil.copy(f, tmp_path / f.name)
    lines = (tmp_path / "planogram.csv").read_text().splitlines()
    lines[1] = lines[1].rsplit(",", 1)[0] + ",NOT_A_NODE"
    (tmp_path / "planogram.csv").write_text("\n".join(lines) + "\n")
    with pytest.raises(DataValidationError):
        load_dataset(tmp_path)

"""Generate Store 2, "Riverside Market": a synthetic two-floor store with its own layout and products.

Deterministic: the same files are written on every run (fixed seed, fixed order). The output must
pass the existing validators (data_loader.load_dataset(..., validate=True)).

Usage (PowerShell, from the repo root):
    python scripts/generate_store_riverside.py                 # writes data/store_riverside
    python scripts/generate_store_riverside.py --out some\\dir
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_store_prices import write_prices  # noqa: E402

STORE_ID = "riverside"
SEED = 20261016
BOUNDS = {"width": 80, "height": 50}
FLOORS = [1, 2]
GRID_X = [10, 25, 40, 55, 70]
GRID_Y = [12, 25, 38]
CONNECTOR_COST = {"escalator": 15, "stairs": 25, "elevator": 30}
CONNECTOR_ACCESSIBLE = {"escalator": False, "stairs": False, "elevator": True}

# (label, node type, x, y, junction x, junction y) per floor
SPURS = {
    1: [
        ("Main Doors", "entrance", 40, 47, 40, 38),
        ("Front Tills", "checkout", 58, 47, 55, 38),
        ("Fresh Market", "zone_front", 10, 4, 10, 12),
        ("Bakehouse", "zone_front", 25, 4, 25, 12),
        ("Butcher Counter", "zone_front", 40, 4, 40, 12),
        ("Fishmonger", "zone_front", 55, 4, 55, 12),
        ("Chilled Foods", "zone_front", 77, 12, 70, 12),
        ("Frozen Hall", "zone_front", 77, 25, 70, 25),
        ("Pantry Aisle A", "aisle", 15, 31, 10, 25),
        ("Pantry Aisle B", "aisle", 30, 31, 25, 25),
        ("Pantry Aisle C", "aisle", 45, 31, 40, 25),
        ("Pantry Aisle D", "aisle", 60, 31, 55, 25),
        ("Escalator Hall", "escalator", 3, 38, 10, 38),
        ("East Stairs", "stairs", 77, 38, 70, 38),
        ("Lift Lobby", "elevator", 25, 46, 25, 38),
    ],
    2: [
        ("Home and Garden", "zone_front", 10, 4, 10, 12),
        ("Electronics Corner", "zone_front", 25, 4, 25, 12),
        ("Kids Zone", "zone_front", 40, 4, 40, 12),
        ("Pharmacy", "zone_front", 55, 4, 55, 12),
        ("Pet Supplies", "zone_front", 77, 12, 70, 12),
        ("Fashion Floor", "zone_front", 77, 25, 70, 25),
        ("Books and Stationery", "zone_front", 15, 31, 10, 25),
        ("Customer Desk", "zone_front", 45, 31, 40, 25),
        ("Escalator Hall", "escalator", 3, 38, 10, 38),
        ("East Stairs", "stairs", 77, 38, 70, 38),
        ("Lift Lobby", "elevator", 25, 46, 25, 38),
    ],
}

# zone label -> list of (category, category code, brands, nouns, sizes)
CATALOGUE = {
    "Fresh Market": [
        ("Fruit", "FRU", ["Riverbend", "Tulsi Grove"], ["Alphonso Mango", "Royal Gala Apple", "Robusta Banana"], ["1 kg", "500 g"]),
        ("Vegetables", "VEG", ["Riverbend", "Tulsi Grove"], ["Baby Spinach", "Red Onion", "Cherry Tomato"], ["1 kg", "250 g"]),
        ("Herbs", "HRB", ["Greenleaf Co", "Tulsi Grove"], ["Fresh Coriander", "Curry Leaves", "Mint Bunch"], ["100 g", "50 g"]),
    ],
    "Bakehouse": [
        ("Breads", "BRD", ["Oakhill", "Copperpot"], ["Multigrain Loaf", "Pav Buns", "Garlic Focaccia"], ["400 g", "6 pack"]),
        ("Pastries", "PST", ["Oakhill", "Copperpot"], ["Almond Croissant", "Cinnamon Swirl", "Veg Puff"], ["single", "4 pack"]),
    ],
    "Butcher Counter": [
        ("Poultry", "POU", ["Kaveri", "Harbour Line"], ["Chicken Breast", "Chicken Drumsticks", "Chicken Mince"], ["500 g", "1 kg"]),
        ("Lamb and Mutton", "LMB", ["Kaveri", "Harbour Line"], ["Mutton Curry Cut", "Lamb Chops", "Mutton Keema"], ["500 g", "1 kg"]),
    ],
    "Fishmonger": [
        ("Fish", "FSH", ["Bluefin Bay", "Harbour Line"], ["Rohu Steaks", "Seer Fish Fillet", "Pomfret Whole"], ["500 g", "1 kg"]),
        ("Prawns and Shellfish", "PRW", ["Bluefin Bay", "Harbour Line"], ["Tiger Prawns", "Crab Meat", "Squid Rings"], ["250 g", "500 g"]),
    ],
    "Chilled Foods": [
        ("Paneer and Curd", "PNR", ["Marigold Farm", "Vanya"], ["Malai Paneer", "Set Curd", "Greek Yoghurt"], ["200 g", "400 g"]),
        ("Butter and Ghee", "GHE", ["Marigold Farm", "Vanya"], ["Cow Ghee", "Salted Butter", "Cultured Butter"], ["200 g", "500 g"]),
        ("Juices", "JUI", ["Sunpeak", "Vanya"], ["Orange Juice", "Guava Nectar", "Mixed Fruit Juice"], ["1 L", "200 ml"]),
    ],
    "Frozen Hall": [
        ("Frozen Snacks", "FRZ", ["Monsoon", "Kestrel"], ["Aloo Tikki", "Veg Spring Rolls", "Chicken Nuggets"], ["400 g", "1 kg"]),
        ("Ice Cream", "ICE", ["Monsoon", "Kestrel"], ["Kesar Pista Kulfi", "Belgian Chocolate Tub", "Mango Sorbet"], ["500 ml", "1 L"]),
    ],
    "Pantry Aisle A": [
        ("Rice and Grains", "RIC", ["Saffron Lane", "Kaveri"], ["Basmati Rice", "Sona Masoori Rice", "Brown Rice"], ["1 kg", "5 kg"]),
        ("Breakfast Cereals", "CER", ["Sunpeak", "Northgate"], ["Rolled Oats", "Corn Flakes", "Ragi Flakes"], ["500 g", "1 kg"]),
    ],
    "Pantry Aisle B": [
        ("Atta and Flours", "ATT", ["Saffron Lane", "Northgate"], ["Whole Wheat Atta", "Besan Flour", "Ragi Flour"], ["1 kg", "5 kg"]),
        ("Pulses and Dals", "DAL", ["Saffron Lane", "Northgate"], ["Toor Dal", "Moong Dal", "Masoor Dal"], ["500 g", "1 kg"]),
    ],
    "Pantry Aisle C": [
        ("Spices and Masalas", "SPC", ["Monsoon", "Saffron Lane"], ["Garam Masala", "Turmeric Powder", "Kashmiri Chilli"], ["100 g", "200 g"]),
        ("Cooking Oils", "OIL", ["Kaveri", "Sunpeak"], ["Groundnut Oil", "Mustard Oil", "Sunflower Oil"], ["1 L", "5 L"]),
    ],
    "Pantry Aisle D": [
        ("Tea and Coffee", "TEA", ["Northgate", "Monsoon"], ["Assam Tea", "Filter Coffee", "Masala Chai"], ["250 g", "500 g"]),
        ("Biscuits", "BIS", ["Oakhill", "Northgate"], ["Butter Cookies", "Digestive Biscuits", "Nankhatai"], ["200 g", "400 g"]),
    ],
    "Home and Garden": [
        ("Cookware", "CKW", ["Copperpot", "Lumen"], ["Cast Iron Tawa", "Pressure Cooker", "Steel Kadai"], ["medium", "large"]),
        ("Garden Tools", "GDN", ["Greenleaf Co", "Lumen"], ["Hand Trowel", "Watering Can", "Pruning Shears"], ["standard", "pro"]),
    ],
    "Electronics Corner": [
        ("Phone Accessories", "PHN", ["Lumen", "Kestrel"], ["USB C Cable", "Power Bank", "Wireless Earbuds"], ["standard", "premium"]),
        ("Small Appliances", "APL", ["Lumen", "Kestrel"], ["Electric Kettle", "Hand Blender", "Pop Up Toaster"], ["standard", "deluxe"]),
    ],
    "Kids Zone": [
        ("Toys", "TOY", ["Tinytoes", "Kestrel"], ["Wooden Puzzle", "Building Blocks", "Toy Train Set"], ["small", "large"]),
        ("Baby Care", "BAB", ["Tinytoes", "Vanya"], ["Baby Wipes", "Diaper Rash Cream", "Baby Lotion"], ["small", "large"]),
    ],
    "Pharmacy": [
        ("Pain Relief", "PAI", ["Vanya", "Northgate"], ["Pain Relief Balm", "Muscle Spray", "Heat Patch"], ["small", "large"]),
        ("Vitamins", "VIT", ["Vanya", "Sunpeak"], ["Vitamin C Tablets", "Multivitamin Capsules", "Omega 3 Softgels"], ["30 pack", "60 pack"]),
    ],
    "Pet Supplies": [
        ("Dog Food", "DOG", ["Pebble Pet", "Harbour Line"], ["Puppy Kibble", "Adult Dog Kibble", "Dog Treat Sticks"], ["1 kg", "3 kg"]),
        ("Cat Food", "CAT", ["Pebble Pet", "Bluefin Bay"], ["Kitten Kibble", "Tuna Cat Pouch", "Cat Litter"], ["1 kg", "3 kg"]),
    ],
    "Fashion Floor": [
        ("Menswear", "MEN", ["Northgate", "Kestrel"], ["Linen Shirt", "Cotton Kurta", "Chino Trousers"], ["M", "L"]),
        ("Womenswear", "WMN", ["Vanya", "Tulsi Grove"], ["Cotton Saree", "Printed Kurti", "Palazzo Pants"], ["M", "L"]),
    ],
    "Books and Stationery": [
        ("Notebooks", "NTB", ["Inkwell", "Oakhill"], ["Ruled Notebook", "Spiral Sketchbook", "Graph Notebook"], ["A5", "A4"]),
        ("Pens and Markers", "PEN", ["Inkwell", "Kestrel"], ["Gel Pens", "Highlighter Markers", "Fountain Pen"], ["5 pack", "10 pack"]),
    ],
    "Customer Desk": [
        ("Gift Vouchers", "GFT", ["Riverbend", "Inkwell"], ["Gift Voucher", "Festive Gift Card", "Birthday Gift Card"], ["500 value", "1000 value"]),
    ],
}

# Everyday staples, added after the catalogue above was first generated. They come after it in every
# list, so the existing products keep their skus, placements, stock and prices. Each category has its
# own code; a category may share its name with an existing one (they browse together).
STAPLES = {
    "Chilled Foods": [
        ("Milk", "MLK", ["Marigold Farm", "Vanya"], ["Full Cream Milk", "Toned Milk", "Skimmed Milk"], ["500 ml", "1 L"]),
        ("Eggs", "EGG", ["Riverbend", "Tulsi Grove"], ["Farm Eggs"], ["6 pack", "12 pack"]),
        ("Cheese", "CHS", ["Marigold Farm"], ["Cheddar Cheese", "Processed Cheese"], ["200 g"]),
        ("Water and Soft Drinks", "DRK", ["Riverbend", "Sunpeak"], ["Still Water"], ["1 L"]),
        ("Water and Soft Drinks", "SFT", ["Sunpeak", "Kestrel"], ["Cola Soft Drink", "Lime Soda"], ["750 ml"]),
    ],
    "Bakehouse": [
        ("Breads", "LOF", ["Oakhill", "Copperpot"], ["White Sandwich Bread", "Brown Bread"], ["400 g"]),
    ],
    "Fresh Market": [
        ("Vegetables", "POT", ["Riverbend"], ["Potatoes"], ["1 kg", "2 kg"]),
    ],
    "Pantry Aisle B": [
        ("Sugar and Salt", "SUG", ["Saffron Lane"], ["Fine Sugar"], ["1 kg", "5 kg"]),
        ("Sugar and Salt", "SLT", ["Northgate"], ["Iodised Salt"], ["1 kg"]),
        ("Atta and Flours", "WFL", ["Saffron Lane"], ["Chakki Wheat Flour"], ["5 kg", "10 kg"]),
    ],
    "Pantry Aisle C": [
        ("Cooking Oils", "COK", ["Kaveri", "Sunpeak"], ["Refined Cooking Oil"], ["1 L"]),
        ("Instant Noodles", "NDL", ["Monsoon", "Kestrel"], ["Instant Noodles"], ["70 g", "280 g"]),
    ],
    "Pantry Aisle D": [
        ("Chips and Snacks", "CHP", ["Monsoon", "Sunpeak"], ["Salted Potato Chips", "Masala Potato Chips"], ["50 g"]),
    ],
    "Home and Garden": [
        ("Laundry and Dishes", "DET", ["Lumen", "Greenleaf Co"], ["Detergent Powder"], ["1 kg"]),
        ("Laundry and Dishes", "DSH", ["Lumen", "Greenleaf Co"], ["Dish Wash Liquid"], ["500 ml"]),
        ("Paper and Bags", "GRB", ["Lumen"], ["Garbage Bags"], ["30 pack"]),
        ("Paper and Bags", "TIS", ["Greenleaf Co"], ["Facial Tissue Box", "Toilet Paper Rolls"], ["4 pack"]),
    ],
    "Pharmacy": [
        ("Personal Care", "SOP", ["Vanya", "Tulsi Grove"], ["Sandalwood Bath Soap"], ["4 pack"]),
        ("Personal Care", "SHM", ["Vanya", "Tulsi Grove"], ["Herbal Shampoo"], ["180 ml"]),
        ("Personal Care", "TTP", ["Vanya", "Tulsi Grove"], ["Herbal Toothpaste"], ["150 g"]),
    ],
    "Electronics Corner": [
        ("Batteries", "BAT", ["Lumen", "Kestrel"], ["AA Batteries", "AAA Batteries"], ["4 pack"]),
    ],
}
STAPLE_CODES = {code for categories in STAPLES.values() for _, code, *_ in categories}
STAPLES_OUT_OF_STOCK = {"RS-MLK-010", "RS-BAT-004"}  # a couple of staples sold out, on purpose

EXTRA_PLACEMENT_EVERY = 97  # every 97th product is also sold at the Front Tills


def _slug(label: str) -> str:
    return "".join(ch for ch in label.upper().replace(" ", "_") if ch.isalnum() or ch == "_")


# Other names shoppers use for a place, accepted as start points ("I'm at produce"). Only clear synonyms
# that name exactly one place and share no word with a product name, category or keyword
# (validators.validate_place_aliases checks this when the store loads). Places on both floors get none.
PLACE_ALIASES = {
    "Fresh Market": ["produce"],
    "Chilled Foods": ["dairy"],
    "Bakehouse": ["bakery"],
    "Front Tills": ["checkout", "tills"],
    "Main Doors": ["entrance"],
    "Customer Desk": ["customer service", "help desk"],
    "Butcher Counter": ["butcher"],
    "Pharmacy": ["chemist"],
    "Electronics Corner": ["electronics"],
    "Books and Stationery": ["stationery"],
    "Fashion Floor": ["clothing", "clothes"],
}


def _junction_id(floor: int, x: int, y: int) -> str:
    return f"RS{floor}_J{GRID_X.index(x) + 1}{GRID_Y.index(y) + 1}"


def build_graph() -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    for floor in FLOORS:
        for y in GRID_Y:
            for x in GRID_X:
                nodes.append({"id": _junction_id(floor, x, y), "floor": floor, "x": x, "y": y, "type": "junction",
                              "label": f"Walkway {GRID_X.index(x) + 1}{GRID_Y.index(y) + 1}"})
        for y in GRID_Y:
            for a, b in zip(GRID_X, GRID_X[1:]):
                edges.append({"a": _junction_id(floor, a, y), "b": _junction_id(floor, b, y)})
        for x in GRID_X:
            for a, b in zip(GRID_Y, GRID_Y[1:]):
                edges.append({"a": _junction_id(floor, x, a), "b": _junction_id(floor, x, b)})
        for label, ntype, x, y, jx, jy in SPURS[floor]:
            node_id = f"RS{floor}_{_slug(label)}"
            node = {"id": node_id, "floor": floor, "x": x, "y": y, "type": ntype, "label": label}
            if label in PLACE_ALIASES:
                node["aliases"] = PLACE_ALIASES[label]
            nodes.append(node)
            edges.append({"a": _junction_id(floor, jx, jy), "b": node_id})
    connectors = []
    for ctype, label in (("escalator", "Escalator Hall"), ("stairs", "East Stairs"), ("elevator", "Lift Lobby")):
        connectors.append({"a": f"RS1_{_slug(label)}", "b": f"RS2_{_slug(label)}", "type": ctype,
                           "cost": CONNECTOR_COST[ctype], "accessible": CONNECTOR_ACCESSIBLE[ctype]})
    return {"store_id": STORE_ID, "floors": FLOORS, "bounds": BOUNDS, "nodes": nodes, "edges": edges,
            "connectors": connectors}


def build_products() -> list[dict]:
    products = []
    for zone, categories in [*CATALOGUE.items(), *STAPLES.items()]:
        for category, code, brands, nouns, sizes in categories:
            n = 0
            for brand in brands:
                for noun in nouns:
                    for size in sizes:
                        n += 1
                        keywords = sorted({noun.lower(), noun.split()[-1].lower(), category.lower()})
                        products.append({
                            "sku": f"RS-{code}-{n:03d}",
                            "name": f"{brand} {noun} {size}",
                            "brand": brand,
                            "category": category,
                            "size": size,
                            "keywords": "|".join(keywords),
                            "zone": zone,
                        })
    return products


def build_planogram(products: list[dict], graph: dict) -> list[dict]:
    node_by_label = {(n["label"], n["floor"]): n for n in graph["nodes"] if n["type"] != "junction"}
    zone_node = {label: node for (label, _), node in node_by_label.items()}
    tills = node_by_label[("Front Tills", 1)]
    next_slot: dict[str, int] = {}
    rows = []

    def place(sku: str, node: dict) -> None:
        i = next_slot.get(node["id"], 0)
        next_slot[node["id"]] = i + 1
        bay = "ABCD"[i // 50 % 4]
        shelf = i // 10 % 5 + 1
        position = i % 10 + 1 + 10 * (i // 200)
        rows.append({"sku": sku, "floor": node["floor"], "zone": node["label"], "bay": bay,
                     "shelf_level": shelf, "position": position, "node_id": node["id"]})

    for idx, p in enumerate(products):
        place(p["sku"], zone_node[p["zone"]])
        if idx % EXTRA_PLACEMENT_EVERY == EXTRA_PLACEMENT_EVERY - 1:
            place(p["sku"], tills)
    return rows


def build_inventory(products: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    rows = []
    for p in products:
        qty = rng.randint(4, 90)
        if rng.random() < 0.03 or p["sku"] in STAPLES_OUT_OF_STOCK:
            qty = 0
        rows.append({"sku": p["sku"], "quantity": qty})
    return rows


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


README = """# Riverside Market (Store 2)

A **synthetic** two-floor store for testing multi-store support. Nothing here is real: the map,
products, brands, stock levels and prices are all made up. It is generated by
`scripts/generate_store_riverside.py` (fixed seed, same output on every run), so edit the script,
not these files.

| File | What it is | Size |
|---|---|---|
| `graph.json` | Walkways, zones and the floor links | {nodes} points, {edges} paths, {connectors} floor links |
| `products.csv` | Products (sku, name, brand, category, size, keywords) | {products} products |
| `planogram.csv` | Where each product sits (zone, bay, shelf, position) | {placements} placements |
| `inventory.csv` | Stock per product (0 means out of stock) | {out_of_stock} out of stock |
| `prices.csv` | Optional **synthetic** prices in rupees (sku, price), from the product rules in `config/price_ranges.json` | {products} prices |

**Floor 1:** Main Doors (entrance), Fresh Market, Bakehouse, Butcher Counter, Fishmonger, Chilled Foods,
Frozen Hall, Pantry Aisles A to D, Front Tills (checkout).
**Floor 2:** Home and Garden, Electronics Corner, Kids Zone, Pharmacy, Pet Supplies, Fashion Floor,
Books and Stationery, Customer Desk.
**Between floors:** Escalator Hall (escalator), East Stairs (stairs), Lift Lobby (step-free lift).

**Other names for places** ({aliases} in all, e.g. "produce" for Fresh Market, "dairy" for Chilled Foods)
are the optional `aliases` on places in `graph.json`, from the generator's `PLACE_ALIASES`. Shoppers can
use them as a start point ("milk and eggs, I'm at produce"). Each must name exactly one place and share no
word with a product, which the data validator checks when the store loads.

**Everyday staples** ({staples} products: milk, eggs, bread, cheese, sugar, salt, cooking oil, noodles,
chips, water, soft drinks, cleaning, personal care, batteries and more) are in the generator's `STAPLES`
list. They come after the original catalogue, so the earlier products keep their skus, shelves, stock
and prices. `tests/test_staples.py` checks every staple can be found by name.

Node ids start with `RS1_` / `RS2_` and skus with `RS-`, so they never collide with the Central Store.
"""


def generate(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = build_graph()
    products = build_products()
    planogram = build_planogram(products, graph)
    inventory = build_inventory(products)

    (out_dir / "graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    _write_csv(out_dir / "products.csv", ["sku", "name", "brand", "category", "size", "keywords"], products)
    _write_csv(out_dir / "planogram.csv", ["sku", "floor", "zone", "bay", "shelf_level", "position", "node_id"], planogram)
    _write_csv(out_dir / "inventory.csv", ["sku", "quantity"], inventory)
    write_prices(out_dir / "products.csv", out_dir / "prices.csv")  # rules in config/price_ranges.json
    counts = {
        "nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "connectors": len(graph["connectors"]),
        "products": len(products), "placements": len(planogram),
        "out_of_stock": sum(r["quantity"] == 0 for r in inventory),
        "staples": sum(p["sku"].split("-")[1] in STAPLE_CODES for p in products),
        "aliases": sum(len(n.get("aliases", [])) for n in graph["nodes"]),
    }
    (out_dir / "README.md").write_text(README.format(**counts), encoding="utf-8", newline="\n")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic Riverside Market store.")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data" / "store_riverside")
    args = parser.parse_args()
    print(f"wrote {args.out}: {generate(args.out)}")


if __name__ == "__main__":
    main()

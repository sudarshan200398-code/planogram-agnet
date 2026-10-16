"""Export the API contract for the web app: web/openapi.json and recorded responses in web/src/api/fixtures/.

The fixtures are real responses from the FastAPI app (TestClient, no network, AI model off), made
deterministic: every request sends a fixed X-Request-ID, session ids are renumbered in order of
appearance, and Retry-After is fixed. tests/test_web_contract.py fails if these files are stale.

Regenerate (PowerShell, repo root):
    $env:PLANOGRAM_PROVIDER='none'; python scripts/export_web_contract.py; npm --prefix web run gen:api
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

OPENAPI_FILE = ROOT / "web" / "openapi.json"
FIXTURE_DIR = ROOT / "web" / "src" / "api" / "fixtures"
FIXED_RETRY_AFTER = "60"
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def _require_model_off() -> None:
    value = os.environ.get("PLANOGRAM_PROVIDER")
    if value is None:
        os.environ["PLANOGRAM_PROVIDER"] = "none"
    elif value.strip().lower() != "none":
        raise SystemExit("Run the exporter with PLANOGRAM_PROVIDER=none (the AI model must be off).")


def _dump(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


class _Sessions:
    """Renumber real session ids (UUIDs) as session-001, session-002, ... in order of appearance."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    def normalise(self, data):
        text = json.dumps(data, ensure_ascii=False)

        def name(m: re.Match) -> str:
            return self.names.setdefault(m.group(0), f"session-{len(self.names) + 1:03d}")

        return json.loads(_UUID.sub(name, text))


def _first_single_place(dataset, floor: int) -> str:
    from planogram_agent.tools import check_inventory, get_location

    for p in sorted(dataset.products, key=lambda p: p.sku):
        locs = get_location(p.sku, dataset)
        if len(locs) == 1 and locs[0].floor == floor and check_inventory(p.sku, dataset) == "available":
            return p.sku
    raise LookupError(f"no single-place in-stock product on floor {floor}")


def build_contract() -> dict[str, str]:
    """Relative path -> file text for openapi.json and every fixture. Writes nothing."""
    _require_model_off()
    from fastapi.testclient import TestClient

    from api.main import create_app
    from planogram_agent.providers import LocalFilesProvider
    from planogram_agent.settings import load_settings

    files: dict[str, str] = {}
    sessions = _Sessions()
    provider = LocalFilesProvider()
    central, riverside = provider.load_dataset("central"), provider.load_dataset("riverside")
    first_category = sorted({p.category for p in central.products}, key=str.casefold)[0]

    with TestClient(create_app(provider=provider)) as client:
        files["openapi.json"] = _dump(client.get("/openapi.json").json())

        def record(name: str, method: str, path: str, body=None, query=None, client_=client) -> dict:
            headers = {"X-Request-ID": f"fixture-{name}"}
            resp = client_.request(method, path, json=body, params=query, headers=headers)
            kept = {}
            if "retry-after" in resp.headers:
                kept["retry-after"] = FIXED_RETRY_AFTER
            fixture = {
                "name": name,
                "request": {"method": method, "path": path, "query": query or {}, "body": body},
                "status": resp.status_code,
                "headers": kept,
                "body": resp.json(),
            }
            normalised = sessions.normalise(fixture)
            files[f"src/api/fixtures/{name}.json"] = _dump(normalised)
            return resp.json()

        record("stores", "GET", "/stores")
        record("categories_central", "GET", "/stores/central/categories")
        record("categories_riverside", "GET", "/stores/riverside/categories")
        record("products_central_page", "GET", "/stores/central/products",
               query={"category": first_category, "page": 1, "page_size": 4})
        record("products_central_page2", "GET", "/stores/central/products",
               query={"category": first_category, "page": 2, "page_size": 4})
        record("product_central_detail", "GET", "/stores/central/products/BAK-BAG-009")
        record("suggest_central_mi", "GET", "/stores/central/suggest", query={"q": "mi"})
        record("suggest_riverside_man", "GET", "/stores/riverside/suggest", query={"q": "man"})
        record("search_central_bagels", "POST", "/stores/central/search", {"text": "Daily Bake Plain Bagels 4 pack"})
        milk = record("search_central_milk", "POST", "/stores/central/search", {"text": "milk"})
        q = milk["question"]
        record("clarify_central_milk", "POST", "/stores/central/clarify",
               {"session_id": milk["session_id"], "item_index": q["item_index"], "sku": q["options"][0]["sku"]})
        record("search_central_sentence", "POST", "/stores/central/search", {"text": "milk, bread and crayons, I'm at produce"})
        record("search_central_out_of_stock", "POST", "/stores/central/search", {"text": "ArtBox Watercolour Paints 12 pack"})
        record("search_central_not_found", "POST", "/stores/central/search", {"text": "zzqx wobble gadget"})
        record("search_riverside_kibble", "POST", "/stores/riverside/search",
               {"text": "i am near the fresh market, Pebble Pet Puppy Kibble 1 kg"})
        record("basket_central_route", "POST", "/stores/central/basket/route",
               {"items": [{"sku": _first_single_place(central, 1), "qty": 2}, {"sku": _first_single_place(central, 2), "qty": 1}]})
        record("basket_riverside_route", "POST", "/stores/riverside/basket/route",
               {"items": [{"sku": _first_single_place(riverside, 1), "qty": 1}, {"sku": _first_single_place(riverside, 2), "qty": 3}]})
        record("error_store_not_found", "GET", "/stores/nope/categories")
        record("error_product_not_found", "GET", "/stores/central/products/NOPE-000")
        record("error_session_not_found", "POST", "/stores/central/clarify",
               {"session_id": "expired-session", "item_index": 0, "sku": "DAI-MIL-001"})
        record("error_text_too_long", "POST", "/stores/central/search", {"text": "a" * (load_settings().max_query_chars + 1)})

    limited = load_settings().model_copy(update={"api_rate_limit_per_minute": 1})
    with TestClient(create_app(provider=provider, settings=limited)) as busy:
        busy.get("/stores")
        record("error_rate_limited", "GET", "/stores", client_=busy)
    return files


def write_contract() -> list[str]:
    files = build_contract()
    for rel, text in files.items():
        path = ROOT / "web" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    stale = [p for p in FIXTURE_DIR.glob("*.json") if f"src/api/fixtures/{p.name}" not in files]
    for p in stale:
        p.unlink()
    return sorted(files)


if __name__ == "__main__":
    written = write_contract()
    print(f"wrote {len(written)} files under web/: openapi.json and {len(written) - 1} fixtures")

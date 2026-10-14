# Planogram Agent

Agentic product finder for a multi-floor store: given product requests, report
**availability** and the **shortest walking route** (across floors, with an
accessible-only mode).

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Repo, config, data chosen | done |
| 1 | Schemas, loaders, validators, 2-floor sample data | done |
| 2 | Graph builder, multi-floor router, accessible mode, route plots | done |
| 3 | Tools (`search_products`, `check_inventory`, `get_location`, `shortest_path`, `plan_route`) | next |
| 4+ | Matching, agents, orchestrator, verifier, multi-item routing, UI | planned |

## Run

    pip install -e ".[dev]"
    pytest                                              # tests
    python -m planogram_agent.cli L1_ENTRANCE L2_TOYS   # route in the terminal
    python -m planogram_agent.cli L1_ENTRANCE L2_TOYS --accessible
    python scripts/plot_route.py L1_ENTRANCE L2_TOYS docs/route.png

### Live Check with Gemini

To run the live check against the Gemini API (note: this script sends test sentences to Google):

    # Windows CMD
    set GEMINI_API_KEY=your_key_here
    python scripts\live_check.py

    # Windows PowerShell
    $env:GEMINI_API_KEY="your_key_here"
    python scripts\live_check.py

    # Linux / macOS
    export GEMINI_API_KEY="your_key_here"
    python scripts/live_check.py

Full redacted logs are saved to `reports/live_check_<YYYYMMDD_HHMMSS>.txt`.

## Web UI

Install the UI extra dependency:

    pip install -e ".[ui]"

Run the Streamlit application:

    streamlit run src/planogram_agent/ui/streamlit_app.py

## Data (data/)

- `graph.json`: nodes (floor, x, y, type), walk edges, and floor connectors
  (escalator, elevator, stairs, each with a cost and an `accessible` flag).
  Hand-digitised from the AI-generated two-floor map; **coordinates and
  distances are estimates in metres**, not measurements.
- `products.csv`, `planogram.csv`, `inventory.csv`: **synthetic**. The source
  planogram images have unreadable product text, so products were written by
  hand and placed in the zones, bays and shelf levels the images show.
- Inventory is a mock: a product is available when quantity > 0. Three items
  are deliberately out of stock to exercise the "not available" path.

## Design rules

1. Code holds the facts (availability, location, routes); agents only reason.
2. One graph for the whole building; floor changes are just weighted edges.
3. Data is validated on load and fails loudly (`validators.py`).

## Tests

- `test_validators.py`: good data passes, 20 kinds of broken data are caught.
- `test_router.py`: hand-checked routes, an independent Floyd-Warshall oracle
  over every node pair (normal and accessible-only), failure modes, step
  consistency.
- `test_properties.py`: hypothesis checks of symmetry, triangle inequality,
  endpoints.

Note: route costs are rounded to 2 decimals, so equal-cost alternatives can
produce different (equally short) paths in opposite directions.

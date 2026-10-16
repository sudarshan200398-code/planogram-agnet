# AGENTS.md: project rules for AI coding agents

## What this project is
A store product finder for a two-floor supermarket. A shopper types one or more products and the
system says whether each is available and gives the shortest walking route to it, across floors.
It is built as an agentic system. Requirements, high-level design and low-level design are in `docs/`.

## The one rule that matters
**Agents decide and phrase. Tools hold the facts.**
Availability, location, distance and route steps come only from deterministic tools that read the
store folder. An AI model must never produce a location, distance or stock level on its own.

## Existing code: do not rewrite it
`src/planogram_agent/` already has `schemas.py`, `data_loader.py`, `validators.py`, and
`graph/builder.py` and `graph/router.py`. Tests in `tests/` pass. Reuse these modules.
Before changing any existing file, say which file and why, and run the full test suite afterwards.
Never overwrite a file you have not read.

## Store data
- A store is one folder: `graph.json`, `products.csv`, `planogram.csv`, `inventory.csv`.
- Put nothing store-specific in code: no floor numbers, aisle names, node ids or product names.
- Data in `data/store_demo/` is synthetic. Swapping the folder must work with no code change.
- Always load data through `data_loader.load_dataset`, which runs the validators.

## Architecture to follow
Front end or Streamlit page -> FastAPI app in `api/` -> `StoreDataProvider` (store registry in
`config/stores.json`) -> `interface.run_query()` -> orchestrator -> agents -> tools -> store data.
The Streamlit page may still call `interface.run_query()` directly.
- Orchestrator: fixed steps (parse, match, check stock, locate, route, compose, verify).
- Agents: Query, Search, Availability, Routing, Verifier. Each returns a validated pydantic model.
- Tools: `search_products`, `check_inventory`, `get_location`, `resolve_start`, route tools.
- Every AI-model call has a schema check, one retry, and a non-AI fallback.
- The API talks to store data only through the `StoreDataProvider` interface, one cached engine per store.
- No voice input in the Python engine or API: they only receive text. Browser-side voice input on the
  front end is allowed and sends plain text to the API.
- No machine learning for routing.

## How to work
1. One phase at a time. Do not start a phase until the previous one's tests pass.
2. Write the plan first and wait for approval before large changes.
3. Write tests with the code. Deterministic parts (matching, routing, validators) get tests first.
4. Test the agent layer with a fake AI model client; tests must not call external services.
5. Keep changes small. Show a short summary of what changed and which tests ran.
6. If something is unclear, ask. Do not guess requirements.
7. For each new function or bug fix, write the test first, run it and show that it fails for the right reason, then implement, then run it and show that it passes.
8. Before a release or a commit that touches src/planogram_agent/matching.py, run pytest -m slow.
9. From now on, every output, number and text quoted in a report must come from a command you actually ran in this task. Never write sample output by hand.

## Code style
- Python 3.11+, type hints, pydantic v2 models, small functions, clear names.
- All thresholds and limits live in one config file, never inline.
- No secrets in code. Read keys from environment variables.

## Test queries
`tests/golden_queries.json` holds expected answers. A phase is not done if it breaks cases that
should already pass. Do not edit expected values to make tests pass; report the mismatch instead.

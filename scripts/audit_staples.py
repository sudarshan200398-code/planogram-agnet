"""Report which everyday staples each store can find by name (the list is in tests/staples.py).

Usage (PowerShell, from the repo root):  $env:PLANOGRAM_PROVIDER='none'; python scripts/audit_staples.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from planogram_agent.data_loader import load_dataset  # noqa: E402
from planogram_agent.settings import load_settings  # noqa: E402
from tests.staples import STAPLES, missing_staples  # noqa: E402

STORES = {"central": ROOT / "data" / "store_demo", "riverside": ROOT / "data" / "store_riverside"}


def main() -> None:
    settings = load_settings()
    for store, folder in STORES.items():
        missing = missing_staples(load_dataset(folder, validate=True), settings)
        print(f"{store}: {len(STAPLES) - len(missing)}/{len(STAPLES)} staples found; missing: {', '.join(missing) or 'none'}")


if __name__ == "__main__":
    main()

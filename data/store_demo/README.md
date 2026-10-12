# Final store data

One store, two floors. Every file below matches the same map (`store_map.png` is drawn from `graph.json`).
All products, brands and distances are synthetic.

| File | What it is | Size |
|---|---|---|
| `graph.json` | The map: walkable points, paths between them, and the escalator, elevator and stairs between floors | 53 points, 74 paths, 3 floor links |
| `products.csv` | The product list: sku, name, brand, category, size, keywords | 971 products |
| `planogram.csv` | Where each product sits: sku, floor, zone, bay, shelf level, position, map point | 974 rows (3 products are on two shelves) |
| `inventory.csv` | Stock per product: sku, quantity (0 = out of stock) | 971 rows, 35 out of stock |
| `store_map.png` | The map as a picture, for checking and for the demo | 2 floors |
| `golden_queries.json` | 85 test queries with the expected answers | 85 cases |

## How the files connect
`planogram.csv` links a product (`sku`) to a place on the map (`node_id`, which is a point in `graph.json`).
The router finds the shortest path to that point. `inventory.csv` says whether the product is available.

## Checks done
- The existing loader and validators accept the folder.
- Every shelf row points to a real map point on the correct floor.
- 15 zones have products across both floors. Only Restrooms has none; it is used as a start point.

## Load it
`load_dataset("final_data")` from `planogram_agent.data_loader` runs the validators.

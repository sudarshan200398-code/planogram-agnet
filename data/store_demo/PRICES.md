# Prices (optional)

`prices.csv` in this folder holds **synthetic** prices in rupees (`sku,price`). They are made up for
testing and demos, like the rest of the data here. The file is optional: without it the API returns
`price: null`.

It was written by `scripts/generate_store_prices.py`, which derives each price from the product's
sku and category, so re-running it gives the same file. None of the other files in this folder were
changed when it was added.

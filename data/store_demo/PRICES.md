# Prices (optional)

`prices.csv` in this folder holds **synthetic** prices in rupees (`sku,price`). They are made up for
testing and demos, like the rest of the data here. The file is optional: without it the API returns
`price: null`.

It is written by `scripts/generate_store_prices.py` from the product rules in
`config/price_ranges.json`: the first rule whose words appear in the product's name or keywords sets
a price band (never the merchandising category), the pack size scales it, and prices end in retail
style (whole rupees under 100, ...9 up to 999, ...99 from 1,000). Gift cards cost their face value.
Re-running the script gives the same file. None of the other files in this folder were changed when
it was added.

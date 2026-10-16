import { LOW_STOCK_MAX } from "../config";
import { formatLocation, formatPrice, initialsOf, stockLabel } from "./format";

it("formats rupees and hides missing prices", () => {
  expect(formatPrice(94)).toBe("₹94");
  expect(formatPrice(1099)).toBe("₹1,099");
  expect(formatPrice(41599)).toBe("₹41,599");
  expect(formatPrice(null)).toBeNull();
  expect(formatPrice(undefined)).toBeNull();
});

it("labels stock with the low-stock threshold from config", () => {
  expect(LOW_STOCK_MAX).toBe(5);
  expect(stockLabel("in_stock", 68)).toEqual({ tone: "ok", text: "In stock · 68" });
  expect(stockLabel("in_stock", 6)).toEqual({ tone: "ok", text: "In stock · 6" });
  expect(stockLabel("in_stock", 5)).toEqual({ tone: "warn", text: "Low stock · 5 left" });
  expect(stockLabel("in_stock", 1)).toEqual({ tone: "warn", text: "Low stock · 1 left" });
  expect(stockLabel("in_stock", 0)).toEqual({ tone: "bad", text: "Out of stock" });
  expect(stockLabel("out_of_stock", 0)).toEqual({ tone: "bad", text: "Out of stock" });
  expect(stockLabel("unknown", 0)).toEqual({ tone: "neutral", text: "Stock unknown" });
  expect(stockLabel(null, null)).toEqual({ tone: "neutral", text: "Stock unknown" });
});

it("writes the location from the known parts", () => {
  expect(formatLocation({ floor: 1, zone: "Bakery", bay: "A", shelf: 2 })).toBe("Level 1 · Bakery · Bay A · Shelf 2");
  expect(formatLocation({ floor: 2, zone: "Café", bay: null, shelf: null })).toBe("Level 2 · Café");
  expect(formatLocation({ floor: null, zone: null, bay: null, shelf: null })).toBeNull();
});

it("makes initials for the fallback tile", () => {
  expect(initialsOf("Daily Bake Plain Bagels 4 pack")).toBe("DB");
  expect(initialsOf("4 pack")).toBe("P");
  expect(initialsOf("")).toBe("?");
});

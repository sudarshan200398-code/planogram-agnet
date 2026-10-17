import { LOW_STOCK_MAX } from "../config";
import type { StockStatus } from "../api/types";

const rupees = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2, minimumFractionDigits: 0 });

/** "₹94", "₹1,099"; null when the store has no price for the product. */
export function formatPrice(price: number | null | undefined): string | null {
  return typeof price === "number" ? rupees.format(price) : null;
}

export type StockTone = "ok" | "warn" | "bad" | "neutral";

/** Stock badge wording; the tone is never the only signal (text and icon always go with it). */
export function stockLabel(status: StockStatus | null | undefined, count: number | null | undefined): { tone: StockTone; text: string } {
  if (status === "out_of_stock" || (status === "in_stock" && count === 0)) return { tone: "bad", text: "Out of stock" };
  if (status === "in_stock" && typeof count === "number") {
    return count <= LOW_STOCK_MAX ? { tone: "warn", text: `Low stock · ${count} left` } : { tone: "ok", text: `In stock · ${count}` };
  }
  if (status === "in_stock") return { tone: "ok", text: "In stock" };
  return { tone: "neutral", text: "Stock unknown" };
}

/** "Level 1 · Bakery · Bay A · Shelf 2" from whichever parts are known. */
export function formatLocation(loc: { floor?: number | null; zone?: string | null; bay?: string | null; shelf?: number | null }): string | null {
  const parts = [
    loc.floor != null ? `Level ${loc.floor}` : null,
    loc.zone ?? null,
    loc.bay ? `Bay ${loc.bay}` : null,
    loc.shelf != null ? `Shelf ${loc.shelf}` : null,
  ].filter((p): p is string => Boolean(p));
  return parts.length ? parts.join(" · ") : null;
}

/** Up to two letters for the fallback image tile. */
export function initialsOf(name: string): string {
  const words = name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w));
  return (words.slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?").slice(0, 2);
}

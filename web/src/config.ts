/** Every threshold and limit the web app uses, in one place. */

/** Base URL of the SuperFind API. In development Vite proxies /api to the local API. */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") || "/api";

/** "Low stock" badge at this many units or fewer (the API reports counts, not a low-stock flag). */
export const LOW_STOCK_MAX = 5;

/** Suggestions: wait this long after typing stops, and need at least this many characters. */
export const SUGGEST_DEBOUNCE_MS = 250;
export const SUGGEST_MIN_CHARS = 2;

/** Shopping list limits, matching the API (max_items 20, quantity 1 to 99). */
export const LIST_MAX_ITEMS = 20;
export const QTY_MIN = 1;
export const QTY_MAX = 99;

/** Longest search text the API accepts (max_query_chars). */
export const SEARCH_MAX_CHARS = 500;

/** localStorage keys. */
export const STORAGE_KEYS = {
  store: "superfind.store",
  theme: "superfind.theme",
  list: (storeId: string) => `superfind.list.${storeId}`,
} as const;

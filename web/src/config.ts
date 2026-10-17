/** Every threshold and limit the web app uses, in one place. */

import { resolveApiBase } from "./lib/apiBase";

export { resolveApiBase };

const apiBase = resolveApiBase(import.meta.env.VITE_API_BASE_URL as string | undefined, import.meta.env.PROD);
/** Base URL of the SuperFind API; empty when misconfigured (see API_CONFIG_ERROR). */
export const API_BASE_URL: string = apiBase.url;
export const API_CONFIG_ERROR: string | null = apiBase.error;

/**
 * Slow API: the free host sleeps when idle and its first answer can take 30 to 60 seconds. After
 * SLOW_REQUEST_MS a "waking up" message shows; a request gives up after REQUEST_TIMEOUT_MS; the store
 * list is tried STORES_RETRIES more time(s) before an error shows.
 */
export const SLOW_REQUEST_MS = 4_000;
export const REQUEST_TIMEOUT_MS = 75_000;
export const STORES_RETRIES = 1;

/** "Low stock" badge at this many units or fewer (the API reports counts, not a low-stock flag). */
export const LOW_STOCK_MAX = 5;

/** Suggestions: wait this long after typing stops, and need at least this many characters. */
export const SUGGEST_DEBOUNCE_MS = 250;
export const SUGGEST_MIN_CHARS = 2;

/** Category browsing: quick chips shown on the home screen, and products per page. */
export const QUICK_CATEGORY_COUNT = 10;
export const BROWSE_PAGE_SIZE = 20;

/** Shopping list limits, matching the API (max_items 20, quantity 1 to 99). */
export const LIST_MAX_ITEMS = 20;
export const TOAST_MS = 4000; // how long a confirmation stays on screen
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

// Kept free of import.meta.env so vite.config.ts can use the same check at build time.

/**
 * Where the SuperFind API is, from VITE_API_BASE_URL (set at build time). In development an unset value
 * means /api, which Vite proxies to the local API. In a production build it must be set: an unset or
 * malformed value is an error (shown on screen by main.tsx; vite.config.ts also stops the build), so the
 * app never silently calls the wrong host.
 */
export function resolveApiBase(raw: string | undefined, production: boolean): { url: string; error: string | null } {
  const value = raw?.trim().replace(/\/+$/, "") ?? "";
  if (!value) {
    return production
      ? { url: "", error: "VITE_API_BASE_URL is not set. Set it to the API's https address and build again." }
      : { url: "/api", error: null };
  }
  if (!/^https?:\/\/[^/\s]+/i.test(value)) {
    return { url: "", error: `VITE_API_BASE_URL must be an http(s) address, like https://api.example.com (got "${value}").` };
  }
  return { url: value, error: null };
}

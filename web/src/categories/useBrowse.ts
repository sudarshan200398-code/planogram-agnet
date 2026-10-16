import { useCallback, useEffect, useRef, useState } from "react";
import { api, isAbort } from "../api/client";
import type { Product } from "../api/types";
import { BROWSE_PAGE_SIZE } from "../config";

export type BrowseState =
  | { status: "idle" }
  | { status: "loading"; category: string }
  | { status: "done"; category: string; items: Product[]; page: number; pages: number; total: number; loadingMore: boolean }
  | { status: "error"; category: string; error: unknown };

/** GET /products?category= for the store, page by page ("Show more"). */
export function useBrowse(storeId: string | null) {
  const [state, setState] = useState<BrowseState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    controller.current?.abort();
    setState({ status: "idle" });
  }, [storeId]);
  useEffect(() => () => controller.current?.abort(), []);

  const load = useCallback(
    async (category: string, page: number, previous: Product[]) => {
      if (!storeId) return;
      controller.current?.abort();
      const c = new AbortController();
      controller.current = c;
      if (page === 1) setState({ status: "loading", category });
      else setState((s) => (s.status === "done" ? { ...s, loadingMore: true } : s));
      try {
        const res = await api.products(storeId, category, page, BROWSE_PAGE_SIZE, c.signal);
        if (c.signal.aborted) return;
        setState({ status: "done", category, items: [...previous, ...res.items], page: res.page, pages: res.pages, total: res.total, loadingMore: false });
      } catch (error) {
        if (!isAbort(error) && !c.signal.aborted) setState({ status: "error", category, error });
      }
    },
    [storeId],
  );

  const open = useCallback((category: string | null) => {
    if (category) void load(category, 1, []);
    else {
      controller.current?.abort();
      setState({ status: "idle" });
    }
  }, [load]);

  const more = useCallback(() => {
    if (state.status === "done" && state.page < state.pages) void load(state.category, state.page + 1, state.items);
  }, [state, load]);

  return { state, open, more };
}

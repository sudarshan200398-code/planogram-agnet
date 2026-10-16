import { useCallback, useEffect, useRef, useState } from "react";
import { api, isAbort } from "../api/client";
import type { SearchResponse } from "../api/types";

export type SearchState =
  | { status: "idle" }
  | { status: "loading"; text: string }
  | { status: "done"; text: string; response: SearchResponse }
  | { status: "error"; text: string; error: unknown };

/** POST /search for the current store. A new search cancels the previous one (AbortController). */
export function useSearch(storeId: string | null) {
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  // A different store means earlier results no longer apply.
  useEffect(() => {
    controller.current?.abort();
    setState({ status: "idle" });
  }, [storeId]);

  useEffect(() => () => controller.current?.abort(), []);

  const search = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!storeId || !text) return;
      controller.current?.abort();
      const c = new AbortController();
      controller.current = c;
      setState({ status: "loading", text });
      try {
        const response = await api.search(storeId, text, c.signal);
        if (!c.signal.aborted) setState({ status: "done", text, response });
      } catch (error) {
        if (!isAbort(error) && !c.signal.aborted) setState({ status: "error", text, error });
      }
    },
    [storeId],
  );

  /** Show a response obtained elsewhere (e.g. after answering a clarification). */
  const show = useCallback((text: string, response: SearchResponse) => setState({ status: "done", text, response }), []);

  /** Clear results (e.g. when browsing a category instead). */
  const reset = useCallback(() => {
    controller.current?.abort();
    setState({ status: "idle" });
  }, []);

  return { state, search, show, reset };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, isAbort } from "../api/client";
import type { SearchResponse } from "../api/types";

export type SearchState =
  | { status: "idle" }
  | { status: "loading"; text: string }
  | { status: "done"; text: string; response: SearchResponse; answering: string | null; notice: string | null }
  | { status: "error"; text: string; error: unknown };

const isSessionGone = (e: unknown) => e instanceof ApiError && e.code === "SESSION_NOT_FOUND";

/**
 * POST /search and POST /clarify for the current store.
 *
 * Every request takes a sequence number; a response is only applied if no newer request has started,
 * so a slow or stale response can never overwrite a newer answer. A 409 SESSION_NOT_FOUND on /clarify
 * re-runs the search exactly once (and re-sends the same choice once if it is still offered), never more.
 */
export function useSearch(storeId: string | null) {
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);
  const seq = useRef(0);

  /** Start a request: cancel the previous one and return what this one needs to check before applying. */
  const begin = useCallback(() => {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    const token = ++seq.current;
    return { signal: c.signal, current: () => token === seq.current && !c.signal.aborted };
  }, []);

  // A different store means earlier results no longer apply.
  useEffect(() => {
    controller.current?.abort();
    seq.current++;
    setState({ status: "idle" });
  }, [storeId]);

  useEffect(() => () => controller.current?.abort(), []);

  const search = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!storeId || !text) return;
      const req = begin();
      setState({ status: "loading", text });
      try {
        const response = await api.search(storeId, text, req.signal);
        if (req.current()) setState({ status: "done", text, response, answering: null, notice: null });
      } catch (error) {
        if (!isAbort(error) && req.current()) setState({ status: "error", text, error });
      }
    },
    [storeId, begin],
  );

  /** Answer the pending question with one of its options. Ignored while another answer is in flight. */
  const answer = useCallback(
    async (itemIndex: number, sku: string) => {
      if (!storeId || state.status !== "done" || state.answering || !state.response.session_id) return;
      const { text, response } = state;
      const req = begin();
      setState({ status: "done", text, response, answering: sku, notice: null });
      const done = (r: SearchResponse, notice: string | null = null) => {
        if (req.current()) setState({ status: "done", text, response: r, answering: null, notice });
      };
      const fail = (error: unknown) => {
        if (!isAbort(error) && req.current()) setState({ status: "error", text, error });
      };
      try {
        done(await api.clarify(storeId, { session_id: response.session_id!, item_index: itemIndex, sku }, req.signal));
      } catch (error) {
        if (!isSessionGone(error)) return fail(error);
        // The question expired on the server: re-run the search once, then re-send the same choice once.
        try {
          const rerun = await api.search(storeId, text, req.signal);
          if (!req.current()) return;
          const q = rerun.question;
          if (rerun.session_id && q && q.item_index === itemIndex && q.options.some((o) => o.sku === sku)) {
            done(await api.clarify(storeId, { session_id: rerun.session_id, item_index: itemIndex, sku }, req.signal));
          } else {
            done(rerun, "That question had expired, so we searched again. Please choose again.");
          }
        } catch (retryError) {
          fail(retryError);
        }
      }
    },
    [storeId, state, begin],
  );

  /** Clear results (e.g. when browsing a category instead). */
  const reset = useCallback(() => {
    controller.current?.abort();
    seq.current++;
    setState({ status: "idle" });
  }, []);

  return { state, search, answer, reset };
}

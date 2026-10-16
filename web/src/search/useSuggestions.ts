import { useEffect, useState } from "react";
import { api, isAbort } from "../api/client";
import type { Suggestion } from "../api/types";
import { SUGGEST_DEBOUNCE_MS, SUGGEST_MIN_CHARS } from "../config";

/** Debounced GET /suggest. Each new text cancels the previous request, so a slow old answer never wins. */
export function useSuggestions(storeId: string | null, text: string, enabled: boolean) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = text.trim();
    if (!enabled || !storeId || q.length < SUGGEST_MIN_CHARS) {
      setSuggestions([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      api
        .suggest(storeId, q, controller.signal)
        .then((res) => {
          if (!controller.signal.aborted) setSuggestions(res.suggestions);
        })
        .catch((err: unknown) => {
          // Suggestions are a convenience: on any failure just show none.
          if (!isAbort(err) && !controller.signal.aborted) setSuggestions([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, SUGGEST_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [storeId, text, enabled]);

  return { suggestions, loading };
}

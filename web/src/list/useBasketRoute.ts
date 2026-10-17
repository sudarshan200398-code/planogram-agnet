import { useCallback, useEffect, useRef, useState } from "react";
import { api, isAbort } from "../api/client";
import type { SearchResponse } from "../api/types";
import { toBasket, type ListItem } from "./list";

export type RouteState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; response: SearchResponse; start: string | null }
  | { status: "error"; error: unknown };

/** POST /basket/route for the list, from an optional start point. Only the newest request may change state. */
export function useBasketRoute(storeId: string | null) {
  const [state, setState] = useState<RouteState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  const clear = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setState({ status: "idle" });
  }, []);

  useEffect(() => clear, [storeId, clear]);

  const find = useCallback(
    async (items: ListItem[], start: string | null = null) => {
      if (!storeId || !items.length) return;
      controller.current?.abort();
      const c = new AbortController();
      controller.current = c;
      setState({ status: "loading" });
      try {
        const response = await api.basketRoute(storeId, toBasket(items), start, c.signal);
        if (controller.current === c) setState({ status: "done", response, start });
      } catch (error) {
        if (!isAbort(error) && controller.current === c) setState({ status: "error", error });
      }
    },
    [storeId],
  );

  return { state, find, clear };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SearchResponse, StoreMap } from "../api/types";

/** Where the shopper said they are (from a sentence like "I'm at produce, milk"), for the list route. */
export interface StartPoint {
  storeId: string;
  label: string; // the start's label in this store's map; sent as `start` to POST /basket/route
  entranceLabel: string | null; // the default start, for "Reset to <entrance>"
}

/**
 * Keeps the start point found in the latest search for the current store. The search response's route
 * says where it started; the store's map says whether that is a real place in this store and whether it
 * is just the entrance (the default, so nothing to keep). Cleared when the store changes.
 */
export function useStartPoint(storeId: string | null) {
  const [start, setStart] = useState<StartPoint | null>(null);
  const maps = useRef(new Map<string, StoreMap>());
  const controller = useRef<AbortController | null>(null);

  const forget = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setStart(null);
  }, []);
  useEffect(() => forget, [storeId, forget]);

  /** Look at a search (or clarify) response; keep its start if it is a known place other than the entrance. */
  const detect = useCallback(
    async (response: SearchResponse) => {
      const route = response.route;
      if (!storeId || !route || response.store_id !== storeId) return;
      controller.current?.abort();
      const c = new AbortController();
      controller.current = c;
      try {
        let map = maps.current.get(storeId);
        if (!map) {
          map = await api.map(storeId, c.signal);
          maps.current.set(storeId, map);
        }
        if (controller.current !== c) return;
        const node = map.nodes.find((n) => n.id === route.start_node);
        if (!node || node.label !== route.start_label) return; // unknown to this store: never used
        if (node.type === "entrance") return; // the default start; keep any start said earlier
        const entrance = map.nodes.find((n) => n.type === "entrance")?.label ?? null;
        setStart({ storeId, label: node.label, entranceLabel: entrance });
      } catch {
        // Cancelled, or no map: keep no start point, so the list route starts at the entrance.
      }
    },
    [storeId],
  );

  return { start: start && start.storeId === storeId ? start : null, detect, reset: forget };
}

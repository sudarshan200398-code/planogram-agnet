import { useCallback, useEffect, useState } from "react";
import { STORAGE_KEYS } from "../config";
import { readJson, writeStorage } from "../lib/storage";
import { addItem, addItems, isListData, removeItem, setQuantity, type ListItem, type NewItem } from "./list";

const load = (storeId: string | null): ListItem[] => (storeId ? readJson(STORAGE_KEYS.list(storeId), isListData, []) : []);

/** The shopping list for the current store, kept in this browser (one list per store). */
export function useShoppingList(storeId: string | null) {
  const [state, setState] = useState(() => ({ storeId, items: load(storeId) }));
  // Switching store shows that store's own list.
  const items = state.storeId === storeId ? state.items : load(storeId);
  useEffect(() => {
    if (state.storeId !== storeId) setState({ storeId, items: load(storeId) });
  }, [storeId, state.storeId]);

  const update = useCallback(
    (next: (list: ListItem[]) => ListItem[]) => {
      setState((s) => {
        const list = next(s.storeId === storeId ? s.items : load(storeId));
        if (storeId) writeStorage(STORAGE_KEYS.list(storeId), JSON.stringify(list));
        return { storeId, items: list };
      });
    },
    [storeId],
  );

  const add = useCallback((item: NewItem) => update((l) => addItem(l, item).list), [update]);
  /** Add several at once; returns the counts for the message (worked out from the list as shown). */
  const addMany = useCallback(
    (news: (NewItem & { qty: number })[]) => {
      const result = addItems(items, news);
      if (result.added) update((l) => addItems(l, news).list);
      return result;
    },
    [items, update],
  );
  const setQty = useCallback((sku: string, qty: number) => update((l) => setQuantity(l, sku, qty)), [update]);
  const remove = useCallback((sku: string) => update((l) => removeItem(l, sku)), [update]);

  return { items, add, addMany, setQty, remove, full: addItem(items, { sku: "\u0000", name: "", image_url: null, place: null }).full };
}

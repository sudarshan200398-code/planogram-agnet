import { useCallback, useEffect, useState } from "react";
import { api, isAbort } from "../api/client";
import type { StoreSummary } from "../api/types";
import { STORAGE_KEYS } from "../config";
import { readStorage, writeStorage } from "../lib/storage";

const URL_PARAM = "store";

function urlStore(): string | null {
  return new URLSearchParams(window.location.search).get(URL_PARAM);
}

function reflectInUrl(id: string): void {
  const u = new URL(window.location.href);
  u.searchParams.set(URL_PARAM, id);
  window.history.replaceState(window.history.state, "", u);
}

/** Pick the store: the URL first, then the remembered choice, then the first store. */
export function chooseStore(stores: StoreSummary[], fromUrl: string | null, remembered: string | null): string | null {
  const ids = stores.map((s) => s.id);
  if (fromUrl && ids.includes(fromUrl)) return fromUrl;
  if (remembered && ids.includes(remembered)) return remembered;
  return ids[0] ?? null;
}

export type StoresState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; stores: StoreSummary[] };

/** Loads GET /stores, keeps the chosen store in the URL and localStorage, and can fall back to the first store. */
export function useStoreSelection() {
  const [state, setState] = useState<StoresState>({ status: "loading" });
  const [storeId, setStoreId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    api
      .stores(controller.signal)
      .then((stores) => {
        setState({ status: "ready", stores });
        const id = chooseStore(stores, urlStore(), readStorage(STORAGE_KEYS.store));
        setStoreId(id);
        if (id) {
          reflectInUrl(id);
          writeStorage(STORAGE_KEYS.store, id);
        }
      })
      .catch((error: unknown) => {
        if (!isAbort(error)) setState({ status: "error", error });
      });
    return () => controller.abort();
  }, [attempt]);

  const selectStore = useCallback((id: string) => {
    setStoreId(id);
    reflectInUrl(id);
    writeStorage(STORAGE_KEYS.store, id);
  }, []);

  /** After 404 STORE_NOT_FOUND: go back to the first store. */
  const resetToFirst = useCallback(() => {
    if (state.status !== "ready" || !state.stores[0]) return;
    selectStore(state.stores[0].id);
  }, [state, selectStore]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const current = state.status === "ready" ? (state.stores.find((s) => s.id === storeId) ?? null) : null;
  return { state, storeId, current, selectStore, resetToFirst, retry };
}

import { useEffect, useState } from "react";
import { api, isAbort } from "../api/client";
import type { Category } from "../api/types";

/** GET /categories for the store; an empty list on failure (the chips are optional shortcuts). */
export function useCategories(storeId: string | null) {
  const [categories, setCategories] = useState<Category[] | null>(null);
  useEffect(() => {
    setCategories(null);
    if (!storeId) return;
    const controller = new AbortController();
    api
      .categories(storeId, controller.signal)
      .then((res) => setCategories(res.categories))
      .catch((err: unknown) => {
        if (!isAbort(err)) setCategories([]);
      });
    return () => controller.abort();
  }, [storeId]);
  return categories;
}

/** The quick chips: the largest categories first (ties alphabetical). */
export function quickCategories(categories: Category[], count: number): Category[] {
  return [...categories].sort((a, b) => b.product_count - a.product_count || a.name.localeCompare(b.name)).slice(0, count);
}

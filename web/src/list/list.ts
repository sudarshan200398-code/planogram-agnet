// Shopping list logic, kept pure so it is easy to test. The hook in useShoppingList.ts stores it per store.
import type { BasketLine } from "../api/types";
import { LIST_MAX_ITEMS, QTY_MAX, QTY_MIN } from "../config";

export interface ListItem {
  sku: string;
  name: string;
  qty: number;
  image_url: string | null;
  place: string | null;
}
export type NewItem = Omit<ListItem, "qty">;

const clampQty = (n: number) => Math.min(QTY_MAX, Math.max(QTY_MIN, Math.round(n)));

/** Add a product with quantity 1. Already listed: unchanged. List full: unchanged and `full` is true. */
export function addItem(list: ListItem[], item: NewItem): { list: ListItem[]; full: boolean } {
  if (list.some((i) => i.sku === item.sku)) return { list, full: false };
  if (list.length >= LIST_MAX_ITEMS) return { list, full: true };
  return { list: [...list, { ...item, qty: QTY_MIN }], full: false };
}

export function setQuantity(list: ListItem[], sku: string, qty: number): ListItem[] {
  if (!Number.isFinite(qty)) return list;
  return list.map((i) => (i.sku === sku ? { ...i, qty: clampQty(qty) } : i));
}

export function removeItem(list: ListItem[], sku: string): ListItem[] {
  return list.filter((i) => i.sku !== sku);
}

export function toBasket(list: ListItem[]): BasketLine[] {
  return list.map((i) => ({ sku: i.sku, qty: i.qty }));
}

const isText = (v: unknown) => typeof v === "string" && v.length > 0;
const isTextOrNull = (v: unknown) => v === null || typeof v === "string";

function isListItem(v: unknown): v is ListItem {
  if (typeof v !== "object" || v === null) return false;
  const i = v as Record<string, unknown>;
  return (
    isText(i.sku) && isText(i.name) && isTextOrNull(i.image_url) && isTextOrNull(i.place) &&
    Number.isInteger(i.qty) && (i.qty as number) >= QTY_MIN && (i.qty as number) <= QTY_MAX
  );
}

/** Whether data read back from storage is a usable list; anything else is ignored. */
export function isListData(v: unknown): v is ListItem[] {
  return (
    Array.isArray(v) && v.length <= LIST_MAX_ITEMS && v.every(isListItem) &&
    new Set(v.map((i: ListItem) => i.sku)).size === v.length
  );
}

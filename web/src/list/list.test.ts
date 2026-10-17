import { LIST_MAX_ITEMS, QTY_MAX, QTY_MIN } from "../config";
import { addAllMessage, addItem, addItems, isListData, removeItem, setQuantity, toBasket, type ListItem } from "./list";

const item = (sku: string, qty = 1): ListItem => ({ sku, name: `Product ${sku}`, qty, image_url: null, place: null });

describe("addItem", () => {
  it("adds a new product with quantity 1, at the end", () => {
    const r = addItem([item("A")], { sku: "B", name: "Bread", image_url: "/img", place: "Level 1 · Bakery" });
    expect(r.full).toBe(false);
    expect(r.list.map((i) => [i.sku, i.qty])).toEqual([["A", 1], ["B", 1]]);
    expect(r.list[1]).toMatchObject({ name: "Bread", image_url: "/img", place: "Level 1 · Bakery" });
  });

  it("does not duplicate a product already in the list", () => {
    const start = [item("A", 3)];
    const r = addItem(start, { sku: "A", name: "x", image_url: null, place: null });
    expect(r.list).toEqual(start);
  });

  it(`refuses the ${LIST_MAX_ITEMS + 1}th product and says the list is full`, () => {
    const full = Array.from({ length: LIST_MAX_ITEMS }, (_, i) => item(`S${i}`));
    const r = addItem(full, { sku: "NEW", name: "x", image_url: null, place: null });
    expect(r.full).toBe(true);
    expect(r.list).toBe(full);
  });
});

describe("setQuantity", () => {
  it(`keeps quantities between ${QTY_MIN} and ${QTY_MAX}, whole numbers`, () => {
    const list = [item("A", 5)];
    expect(setQuantity(list, "A", 0)[0]!.qty).toBe(QTY_MIN);
    expect(setQuantity(list, "A", -4)[0]!.qty).toBe(QTY_MIN);
    expect(setQuantity(list, "A", QTY_MAX + 1)[0]!.qty).toBe(QTY_MAX);
    expect(setQuantity(list, "A", 2.6)[0]!.qty).toBe(3);
    expect(setQuantity(list, "A", Number.NaN)[0]!.qty).toBe(5);
  });

  it("changes only the named product", () => {
    const r = setQuantity([item("A"), item("B")], "B", 4);
    expect(r.map((i) => i.qty)).toEqual([1, 4]);
  });
});

it("removeItem removes only that product", () => {
  expect(removeItem([item("A"), item("B")], "A").map((i) => i.sku)).toEqual(["B"]);
});

it("toBasket sends sku and qty, in list order", () => {
  expect(toBasket([item("A", 2), item("B")])).toEqual([{ sku: "A", qty: 2 }, { sku: "B", qty: 1 }]);
});

describe("isListData (what may be read back from storage)", () => {
  it("accepts a valid list", () => {
    expect(isListData([item("A", 2)])).toBe(true);
    expect(isListData([])).toBe(true);
  });
  it.each([
    ["not an array", { sku: "A" }],
    ["missing sku", [{ name: "x", qty: 1, image_url: null, place: null }]],
    ["quantity too big", [item("A", QTY_MAX + 1)]],
    ["quantity not whole", [item("A", 1.5)]],
    ["duplicate sku", [item("A"), item("A")]],
    ["too many items", Array.from({ length: LIST_MAX_ITEMS + 1 }, (_, i) => item(`S${i}`))],
  ])("rejects %s", (_, value) => {
    expect(isListData(value)).toBe(false);
  });
});

describe("addItems (Add all to list)", () => {
  const n = (sku: string, qty: number) => ({ sku, name: `Product ${sku}`, image_url: null, place: null, qty });

  it(`adds each new product with its quantity, kept between ${QTY_MIN} and ${QTY_MAX}`, () => {
    const r = addItems([], [n("A", 2), n("B", 150), n("C", 0), n("D", 2.6)]);
    expect(r.list.map((i) => [i.sku, i.qty])).toEqual([["A", 2], ["B", QTY_MAX], ["C", QTY_MIN], ["D", 3]]);
    expect(r).toMatchObject({ added: 4, already: 0, noRoom: 0 });
  });

  it("leaves listed products unchanged and counts them, also when one is asked for twice", () => {
    const r = addItems([item("A", 7)], [n("A", 2), n("B", 1), n("B", 4)]);
    expect(r.list.map((i) => [i.sku, i.qty])).toEqual([["A", 7], ["B", 1]]);
    expect(r).toMatchObject({ added: 1, already: 2, noRoom: 0 });
  });

  it(`stops at ${LIST_MAX_ITEMS} products and counts what did not fit`, () => {
    const almost = Array.from({ length: LIST_MAX_ITEMS - 1 }, (_, i) => item(`S${i}`));
    const r = addItems(almost, [n("A", 1), n("B", 1), n("C", 1)]);
    expect(r.list).toHaveLength(LIST_MAX_ITEMS);
    expect(r).toMatchObject({ added: 1, already: 0, noRoom: 2 });
  });
});

describe("addAllMessage", () => {
  it("says what was added, kept, left out and skipped", () => {
    expect(addAllMessage({ added: 2, already: 0, noRoom: 0 }, 0)).toBe("Added 2 to your list.");
    expect(addAllMessage({ added: 1, already: 0, noRoom: 0 }, 1)).toBe("Added 1 to your list. Skipped 1 that is out of stock or not found.");
    expect(addAllMessage({ added: 0, already: 3, noRoom: 0 }, 0)).toBe("These are already in your list.");
    expect(addAllMessage({ added: 0, already: 0, noRoom: 2 }, 0)).toBe(`Your list is full (${LIST_MAX_ITEMS} products), so 2 didn't fit.`);
  });
});

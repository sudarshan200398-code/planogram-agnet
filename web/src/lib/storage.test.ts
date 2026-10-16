import { readJson, readStorage, writeStorage } from "./storage";

const isNumberList = (v: unknown): v is number[] => Array.isArray(v) && v.every((x) => typeof x === "number");

it("reads and writes", () => {
  writeStorage("k", "v");
  expect(readStorage("k")).toBe("v");
  writeStorage("k", null);
  expect(readStorage("k")).toBeNull();
});

it("never throws when storage is blocked", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("SecurityError");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("QuotaExceededError");
  });
  expect(() => writeStorage("k", "v")).not.toThrow();
  expect(readStorage("k")).toBeNull();
  expect(readJson("k", isNumberList, [])).toEqual([]);
});

it("falls back on corrupt or wrong-shaped JSON", () => {
  window.localStorage.setItem("bad", "{not json");
  window.localStorage.setItem("shape", JSON.stringify({ a: 1 }));
  window.localStorage.setItem("good", JSON.stringify([1, 2]));
  expect(readJson("bad", isNumberList, [9])).toEqual([9]);
  expect(readJson("shape", isNumberList, [9])).toEqual([9]);
  expect(readJson("good", isNumberList, [9])).toEqual([1, 2]);
});

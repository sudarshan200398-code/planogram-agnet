import type { StoreSummary } from "../api/types";
import { fixture } from "../test/handlers";
import { chooseStore } from "./useStoreSelection";

const stores = fixture("stores").body as StoreSummary[];

it("prefers the URL, then the remembered store, then the first store", () => {
  expect(chooseStore(stores, "riverside", "central")).toBe("riverside");
  expect(chooseStore(stores, null, "riverside")).toBe("riverside");
  expect(chooseStore(stores, null, null)).toBe("central");
});

it("ignores unknown ids from the URL or storage", () => {
  expect(chooseStore(stores, "nope", "also-nope")).toBe("central");
  expect(chooseStore(stores, "nope", "riverside")).toBe("riverside");
  expect(chooseStore([], "central", null)).toBeNull();
});

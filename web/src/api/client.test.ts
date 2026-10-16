import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { fixture, reply } from "../test/handlers";
import { api, ApiError, imageSrc } from "./client";

it("returns typed data from the API", async () => {
  const stores = await api.stores();
  expect(stores.map((s) => s.id)).toEqual(["central", "riverside"]);
});

it("turns the API error body into an ApiError with code and request id", async () => {
  server.use(http.get("*/api/stores/:store/categories", () => reply("error_store_not_found")));
  const err = await api.categories("nope").catch((e: unknown) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err).toMatchObject({ status: 404, code: "STORE_NOT_FOUND", requestId: "fixture-error_store_not_found" });
});

it("reads Retry-After on 429", async () => {
  server.use(http.get("*/api/stores", () => reply("error_rate_limited")));
  const err = (await api.stores().catch((e: unknown) => e)) as ApiError;
  expect(err.code).toBe("RATE_LIMITED");
  expect(err.retryAfterSeconds).toBe(Number(fixture("error_rate_limited").headers["retry-after"]));
});

it("reports an unreachable API as NETWORK", async () => {
  server.use(http.get("*/api/stores", () => HttpResponse.error()));
  const err = (await api.stores().catch((e: unknown) => e)) as ApiError;
  expect(err).toMatchObject({ status: 0, code: "NETWORK", requestId: null });
});

it("copes with a non-JSON error", async () => {
  server.use(http.get("*/api/stores", () => new HttpResponse("Bad gateway", { status: 502 })));
  const err = (await api.stores().catch((e: unknown) => e)) as ApiError;
  expect(err).toMatchObject({ status: 502, code: "HTTP_502" });
});

it("lets an aborted request stay an abort", async () => {
  const c = new AbortController();
  const p = api.stores(c.signal);
  c.abort();
  await expect(p).rejects.toMatchObject({ name: "AbortError" });
});

it("sends the search text as JSON to the chosen store", async () => {
  let seen: unknown;
  server.use(
    http.post("*/api/stores/riverside/search", async ({ request }) => {
      seen = await request.json();
      return reply("search_riverside_kibble");
    }),
  );
  const res = await api.search("riverside", "puppy kibble");
  expect(seen).toEqual({ text: "puppy kibble" });
  expect(res.store_id).toBe("riverside");
});

it("builds image URLs against the API base", () => {
  expect(imageSrc("/stores/central/products/BAK-BAG-009/image")).toBe("/api/stores/central/products/BAK-BAG-009/image");
});

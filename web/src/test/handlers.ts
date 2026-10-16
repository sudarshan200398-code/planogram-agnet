import { http, HttpResponse } from "msw";

/** Every recorded fixture by name (written by scripts/export_web_contract.py from the real API). */
const modules = import.meta.glob<{ default: Fixture }>("../api/fixtures/*.json", { eager: true });

export interface Fixture {
  name: string;
  request: { method: string; path: string; query: Record<string, unknown>; body: unknown };
  status: number;
  headers: Record<string, string>;
  body: unknown;
}

export const fixtures: Record<string, Fixture> = Object.fromEntries(
  Object.values(modules).map((m) => [m.default.name, m.default]),
);

export function fixture(name: string): Fixture {
  const f = fixtures[name];
  if (!f) throw new Error(`no fixture ${name}`);
  return f;
}

/** Answer with a fixture's recorded status, headers and body. */
export function reply(name: string) {
  const f = fixture(name);
  return HttpResponse.json(f.body as Record<string, unknown>, { status: f.status, headers: f.headers });
}

const API = "*/api";

/** The recorded search fixture for a store and text, if there is one. */
function searchFixture(store: string, text: string): Fixture | undefined {
  return Object.values(fixtures).find(
    (f) =>
      f.name.startsWith("search_") &&
      f.request.path === `/stores/${store}/search` &&
      (f.request.body as { text?: string } | null)?.text?.toLowerCase() === text.trim().toLowerCase(),
  );
}

/** Defaults: the happy paths. Tests override with server.use(...) for errors and other cases. */
export const defaultHandlers = [
  http.get(`${API}/stores`, () => reply("stores")),
  http.get(`${API}/stores/:store/categories`, ({ params }) =>
    params.store === "riverside" ? reply("categories_riverside") : reply("categories_central"),
  ),
  http.get(`${API}/stores/:store/suggest`, ({ params, request }) => {
    const q = new URL(request.url).searchParams.get("q") ?? "";
    const f = Object.values(fixtures).find(
      (x) => x.name.startsWith("suggest_") && x.request.path === `/stores/${String(params.store)}/suggest` && x.request.query.q === q,
    );
    return f ? reply(f.name) : HttpResponse.json({ store_id: params.store, suggestions: [] });
  }),
  http.get(`${API}/stores/:store/products`, ({ params, request }) => {
    const u = new URL(request.url);
    const page = u.searchParams.get("page") ?? "1";
    const f = Object.values(fixtures).find(
      (x) =>
        x.name.startsWith("products_") &&
        x.request.path === `/stores/${String(params.store)}/products` &&
        x.request.query.category === u.searchParams.get("category") &&
        String(x.request.query.page) === page,
    );
    if (!f) throw new Error(`no recorded products page for ${u.search}`);
    return reply(f.name);
  }),
  http.post(`${API}/stores/:store/basket/route`, async ({ params, request }) => {
    const body = JSON.stringify(await request.json());
    const f = Object.values(fixtures).find(
      (x) => x.name.startsWith("basket_") && x.request.path === `/stores/${String(params.store)}/basket/route` && JSON.stringify(x.request.body) === body,
    );
    if (!f) throw new Error(`no basket fixture for ${String(params.store)} ${body}`);
    return reply(f.name);
  }),
  http.post(`${API}/stores/:store/clarify`, async ({ params, request }) => {
    const body = (await request.json()) as { session_id: string; item_index: number; sku: string };
    const f = Object.values(fixtures).find((x) => {
      const b = x.request.body as typeof body | null;
      return x.name.startsWith("clarify_") && x.request.path === `/stores/${String(params.store)}/clarify` &&
        b?.session_id === body.session_id && b.item_index === body.item_index && b.sku === body.sku;
    });
    return f ? reply(f.name) : reply("error_session_not_found");
  }),
  http.post(`${API}/stores/:store/search`, async ({ params, request }) => {
    const { text } = (await request.json()) as { text: string };
    const f = searchFixture(String(params.store), text);
    if (!f) throw new Error(`no recorded search fixture for ${String(params.store)} / ${text}`);
    return reply(f.name);
  }),
];

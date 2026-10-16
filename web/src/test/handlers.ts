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
  http.post(`${API}/stores/:store/search`, async ({ params, request }) => {
    const { text } = (await request.json()) as { text: string };
    const f = searchFixture(String(params.store), text);
    if (!f) throw new Error(`no recorded search fixture for ${String(params.store)} / ${text}`);
    return reply(f.name);
  }),
];

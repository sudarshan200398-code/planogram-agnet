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

/** Defaults: the happy paths. Tests override with server.use(...) for errors and other cases. */
export const defaultHandlers = [
  http.get(`${API}/stores`, () => reply("stores")),
  http.get(`${API}/stores/:store/categories`, ({ params }) =>
    params.store === "riverside" ? reply("categories_riverside") : reply("categories_central"),
  ),
];

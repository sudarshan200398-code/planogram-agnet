import { API_BASE_URL } from "../config";
import type {
  BasketLine,
  StoreMap,
  CategoriesResponse,
  ClarifyRequest,
  ProductPage,
  SearchResponse,
  StoreSummary,
  SuggestResponse,
} from "./types";

/** A failed API call. code is the API's error code, or NETWORK when the API could not be reached. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
    readonly retryAfterSeconds: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** True for a cancelled request. Checks the name, since aborts can come from another realm's DOMException. */
export function isAbort(err: unknown): boolean {
  return typeof err === "object" && err !== null && (err as { name?: unknown }).name === "AbortError";
}

function url(path: string, query?: Record<string, string | number | undefined>): string {
  const u = new URL(API_BASE_URL + path, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== "") u.searchParams.set(k, String(v));
  return u.toString();
}

async function request<T>(
  path: string,
  init: { method?: "GET" | "POST"; body?: unknown; signal?: AbortSignal; query?: Record<string, string | number | undefined> } = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url(path, init.query), {
      method: init.method ?? "GET",
      headers: init.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
  } catch (err) {
    if (isAbort(err)) throw err;
    throw new ApiError(0, "NETWORK", "The store service can't be reached.", null);
  }
  if (res.ok) return (await res.json()) as T;

  let code = `HTTP_${res.status}`;
  let message = "Something went wrong.";
  let requestId = res.headers.get("X-Request-ID");
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string; request_id?: string } };
    code = body.error?.code ?? code;
    message = body.error?.message ?? message;
    requestId = body.error?.request_id ?? requestId;
  } catch {
    /* not JSON: keep the defaults */
  }
  const retry = Number(res.headers.get("Retry-After"));
  throw new ApiError(res.status, code, message, requestId, Number.isFinite(retry) && retry > 0 ? retry : null);
}

const store = (id: string) => `/stores/${encodeURIComponent(id)}`;

export const api = {
  stores: (signal?: AbortSignal) => request<StoreSummary[]>("/stores", { signal }),
  categories: (storeId: string, signal?: AbortSignal) => request<CategoriesResponse>(`${store(storeId)}/categories`, { signal }),
  products: (storeId: string, category: string | undefined, page: number, pageSize: number, signal?: AbortSignal) =>
    request<ProductPage>(`${store(storeId)}/products`, { signal, query: { category, page, page_size: pageSize } }),
  suggest: (storeId: string, q: string, signal?: AbortSignal) =>
    request<SuggestResponse>(`${store(storeId)}/suggest`, { signal, query: { q } }),
  search: (storeId: string, text: string, signal?: AbortSignal) =>
    request<SearchResponse>(`${store(storeId)}/search`, { method: "POST", body: { text }, signal }),
  clarify: (storeId: string, body: ClarifyRequest, signal?: AbortSignal) =>
    request<SearchResponse>(`${store(storeId)}/clarify`, { method: "POST", body, signal }),
  map: (storeId: string, signal?: AbortSignal) => request<StoreMap>(`${store(storeId)}/map`, { signal }),
  basketRoute: (storeId: string, items: BasketLine[], signal?: AbortSignal) =>
    request<SearchResponse>(`${store(storeId)}/basket/route`, { method: "POST", body: { items }, signal }),
};

/** image_url from the API is a path; make it absolute against the API base. */
export function imageSrc(imageUrl: string): string {
  return API_BASE_URL + imageUrl;
}

/** API types, generated from the real OpenAPI schema (web/openapi.json -> schema.d.ts). Never hand-written. */
import type { components } from "./schema";

type S = components["schemas"];

export type StoreSummary = S["StoreSummary"];
export type Category = S["Category"];
export type CategoriesResponse = S["CategoriesResponse"];
export type Product = S["Product"];
export type ProductPage = S["ProductPage"];
export type Suggestion = S["Suggestion"];
export type SuggestResponse = S["SuggestResponse"];
export type SearchRequest = S["SearchRequest"];
export type SearchResponse = S["SearchResponse"];
export type SearchItem = S["SearchItem"];
export type Question = S["QuestionOut"];
export type Option = S["Option"];
export type ClarifyRequest = S["ClarifyRequest"];
export type BasketLine = S["BasketLine"];
export type BasketRouteRequest = S["BasketRouteRequest"];
export type Route = S["RouteOut"];
export type StoreMap = S["MapResponse"];
export type MapNode = S["MapNode"];
export type RouteStep = S["RouteStep"];
export type Location = S["Location"];
export type ErrorBody = S["ErrorBody"];
export type StockStatus = Product["stock_status"];

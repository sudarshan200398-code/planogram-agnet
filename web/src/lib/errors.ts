import { ApiError } from "../api/client";

export interface FriendlyError {
  title: string;
  message: string;
  requestId: string | null;
}

/** Shopper-friendly wording for any failure. Never shows the raw error. */
export function friendlyError(err: unknown): FriendlyError {
  if (!(err instanceof ApiError)) {
    return { title: "Something went wrong", message: "Please try again.", requestId: null };
  }
  const requestId = err.requestId;
  switch (err.code) {
    case "NETWORK":
      return { title: "Can't reach the store", message: "Check your connection and try again.", requestId };
    case "RATE_LIMITED": {
      const wait = err.retryAfterSeconds ?? 30;
      return { title: "Lots of searches right now", message: `Please wait about ${wait} seconds and try again.`, requestId };
    }
    case "STORE_NOT_FOUND":
      return { title: "That store isn't available", message: "We've switched you to another store.", requestId };
    case "SESSION_NOT_FOUND":
      return { title: "That question has expired", message: "Please search again.", requestId };
    case "TEXT_TOO_LONG":
      return { title: "That's a long search", message: "Please shorten it to under 500 characters.", requestId };
    case "STORE_UNAVAILABLE":
      return { title: "The store is updating", message: "Please try again in a moment.", requestId };
    default:
      return { title: "Something went wrong", message: "Please try again.", requestId };
  }
}

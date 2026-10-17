import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { toHaveNoViolations } from "jest-axe";
import { afterAll, afterEach, beforeAll, expect } from "vitest";
import { server } from "./server";

expect.extend(toHaveNoViolations);

declare module "vitest" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- must match Vitest's declaration
  interface Matchers<R extends void | Promise<void> = void | Promise<void>, T = unknown> {
    toHaveNoViolations(): R;
  }
}

// Any request without a matching mock handler fails the test (no real network in tests).
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});
afterAll(() => server.close());

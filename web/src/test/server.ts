import { setupServer } from "msw/node";
import { defaultHandlers } from "./handlers";

/** Mock API for tests, answering with responses recorded from the real API (src/api/fixtures). */
export const server = setupServer(...defaultHandlers);

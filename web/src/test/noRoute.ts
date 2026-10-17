import { screen, within } from "@testing-library/react";
import { expect } from "vitest";

/** Search results show only product cards: no "Your route", no steps button and no map (the route lives in the list). */
export function expectNoRouteUnderSearch() {
  const results = screen.getByRole("region", { name: "Results" });
  expect(within(results).queryByRole("region", { name: "Your route" })).not.toBeInTheDocument();
  expect(within(results).queryByRole("heading", { name: "Your route" })).not.toBeInTheDocument();
  expect(within(results).queryByRole("button", { name: /^(Show \d+ steps|Hide steps)$/ })).not.toBeInTheDocument();
  expect(within(results).queryByRole("img", { name: /^Map of / })).not.toBeInTheDocument();
  expect(results.querySelector(".sf-route, .sf-map")).toBeNull();
}

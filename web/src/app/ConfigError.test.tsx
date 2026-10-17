import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { resolveApiBase } from "../config";
import { ConfigError } from "./ConfigError";

it("says plainly that the app is not set up, with the exact setting to fix, and logs it", async () => {
  const error = resolveApiBase(undefined, true).error!;
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const { container } = render(<ConfigError message={error} />);
  expect(screen.getByRole("alert")).toHaveTextContent("This app isn't set up correctly");
  expect(screen.getByRole("alert")).toHaveTextContent(error);
  expect(log).toHaveBeenCalledWith(expect.stringContaining("VITE_API_BASE_URL is not set"));
  expect(await axe(container)).toHaveNoViolations();
});

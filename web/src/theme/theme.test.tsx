import { act, renderHook } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { useTheme } from "./theme";

function mockSystem(dark: boolean) {
  const listeners: ((e: { matches: boolean }) => void)[] = [];
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: dark && query.includes("dark"),
        media: query,
        addEventListener: (_: string, fn: (e: { matches: boolean }) => void) => listeners.push(fn),
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  );
}

beforeEach(() => {
  if (!window.matchMedia) window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
});

it("follows the system setting by default", () => {
  mockSystem(true);
  const { result } = renderHook(() => useTheme());
  expect(result.current.preference).toBe("system");
  expect(result.current.theme).toBe("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
});

it("remembers a manual choice and can go back to the system setting", () => {
  mockSystem(true);
  const { result } = renderHook(() => useTheme());
  act(() => result.current.setPreference("light"));
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(window.localStorage.getItem("superfind.theme")).toBe("light");
  act(() => result.current.setPreference("system"));
  expect(window.localStorage.getItem("superfind.theme")).toBeNull();
  expect(document.documentElement.dataset.theme).toBe("dark");
});

it("keeps working when storage is blocked", () => {
  mockSystem(false);
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("light");
  act(() => result.current.setPreference("dark"));
  expect(document.documentElement.dataset.theme).toBe("dark");
});

it("sets the theme in index.html before the app loads (no flash), with storage in try/catch", () => {
  const html = readFileSync(join(__dirname, "..", "..", "index.html"), "utf8");
  const head = html.slice(0, html.indexOf("</head>"));
  expect(head).toContain('localStorage.getItem("superfind.theme")');
  expect(head).toMatch(/try\s*\{/);
  expect(head).toContain('setAttribute("data-theme"');
  expect(html.indexOf('setAttribute("data-theme"')).toBeLessThan(html.indexOf("/src/main.tsx"));
});

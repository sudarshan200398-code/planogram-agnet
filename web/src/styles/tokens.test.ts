import { readFileSync } from "node:fs";
import { join } from "node:path";

/** WCAG AA contrast for every text/background pair the app uses, in both themes, read from tokens.css. */

const css = readFileSync(join(__dirname, "tokens.css"), "utf8");

function block(selector: RegExp): Record<string, string> {
  const match = css.match(selector);
  if (!match?.[1]) throw new Error(`no block for ${selector}`);
  const vars: Record<string, string> = {};
  for (const m of match[1].matchAll(/--(color-[a-z-]+):\s*(#[0-9a-fA-F]{6})/g)) vars[m[1]!] = m[2]!.toLowerCase();
  return vars;
}

const themes = {
  light: block(/:root,\s*:root\[data-theme="light"\]\s*\{([^}]*)\}/),
  dark: block(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/),
};

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

// [foreground, background, minimum ratio, where it is used]
const PAIRS: [string, string, number, string][] = [
  ["color-text", "color-bg", 4.5, "body text on page"],
  ["color-text", "color-surface", 4.5, "body text on cards"],
  ["color-text", "color-surface-sunken", 4.5, "text on sunken areas"],
  ["color-muted", "color-bg", 4.5, "secondary text on page"],
  ["color-muted", "color-surface", 4.5, "secondary text on cards"],
  ["color-on-primary", "color-primary", 4.5, "button labels"],
  ["color-primary", "color-bg", 4.5, "links on page"],
  ["color-primary", "color-surface", 4.5, "links on cards"],
  ["color-accent", "color-bg", 3, "accent large text and icons"],
  ["color-accent-text", "color-surface", 4.5, "small accent text"],
  ["color-ok-fg", "color-ok-bg", 4.5, "in stock badge"],
  ["color-warn-fg", "color-warn-bg", 4.5, "low stock badge"],
  ["color-bad-fg", "color-bad-bg", 4.5, "out of stock badge"],
  ["color-bad-fg", "color-surface", 4.5, "error text on cards"],
  ["color-info-fg", "color-info-bg", 4.5, "info badge"],
  ["color-border", "color-surface", 3, "input and chip borders (non-text)"],
  ["color-primary", "color-surface", 3, "focus ring (non-text)"],
  ["color-map-route", "color-map-floor", 3, "route line on the floor map (non-text)"],
  ["color-map-route", "color-surface", 3, "route line where it crosses a zone marker's halo (non-text)"],
  ["color-text", "color-map-floor", 4.5, "zone labels on the floor map"],
  ["color-map-zone", "color-map-floor", 3, "zone markers on the floor map (non-text)"],
  ["color-on-primary", "color-primary", 4.5, "stop numbers on the map"],
];

describe.each(Object.entries(themes))("%s theme", (_name, vars) => {
  it.each(PAIRS)("%s on %s is at least %s:1 (%s)", (fg, bg, min) => {
    expect(vars[fg], fg).toBeDefined();
    expect(vars[bg], bg).toBeDefined();
    expect(contrast(vars[fg]!, vars[bg]!)).toBeGreaterThanOrEqual(min);
  });
});

it("uses the brand colours from the brief", () => {
  expect(themes.light).toMatchObject({
    "color-primary": "#0b7a5e", "color-accent": "#c77700", "color-bg": "#f7faf8", "color-surface": "#ffffff", "color-text": "#10201a",
  });
  expect(themes.dark).toMatchObject({
    "color-primary": "#3dd6a5", "color-accent": "#f5b544", "color-bg": "#0d1512", "color-surface": "#16211d", "color-text": "#e8f1ed",
  });
});

it("never uses the light accent for small text (it is 3.46:1 on white)", () => {
  expect(contrast(themes.light["color-accent"]!, themes.light["color-surface"]!)).toBeLessThan(4.5);
  expect(themes.light["color-accent-text"]).toBe("#8f5600");
});

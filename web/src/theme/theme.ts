import { useCallback, useEffect, useState } from "react";
import { STORAGE_KEYS } from "../config";
import { readStorage, writeStorage } from "../lib/storage";

export type ThemePreference = "system" | "light" | "dark";
export type Theme = "light" | "dark";

const DARK_QUERY = "(prefers-color-scheme: dark)";

export function readPreference(): ThemePreference {
  const v = readStorage(STORAGE_KEYS.theme);
  return v === "light" || v === "dark" ? v : "system";
}

export function systemTheme(): Theme {
  return typeof window !== "undefined" && window.matchMedia?.(DARK_QUERY).matches ? "dark" : "light";
}

export function resolveTheme(pref: ThemePreference): Theme {
  return pref === "system" ? systemTheme() : pref;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

/** Theme preference (system / light / dark), remembered, following system changes while on "system". */
export function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(readPreference()));

  useEffect(() => {
    const next = resolveTheme(preference);
    setTheme(next);
    applyTheme(next);
    if (preference !== "system" || !window.matchMedia) return;
    const media = window.matchMedia(DARK_QUERY);
    const onChange = () => {
      const t = media.matches ? "dark" : "light";
      setTheme(t);
      applyTheme(t);
    };
    media.addEventListener?.("change", onChange);
    return () => media.removeEventListener?.("change", onChange);
  }, [preference]);

  const setPreference = useCallback((pref: ThemePreference) => {
    writeStorage(STORAGE_KEYS.theme, pref === "system" ? null : pref);
    setPreferenceState(pref);
  }, []);

  return { preference, theme, setPreference };
}

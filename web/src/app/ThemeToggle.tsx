import { MoonIcon, SunIcon } from "../components/icons";
import type { ThemePreference } from "../theme/theme";

const NEXT: Record<ThemePreference, ThemePreference> = { system: "light", light: "dark", dark: "system" };
const LABEL: Record<ThemePreference, string> = { system: "System", light: "Light", dark: "Dark" };

/** Cycles System → Light → Dark; the button says the current choice. */
export function ThemeToggle({ preference, onChange }: { preference: ThemePreference; onChange: (p: ThemePreference) => void }) {
  return (
    <button
      type="button"
      className="sf-theme-toggle"
      onClick={() => onChange(NEXT[preference])}
      aria-label={`Theme: ${LABEL[preference]}. Change theme`}
    >
      {preference === "dark" ? <MoonIcon /> : <SunIcon />}
      <span>{LABEL[preference]}</span>
    </button>
  );
}

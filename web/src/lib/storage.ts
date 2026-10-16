/** localStorage that never throws: private windows, blocked site data or quota errors just mean "not saved". */

export function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* not saved; the app keeps working for this visit */
  }
}

export function readJson<T>(key: string, isValid: (v: unknown) => v is T, fallback: T): T {
  const raw = readStorage(key);
  if (raw === null) return fallback;
  try {
    const value: unknown = JSON.parse(raw);
    return isValid(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

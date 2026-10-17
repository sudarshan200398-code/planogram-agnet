import { resolveApiBase } from "./config";

describe("resolveApiBase (VITE_API_BASE_URL)", () => {
  it("development without a value uses the /api dev proxy", () => {
    expect(resolveApiBase(undefined, false)).toEqual({ url: "/api", error: null });
  });

  it("uses the given API address, without a trailing slash", () => {
    expect(resolveApiBase("https://superfind-api.onrender.com/", true)).toEqual({ url: "https://superfind-api.onrender.com", error: null });
    expect(resolveApiBase(" http://127.0.0.1:8001 ", true)).toEqual({ url: "http://127.0.0.1:8001", error: null });
  });

  it("production without a value is an error, never a silent call to the wrong host", () => {
    for (const missing of [undefined, "", "   "]) {
      const r = resolveApiBase(missing, true);
      expect(r.error).toMatch(/VITE_API_BASE_URL is not set/);
      expect(r.url).toBe("");
    }
  });

  it("rejects a value that is not an http(s) address", () => {
    for (const bad of ["superfind-api.onrender.com", "ftp://x.example", "javascript:alert(1)"]) {
      const r = resolveApiBase(bad, true);
      expect(r.error).toMatch(/VITE_API_BASE_URL must be an http\(s\) address/);
      expect(r.url).toBe("");
    }
  });
});

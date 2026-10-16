// Minimal types for jest-axe (its @types package pulls in Jest's globals, which clash with Vitest's).
declare module "jest-axe" {
  export function axe(html: Element | string, options?: Record<string, unknown>): Promise<unknown>;
  export const toHaveNoViolations: Record<string, (received: unknown) => { pass: boolean; message(): string }>;
}

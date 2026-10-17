import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { AlertIcon } from "./icons";
import "./ui.css";

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({
  variant = "primary",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return <button type="button" className={`sf-button sf-button--${variant} ${className}`} {...rest} />;
}

/** Icon-only button: the label is required so screen readers announce it. */
export function IconButton({
  label,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" aria-label={label} title={label} className={`sf-icon-button ${className}`} {...rest}>
      {children}
    </button>
  );
}

export function Chip({
  selected = false,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return (
    <button type="button" aria-pressed={selected} className={`sf-chip ${selected ? "is-selected" : ""} ${className}`} {...rest} />
  );
}

export type BadgeTone = "ok" | "warn" | "bad" | "neutral" | "info";

/** Status badge: always icon plus text, never colour alone. */
export function Badge({ tone, icon, children }: { tone: BadgeTone; icon?: ReactNode; children: ReactNode }) {
  return (
    <span className={`sf-badge sf-badge--${tone}`}>
      {icon}
      <span>{children}</span>
    </span>
  );
}

export function Card({ className = "", ...rest }: HTMLAttributes<HTMLElement>) {
  return <article className={`sf-card ${className}`} {...rest} />;
}

export function Skeleton({ height = "1rem", width = "100%", className = "" }: { height?: string; width?: string; className?: string }) {
  return <span aria-hidden="true" className={`sf-skeleton ${className}`} style={{ height, width }} />;
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <section className="sf-state" aria-live="polite">
      {icon ? <div className="sf-state__icon">{icon}</div> : null}
      <h2 className="sf-state__title">{title}</h2>
      {children ? <div className="sf-state__body">{children}</div> : null}
    </section>
  );
}

/** Friendly error with an optional retry; the request id is shown small so support can trace it. */
export function ErrorState({
  title,
  message,
  requestId,
  onRetry,
  retryLabel = "Try again",
}: {
  title: string;
  message: string;
  requestId?: string | null;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <section className="sf-state sf-state--error" role="alert">
      <div className="sf-state__icon">
        <AlertIcon />
      </div>
      <h2 className="sf-state__title">{title}</h2>
      <p className="sf-state__body">{message}</p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
      {requestId ? <p className="sf-state__ref">Reference: {requestId}</p> : null}
    </section>
  );
}

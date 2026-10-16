import { useEffect, useId, useRef, type ReactNode } from "react";
import { CloseIcon } from "./icons";
import { IconButton } from "./ui";
import "./sheet.css";

/** Bottom sheet on phones, centred dialog on wider screens. Esc and the backdrop close it; focus returns afterwards. */
export function Sheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="sf-sheet" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={panel} className="sf-sheet__panel" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="sf-sheet__head">
          <h2 id={titleId} className="sf-sheet__title">
            {title}
          </h2>
          <IconButton label="Close" onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </div>
        <div className="sf-sheet__body">{children}</div>
      </div>
    </div>
  );
}

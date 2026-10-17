import { useEffect } from "react";
import { TOAST_MS } from "../config";
import { CheckIcon, CloseIcon } from "./icons";
import { IconButton } from "./ui";
import "./toast.css";

export interface ToastMessage {
  id: number; // a new id restarts the timer, even for the same text
  text: string;
  action?: { label: string; run: () => void };
}

/**
 * A short confirmation at the bottom of the screen. The live region is always in the page so screen
 * readers announce new messages; it never takes focus, and it closes itself after TOAST_MS.
 */
export function Toast({ message, onClose }: { message: ToastMessage | null; onClose: () => void }) {
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(onClose, TOAST_MS);
    return () => window.clearTimeout(timer);
  }, [message, onClose]);

  return (
    <div className="sf-toast-region" aria-live="polite">
      {message ? (
        <div className="sf-toast" data-testid="toast" key={message.id}>
          <CheckIcon className="sf-toast__icon" />
          <p className="sf-toast__text">{message.text}</p>
          {message.action ? (
            <button
              type="button"
              className="sf-toast__action"
              onClick={() => {
                message.action!.run();
                onClose();
              }}
            >
              {message.action.label}
            </button>
          ) : null}
          <IconButton label="Dismiss" className="sf-toast__close" onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </div>
      ) : null}
    </div>
  );
}

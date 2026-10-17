import { useEffect, useState } from "react";
import { SLOW_REQUEST_MS } from "../config";
import "./waking.css";

/** True once `active` has stayed true for SLOW_REQUEST_MS; false again as soon as it ends. */
export function useSlow(active: boolean, ms = SLOW_REQUEST_MS): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), ms);
    return () => window.clearTimeout(timer);
  }, [active, ms]);
  return active && slow;
}

/** Shown while a request is slow: the free API host sleeps when idle and takes a while to wake. */
export function WakingUp() {
  return (
    <p className="sf-waking" role="status">
      <span className="sf-waking__spinner" aria-hidden="true" />
      Waking up the store server, this can take up to a minute.
    </p>
  );
}

import { useEffect } from "react";
import "../components/ui.css";
import "./app.css";

/** Shown instead of the app when the build has no usable API address (see resolveApiBase). */
export function ConfigError({ message }: { message: string }) {
  useEffect(() => console.error(`SuperFind: ${message}`), [message]);
  return (
    <main className="sf-main">
      <section className="sf-state sf-state--error" role="alert">
        <h1 className="sf-state__title">This app isn't set up correctly</h1>
        <p className="sf-state__body">{message}</p>
      </section>
    </main>
  );
}

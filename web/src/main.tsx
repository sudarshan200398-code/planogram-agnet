import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ConfigError } from "./app/ConfigError";
import { API_CONFIG_ERROR } from "./config";
import "./styles/tokens.css";
import "./styles/base.css";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      {API_CONFIG_ERROR ? <ConfigError message={API_CONFIG_ERROR} /> : <App />}
    </StrictMode>,
  );
}

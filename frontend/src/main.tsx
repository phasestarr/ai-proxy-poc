/**
 * Purpose:
 * - Entry point for the React application.
 *
 * Responsibilities:
 * - Mount the root React component into the browser DOM.
 * - Keep top-level composition thin and predictable.
 */
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

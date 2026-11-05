import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@fontsource-variable/inter/wght.css";
import "@fontsource/newsreader/latin-400.css";
import "@fontsource/newsreader/latin-400-italic.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "./index.css";

// shortcut: throwaway sky candidate switch (?sky=a|b|c, docs/design/sky-pattern.md); remove once the owner picks one
document.documentElement.dataset.sky = new URLSearchParams(location.search).get("sky") ?? "none";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

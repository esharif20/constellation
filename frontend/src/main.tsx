import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@fontsource-variable/inter/wght.css";
import "@fontsource/newsreader/latin-400.css";
import "@fontsource/newsreader/latin-400-italic.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "./index.css";
import { startSky } from "./graph/sky";

// shortcut: throwaway sky candidate switch (?sky=a|b|c, docs/design/sky-pattern.md); remove once the owner picks one
const q = new URLSearchParams(location.search), sky = q.get("sky") ?? "none";
document.documentElement.dataset.sky = sky;
if (q.has("drift")) document.documentElement.dataset.drift = ""; // opt-in slow drift of the deep field, CSS only
if (sky === "b" || sky === "c") startSky();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

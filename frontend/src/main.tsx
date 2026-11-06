import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@fontsource-variable/inter/wght.css";
import "@fontsource/newsreader/latin-400.css";
import "@fontsource/newsreader/latin-400-italic.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "./index.css";
import { startSky } from "./graph/sky";

// ?drift: the deep field's slow wander, off by default and off under reduced motion (CSS only); ?sky= overrides the Sky settings
if (new URLSearchParams(location.search).has("drift")) document.documentElement.dataset.drift = "";
startSky();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

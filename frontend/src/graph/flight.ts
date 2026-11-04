// The camera flight's path and length. Kept apart from layout.ts so d3-interpolate loads with the map (the Atlas chunk), not with the first paint.
import { interpolateZoom } from "d3-interpolate";
import type { View } from "./layout";

export const FLIGHT = { rho: 1.2, min: 700, max: 1300 };

// d3's smooth zoom-and-pan path between two views (van Wijk), at our rho: a flatter arc than d3's default sqrt 2, so a hop between
// neighbouring clusters does not balloon out to the whole map. Calling it with t in 0..1 gives [x, y, width in graph units].
// (@types/d3-interpolate does not declare `.rho`; it exists at runtime.)
export const flightPath = (a: View, b: View, W: number) =>
  (interpolateZoom as typeof interpolateZoom & { rho: (rho: number) => typeof interpolateZoom }).rho(FLIGHT.rho)([a.x, a.y, W / a.k], [b.x, b.y, W / b.k]);

// From d3's own path-length duration: longer for far or deep moves, never under 700 ms or over 1300 ms.
export const flightMs = (d3Duration: number) => Math.max(FLIGHT.min, Math.min(FLIGHT.max, d3Duration * 0.8));

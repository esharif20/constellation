// Sky settings (docs/design/sky-pattern.md): which background layers show and how strongly. Pure logic plus a tiny
// store; the deep field (sky.ts), the graticule (paint.ts) and the Sky popover all read it.

export type Strength = 0 | 1 | 2; // Off, Subtle, Rich
export type SkySettings = { band: boolean; dust: boolean; anchors: boolean; graticule: boolean; grain: boolean; strength: Strength };
export type Layer = Exclude<keyof SkySettings, "strength">;

export const LAYERS: [Layer, string][] = [["band", "Milky Way band"], ["dust", "Star dust"], ["anchors", "Bright stars"], ["graticule", "Chart rings"], ["grain", "Grain"]];
export const STRENGTHS = ["Off", "Subtle", "Rich"] as const;
// the recommended subtle blend: chart rings stay off because they are lines behind the Relation lines
export const DEFAULTS: SkySettings = { band: true, dust: true, anchors: true, graticule: false, grain: true, strength: 1 };
export const KEY = "constellation.sky.v1";

// how much each strength multiplies every layer's alpha token
export const gain = (s: Strength) => [0, 1, 1.55][s];

// Anything from storage or a URL is untrusted: keep only known keys of the right type, fill the rest from DEFAULTS.
export function parse(raw: unknown): SkySettings {
  const out = { ...DEFAULTS };
  if (!raw || typeof raw !== "object") return out;
  const r = raw as Record<string, unknown>;
  for (const [k] of LAYERS) if (typeof r[k] === "boolean") out[k] = r[k];
  if (r.strength === 0 || r.strength === 1 || r.strength === 2) out.strength = r.strength;
  return out;
}

// dev override: ?sky=a|b|c|none from the candidate rounds still works, and wins over storage without being saved
export function fromQuery(sky: string | null): SkySettings | null {
  if (sky === "none") return { ...DEFAULTS, strength: 0 };
  if (sky === "a") return { band: false, dust: false, anchors: false, graticule: true, grain: false, strength: 1 };
  if (sky === "b") return { ...DEFAULTS };
  if (sky === "c") return { ...DEFAULTS, graticule: true };
  if (sky === "rich") return { ...DEFAULTS, strength: 2 };
  return null;
}

// Each image layer is rendered once at Rich strength; a toggle or strength change only sets its CSS opacity.
export type ImageLayer = "band" | "dust" | "anchors" | "grain";
export const IMAGE_LAYERS: ImageLayer[] = ["band", "dust", "anchors", "grain"];
export const layerOpacity = (s: SkySettings) =>
  Object.fromEntries(IMAGE_LAYERS.map((k) => [k, s[k] ? gain(s.strength) / gain(2) : 0])) as Record<ImageLayer, number>;

export function load(storage: Pick<Storage, "getItem"> | null): SkySettings {
  try { return parse(JSON.parse(storage?.getItem(KEY) ?? "null")); } catch { return { ...DEFAULTS }; }
}
export function save(storage: Pick<Storage, "setItem"> | null, s: SkySettings) {
  try { storage?.setItem(KEY, JSON.stringify(s)); } catch { /* private mode or blocked storage: the setting lasts this visit only */ }
}

const store = () => { try { return window.localStorage; } catch { return null; } };
const override = typeof location === "undefined" ? null : fromQuery(new URLSearchParams(location.search).get("sky"));
let current: SkySettings = override ?? (typeof window === "undefined" ? { ...DEFAULTS } : load(store()));
const subs = new Set<(s: SkySettings) => void>();

export const getSky = () => current;
export function setSky(next: SkySettings) {
  current = next;
  if (!override) save(store(), next);
  for (const f of subs) f(next);
}
export function onSky(f: (s: SkySettings) => void) { subs.add(f); return () => void subs.delete(f); }

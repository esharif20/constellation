// Sky settings logic and band geometry (docs/design/sky-pattern.md). Run: npm run sky:check
import { strict as assert } from "node:assert";
import { DEFAULTS, IMAGE_LAYERS, KEY, VERSION, LAYERS, fromQuery, gain, layerOpacity, load, parse, save } from "../src/graph/skySettings.ts";
import { readFileSync } from "node:fs";
import { bandAt, bandPixels, fbm, fields, placeFor, sizeKey, type Ink, type RGB } from "../src/graph/sky.ts";

// parse keeps only known, well-typed keys
assert.deepEqual(parse(null), DEFAULTS);
assert.deepEqual(parse("x"), DEFAULTS);
assert.deepEqual(parse({ band: false, strength: 2, evil: 1, grain: "yes" }), { ...DEFAULTS, band: false, strength: 2 });
assert.equal(parse({ strength: 3 }).strength, DEFAULTS.strength);
assert.equal(parse({ strength: "1" }).strength, DEFAULTS.strength);
// the recommended default: subtle, chart rings on
assert.equal(DEFAULTS.strength, 1);
assert.equal(DEFAULTS.graticule, true);
assert.equal(LAYERS.length, 5);

// storage round trip; broken JSON and throwing storage fall back without a crash
const mem = new Map<string, string>();
const fake = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v) };
save(fake, { ...DEFAULTS, grain: false, strength: 2 });
assert.deepEqual(load(fake), { ...DEFAULTS, grain: false, strength: 2 });
mem.set(KEY, "{not json");
assert.deepEqual(load(fake), DEFAULTS);
const boom = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
assert.deepEqual(load(boom), DEFAULTS);
save(boom, DEFAULTS); // must not throw
assert.deepEqual(load(null), DEFAULTS);

// migration: an old v1 record (rings off, no version) gets the new layers once, keeping its strength; a v2 record is kept
mem.set(KEY, JSON.stringify({ ...DEFAULTS, graticule: false, dust: false, strength: 2 }));
assert.deepEqual(load(fake), { ...DEFAULTS, strength: 2 });
mem.set(KEY, JSON.stringify({ ...DEFAULTS, graticule: false, v: VERSION }));
assert.equal(load(fake).graticule, false, "a choice saved after the migration is kept");
save(fake, { ...DEFAULTS, grain: false });
assert.equal(JSON.parse(mem.get(KEY)!).v, VERSION);
// dev override
assert.equal(fromQuery("none")!.strength, 0);
assert.equal(fromQuery("c")!.graticule, true);
assert.equal(fromQuery("a")!.band, false);
assert.equal(fromQuery("zzz"), null);
assert.equal(fromQuery(null), null);

// strength scales every layer; Off is zero
assert.equal(gain(0), 0);
assert.ok(gain(1) < gain(2));
// a toggle or strength change is opacity only: layers are rendered at Rich and the render key is the window size alone
const o = layerOpacity(DEFAULTS);
assert.ok(Math.abs(o.band - gain(1) / gain(2)) < 1e-9);
assert.equal(layerOpacity({ ...DEFAULTS, band: false }).band, 0);
assert.equal(layerOpacity({ ...DEFAULTS, strength: 2 }).dust, 1);
for (const k of IMAGE_LAYERS) assert.equal(layerOpacity({ ...DEFAULTS, strength: 0 })[k], 0);
assert.equal(sizeKey(1488, 948), "1488x948:1:0:0");
// structural: apply() (the onSky handler) sets opacity and never calls a renderer; only renderAll renders
const src = readFileSync(new URL("../src/graph/sky.ts", import.meta.url), "utf8");
const applyBody = src.slice(src.indexOf("export function apply()"), src.indexOf("\n}\n", src.indexOf("export function apply()")));
assert.ok(!/render|fields\(/.test(applyBody.replace("performance.measure(\"sky-apply\"", "")), "apply() must not render");
assert.ok(/onSky\(apply\)/.test(src), "settings changes go to apply()");
assert.ok(!/onSky\(renderAll\)/.test(src));

// noise is deterministic and in range
assert.equal(fbm(12.3, 4.5, 5), fbm(12.3, 4.5, 5));
for (let i = 0; i < 500; i++) { const v = fbm(i * 0.37, i * 0.11, 5); assert.ok(v >= 0 && v <= 1); }

// band geometry: a narrow Gaussian across the plane, the bulge and the band kept off the graph's real screen box
for (const [w, h] of [[1440, 900], [390, 844]]) {
  const S = Math.min(w, h), p0 = placeFor(null, w, h), mid = bandAt(w / 2, h / 2, w, h, p0);
  assert.ok(mid.sigma > 0.05 * S && mid.sigma < 0.13 * S, `a narrow band: sigma ~8.5% of the short side at ${w}`);
  assert.ok(bandAt(w / 2 + mid.sigma * 3 * 0.5, h / 2 + mid.sigma * 3 * 0.87, w, h, p0).core < 0.3, "the band falls off across");
  // graph in the bottom-right corner: the band moves up-left, so the graph's centre is well off the plane
  const box = { x: 0.62 * w, y: 0.68 * h, w: 0.34 * w, h: 0.28 * h }, p = placeFor(box, w, h);
  const c = bandAt(box.x + box.w / 2, box.y + box.h / 2, w, h, p);
  assert.ok(c.core < 0.05 && c.bulge < 0.2, `band and bulge avoid a corner graph at ${w}: ${JSON.stringify(p)}`);
  // graph over the middle: the bulge is pushed out to the corner
  const pc = placeFor({ x: 0.2 * w, y: 0.15 * h, w: 0.6 * w, h: 0.7 * h }, w, h);
  assert.ok(pc.far && bandAt(w / 2, h / 2, w, h, pc).bulge < 0.2, `bulge off a centred graph at ${w}`);
  // a small pan does not change the placement (no re-render)
  assert.deepEqual(placeFor({ ...box, x: box.x + 8, y: box.y - 6 }, w, h), p);
}
// first paint (owner: "it weirdly renders in"): the root stays hidden until every layer has an image, then all four swap
// in one task and the root fades once; no layer is revealed alone
const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
assert.match(css, /\.sky-layers \{[^}]*opacity: 0;[^}]*transition: opacity var\(--t-slow\)/, "the sky waits hidden, then one --t-slow fade");
assert.match(css, /\.sky-layers\[data-ready\] \{ opacity: 1; \}/);
const showBody = src.slice(src.indexOf("function show("), src.indexOf("\n}\n", src.indexOf("function show(")));
assert.ok(/pending\.size < IMAGE_LAYERS\.length\) return/.test(showBody), "no layer swaps in before all are decoded");
assert.ok(showBody.indexOf("backgroundImage") > showBody.indexOf("pending.size <") && /data-ready/.test(showBody), "reveal after the full set");
// graph zone (owner: "purple dust ... blurs the background"): no CSS mask follows the graph, and the dim is light only
assert.ok(!/mask-image/.test(css), "no mask on the sky layers: its soft hole smeared the band and jumped after a pan");
const skyGraphBody = src.slice(src.indexOf("export function skyGraph("), src.indexOf("\n}\n", src.indexOf("export function skyGraph(")));
assert.ok(!/setProperty|style/.test(skyGraphBody), "a pan or zoom changes nothing in the sky");
assert.ok(!/--halo:\s*rgb\(120 130 255/.test(css), "cluster halos are not indigo");
{
  const w = 240, h = 160, p = { side: 1 as const, shift: 0 }, zone = { x: 60, y: 40, w: 120, h: 80 };
  const ink: Ink = { core: [244, 163, 154], rose: [196, 122, 166], arm: [142, 147, 218], star: [247, 248, 248], deep: [1, 1, 2], band: 0.32, lane: 0.5, outside: 0.3, haze: 0.18, dust: 0.5, anchor: 0.7, grain: 0.03, hole: 0.2, holeStars: 0.6 };
  // composited over --night-lift, a pixel behind the graph must lie on the line from the band as rendered (P) to the band
  // with no light at all (K): a pure fade of the band's own light, adding no colour (chroma) of its own
  const plain = bandPixels(w, h, fields(w, h, p), ink), dim = bandPixels(w, h, fields(w, h, p, zone), ink), dark = bandPixels(w, h, fields(w, h, p), { ...ink, band: 0, haze: 0 }), body: RGB = [16, 23, 58];
  const over = (a: Uint8ClampedArray, i: number) => [0, 1, 2].map((c) => body[c] + (a[i + c] - body[c]) * (a[i + 3] / 255));
  let lit = 0;
  for (let i = 0; i < plain.length; i += 4) {
    const P = over(plain, i), D = over(dim, i), K = over(dark, i), c0 = [0, 1, 2].reduce((m, c) => (Math.abs(P[c] - K[c]) > Math.abs(P[m] - K[m]) ? c : m), 0);
    const s = Math.abs(P[c0] - K[c0]) < 1 ? 1 : (D[c0] - K[c0]) / (P[c0] - K[c0]);
    assert.ok(s > -0.02 && s < 1.02, `behind the graph the band only fades (px ${i / 4}: ${s})`);
    for (let c = 0; c < 3; c++) assert.ok(Math.abs(D[c] - (K[c] + s * (P[c] - K[c]))) <= 2, `no tint behind the graph (px ${i / 4}, channel ${c})`);
    if (s < 0.9) lit++;
  }
  assert.ok(lit > 0, "the zone does dim the band");
  const x = 2, y = 2, i = (y * w + x) * 4; // far outside the zone the band is untouched
  assert.deepEqual([...dim.subarray(i, i + 4)], [...plain.subarray(i, i + 4)]);
}
// render budget: the fields of a 1488x948 sky in well under 150 ms (Node, single thread)
{ const t0 = performance.now(); fields(1488, 948, { side: 1, shift: 0 }); const ms = performance.now() - t0; assert.ok(ms < 150, `fields ${ms | 0} ms`); }
console.log("sky:check ok");

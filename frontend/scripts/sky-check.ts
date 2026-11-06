// Sky settings logic and band geometry (docs/design/sky-pattern.md). Run: npm run sky:check
import { strict as assert } from "node:assert";
import { DEFAULTS, KEY, LAYERS, fieldKey, fromQuery, gain, load, parse, save } from "../src/graph/skySettings.ts";
import { bandAt, fbm } from "../src/graph/sky.ts";

// parse keeps only known, well-typed keys
assert.deepEqual(parse(null), DEFAULTS);
assert.deepEqual(parse("x"), DEFAULTS);
assert.deepEqual(parse({ band: false, strength: 2, evil: 1, grain: "yes" }), { ...DEFAULTS, band: false, strength: 2 });
assert.equal(parse({ strength: 3 }).strength, DEFAULTS.strength);
assert.equal(parse({ strength: "1" }).strength, DEFAULTS.strength);
// the recommended default: subtle, chart rings off
assert.equal(DEFAULTS.strength, 1);
assert.equal(DEFAULTS.graticule, false);
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

// dev override
assert.equal(fromQuery("none")!.strength, 0);
assert.equal(fromQuery("c")!.graticule, true);
assert.equal(fromQuery("a")!.band, false);
assert.equal(fromQuery("zzz"), null);
assert.equal(fromQuery(null), null);

// strength scales every layer; Off is zero
assert.equal(gain(0), 0);
assert.ok(gain(1) < gain(2));
// a chart-ring toggle never re-renders the deep field; any field change or Off does
assert.equal(fieldKey(DEFAULTS), fieldKey({ ...DEFAULTS, graticule: true }));
assert.notEqual(fieldKey(DEFAULTS), fieldKey({ ...DEFAULTS, band: false }));
assert.equal(fieldKey({ ...DEFAULTS, strength: 0 }), "off");

// noise is deterministic and in range
assert.equal(fbm(12.3, 4.5, 5), fbm(12.3, 4.5, 5));
for (let i = 0; i < 500; i++) { const v = fbm(i * 0.37, i * 0.11, 5); assert.ok(v >= 0 && v <= 1); }

// band geometry: the core bulge sits away from the map's middle, and the band dims behind the map
for (const [w, h] of [[1440, 900], [390, 844]]) {
  const mid = bandAt(0.56 * w, 0.48 * h, w, h), corner = bandAt(0.02 * w, 0.98 * h, w, h);
  assert.ok(mid.map < 0.5, `band dims behind the map at ${w}`);
  assert.ok(corner.map > 0.95);
  assert.ok(mid.bulge < 0.5, `the bulge is not behind the map at ${w}`);
}
console.log("sky:check ok");

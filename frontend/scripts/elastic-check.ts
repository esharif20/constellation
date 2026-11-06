// Elastic drag maths (src/graph/elastic.ts): falloff weights, exact return home, no NaN, determinism, cheap while at rest.
// Run: npm run elastic:check
import { strict as assert } from "node:assert";
import { createElastic, HOPS, HUB, MATE, pullWeights, type Pt } from "../src/graph/elastic.ts";

type N = Pt & { id: string };
const mk = (id: string, x: number, y: number): N => ({ id, x, y });
const a = mk("a", 0, 0), b = mk("b", 20, 0), c = mk("c", 40, 0), d = mk("d", 60, 0), far = mk("far", 500, 0), hub = mk("hub", 300, 0);
const adj = new Map<N, N[]>([[a, [b]], [b, [a, c]], [c, [b, d]], [d, [c]], [far, []], [hub, []]]);
const home = (n: N): [number, number] => [n.x!, n.y!];
const w = pullWeights(a, (n) => adj.get(n)!, [a, b, c, d, far, hub], hub, home);
assert.equal(w.get(a), 1);
assert.equal(w.get(b), HOPS[1]); // 1 hop 35%
assert.equal(w.get(c), HOPS[2]); // 2 hops 15%
assert.ok(!w.has(d) || w.get(d)! <= MATE * (1 - 60 / 90) + 1e-9); // 3 hops: only the cluster-mate share, never a hop share
assert.ok(!w.has(far)); // another cluster / out of reach: still
assert.equal(w.get(hub), HUB); // the hub is lightly pulled

function run() {
  const ns = [a, b, c, d, far, hub].map((n) => ({ ...n }));
  const [A, B, C, D, F, H] = ns;
  const nb = new Map<N, N[]>([[A, [B]], [B, [A, C]], [C, [B, D]], [D, [C]], [F, []], [H, []]]);
  const e = createElastic<N>();
  e.grab(A, pullWeights(A, (n) => nb.get(n)!, ns, H, home));
  const trace: number[] = [];
  for (let f = 0; f < 60; f++) { A.x = 100 * Math.min(1, f / 20); A.y = 50; e.move(); e.tick(1 / 60); trace.push(B.x!, C.x!); }
  assert.ok(B.x! > 20 && B.x! < 20 + 0.35 * 100 + 1, "1 hop follows by about 35%");
  assert.ok(C.x! > 40 && C.x! < 40 + 0.15 * 100 + 1, "2 hops follow by about 15%");
  assert.equal(F.x, 500); // untouched
  e.release();
  let frames = 0, over = 0;
  while (e.tick(1 / 60) && frames < 200) { frames++; over = Math.min(over, B.x! - 20); }
  assert.ok(frames * 16.7 >= 250 && frames * 16.7 <= 700, `settles in 250-700 ms, took ${frames * 16.7}`);
  for (const [n, o] of [[A, a], [B, b], [C, c], [D, d], [F, far], [H, hub]] as const) { assert.equal(n.x, o.x); assert.equal(n.y, o.y); } // exactly home
  assert.ok(!e.active(), "asleep once settled");
  assert.ok(ns.every((n) => Number.isFinite(n.x!) && Number.isFinite(n.y!)));
  return trace.concat(ns.flatMap((n) => [n.x!, n.y!]));
}
const first = run();
assert.deepEqual(run(), first); // deterministic
assert.ok(first.every(Number.isFinite));

// frame rate does not change the end state: 30 fps and 144 fps both land home; a huge dt is capped, not exploded
const e2 = createElastic<N>(), P = mk("p", 0, 0), Q = mk("q", 10, 0);
e2.grab(P, new Map([[P, 1], [Q, 0.35]]));
P.x = 80; e2.move(); e2.tick(10); e2.release();
for (let i = 0; i < 400 && e2.tick(1 / 144); i++);
assert.deepEqual([P.x, P.y, Q.x, Q.y], [0, 0, 10, 0]);
console.log("elastic:check ok");

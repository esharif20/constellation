// Layer-stack logic behind every overlay's dismissal (docs/design/dismiss.md). Pure functions plus the store driven by stub events.
// Run: npm run dismiss:check
import { strict as assert } from "node:assert";
import { backgroundTargets, escapeTarget, isTap, pressTargets, pushLayer, removeLayer, RANK, SLOP, type Layer } from "../src/lib/dismiss.ts";

const L = (id: string, rank: number, seq: number, extra: Partial<Layer> = {}): Layer => ({ id, rank, seq, close: () => {}, ...extra });

// click vs drag
assert.ok(isTap({ x: 10, y: 10 }, { x: 10, y: 10 }));
assert.ok(isTap({ x: 10, y: 10 }, { x: 10 + SLOP, y: 10 }));
assert.ok(!isTap({ x: 10, y: 10 }, { x: 10 + SLOP + 1, y: 10 }));
assert.ok(!isTap({ x: 0, y: 0 }, { x: 40, y: 3 })); // the end of a pan

// one transient at a time; docked layers coexist
let s: Layer[] = [];
let r = pushLayer(s, L("brief", RANK.brief, 1)); s = r.stack;
r = pushLayer(s, L("inspector", RANK.inspector, 2)); s = r.stack;
assert.deepEqual(r.replaced, []);
r = pushLayer(s, L("sky", RANK.popover, 3)); s = r.stack;
assert.deepEqual(r.replaced, []);
r = pushLayer(s, L("history", RANK.popover, 4)); s = r.stack;
assert.deepEqual(r.replaced.map((l) => l.id), ["sky"]);
assert.deepEqual(s.map((l) => l.id), ["brief", "inspector", "history"]);
r = pushLayer(s, L("ask", RANK.panel, 5)); s = r.stack;
assert.deepEqual(r.replaced.map((l) => l.id), ["history"]);
assert.equal(pushLayer(s, L("ask", RANK.panel, 6)).stack.length, s.length); // re-registering the same id does not duplicate or close itself
assert.deepEqual(pushLayer(s, L("ask", RANK.panel, 6)).replaced, []);

// Escape order: transient, then Inspector, then cluster card, then highlight, then Brief
assert.equal(escapeTarget(s)?.id, "ask");
s = removeLayer(s, "ask");
assert.equal(escapeTarget(s)?.id, "inspector");
s = removeLayer(s, "inspector");
s = pushLayer(s, L("cluster", RANK.cluster, 7)).stack;
s = pushLayer(s, L("highlight", RANK.highlight, 8)).stack;
assert.deepEqual([escapeTarget(s)?.id, escapeTarget(removeLayer(s, "cluster"))?.id], ["cluster", "highlight"]);
assert.equal(escapeTarget(removeLayer(removeLayer(s, "cluster"), "highlight"))?.id, "brief");
assert.equal(escapeTarget([]), undefined);
assert.equal(escapeTarget([L("a", 30, 1), L("b", 30, 2)])?.id, "b"); // ties: the later one

// outside press: only transients, only the ones not hit, and not the ones that opt out
const popover = L("sky", RANK.popover, 1), ask = L("ask", RANK.panel, 2, { press: false }), mode = L("scrub", RANK.panel, 3, { press: false, background: false }), docked = L("inspector", RANK.inspector, 4);
assert.deepEqual(pressTargets([popover, ask, mode, docked], () => false).map((l) => l.id), ["sky"]);
assert.deepEqual(pressTargets([popover], (l) => l.id === "sky"), []); // inside: the trigger or the content
assert.deepEqual(backgroundTargets([popover, ask, mode, docked]).map((l) => l.id), ["sky", "ask"]);

// the store, driven by stub window events
type H = (e: unknown) => void;
const handlers = new Map<string, H>();
const g = globalThis as Record<string, unknown>;
g.addEventListener = (t: string, h: H) => void handlers.set(t, h);
g.removeEventListener = (t: string) => void handlers.delete(t);
class Fake { contains(n: Fake): boolean { return n === this; } }
g.Node = Fake;
const { register, escape, background } = await import("../src/lib/dismiss.ts");
const content = new Fake(), trigger = new Fake(), canvas = new Fake();
const closed: string[] = [];
const log = (s: string): void => { (closed as string[]).push(s); }; // assert.deepEqual narrows `closed` to never[], so push through a helper
const ev = (type: string, x: number, y: number, target: Fake, pointerId = 1) => handlers.get(type)?.({ clientX: x, clientY: y, target, pointerId });
const tap = (target: Fake, x = 5, y = 5) => { ev("pointerdown", x, y, target); ev("pointerup", x, y, target); };

assert.equal(handlers.size, 0); // no listeners while nothing is open
const off = register({ id: "sky", rank: RANK.popover, close: (w) => log(`sky:${w}`), inside: () => [content, trigger] as unknown as Element[] });
assert.equal(handlers.size, 3);
tap(content); tap(trigger);
assert.deepEqual(closed, []); // inside, and the trigger toggles on its own: no flicker loop
ev("pointerdown", 100, 100, canvas); ev("pointermove", 160, 100, canvas); ev("pointerup", 160, 100, canvas);
assert.deepEqual(closed, []); // a pan ending outside closes nothing
ev("pointerdown", 100, 100, canvas); handlers.get("pointercancel")?.({}); ev("pointerup", 100, 100, canvas);
assert.deepEqual(closed, []); // a touch the browser took over (scroll) closes nothing
ev("pointerdown", 100, 100, content); ev("pointerup", 300, 300, canvas);
assert.deepEqual(closed, []); // pressed inside, released outside (text selection)
tap(canvas, 100, 100);
assert.deepEqual(closed, ["sky:press"]);
register({ id: "history", rank: RANK.popover, close: (w) => log(`history:${w}`) });
assert.deepEqual(closed.slice(1), ["sky:replace"]); // opening another closes the first
off();
assert.ok(escape());
assert.deepEqual(closed.slice(2), ["history:escape"]);
background();
assert.equal(closed.at(-1), "history:background");
const offAll = register({ id: "x", rank: RANK.popover, close: () => {} });
offAll();
assert.equal(handlers.size, 0); // listeners go when the stack is empty
console.log("Dismiss layer stack passes.");

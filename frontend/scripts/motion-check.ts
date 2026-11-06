// Motion system self-check, no browser: node scripts/motion-check.ts  (npm run motion:check)
// The shared durations, curves and distances stay in spec, reduced motion is opacity only, the CSS in index.css
// matches src/lib/motion.ts, and no Radix wrapper uses the base-ui `data-open` / `data-closed` hooks (Radix never sets them,
// which is why dialogs and popovers once popped in with no animation).
import { readFileSync, readdirSync } from "node:fs";
import { strict as assert } from "node:assert";
import { DISTANCE, EASE, MODAL_SCALE, MS, REDUCED_MS, exitMs, reducedMotion } from "../src/lib/motion.ts";

const read = (f: string) => readFileSync(new URL(f, import.meta.url), "utf8");
for (const [role, ms] of Object.entries(MS)) {
  assert.ok(ms.in >= 160 && ms.in <= 240, `${role} enter ${ms.in}ms is outside 160-240`);
  assert.ok(ms.out >= 120 && ms.out <= 180, `${role} exit ${ms.out}ms is outside 120-180`);
  assert.ok(ms.out < ms.in, `${role} exit must be shorter than its enter`);
}
assert.ok(DISTANCE.side >= 12 && DISTANCE.side <= 16, "side panels slide 12-16px");
assert.equal(MODAL_SCALE, 0.98);

const css = read("../src/index.css");
const at = css.indexOf("@media (prefers-reduced-motion");
const root = css.slice(0, at), reduced = css.slice(at, css.indexOf("@theme inline"));
const token = (name: string) => root.match(new RegExp(`--${name}:\\s*(\\d+)ms`))?.[1];
const pairs: [string, number][] = [["panel-in", MS.panel.in], ["panel-out", MS.panel.out], ["modal-in", MS.modal.in], ["modal-out", MS.modal.out], ["pop-in", MS.popover.in], ["pop-out", MS.popover.out]];
for (const [name, ms] of pairs) assert.equal(Number(token(`m-${name}`)), ms, `--m-${name} in index.css must equal src/lib/motion.ts`);
assert.ok(root.includes(`--ease-out: ${EASE.out}`) && root.includes(`--ease-in: ${EASE.in}`), "easing curves match index.css");
for (const [name] of pairs) assert.ok(new RegExp(`--m-${name}: ${REDUCED_MS}ms`).test(reduced), `reduced motion sets --m-${name} to ${REDUCED_MS}ms`);
assert.ok(/--tw-enter-scale: 1 !important/.test(reduced), "reduced motion removes Radix scale and slide");

// Panels: [data-pane] enter uses ease-out and the enter duration, the leaving state uses ease-in and the (shorter) exit; only transform and opacity move.
assert.ok(/\[data-pane\] \{[^}]*animation: pane-in var\(--m-panel-in\) var\(--ease-out\)/.test(css), "pane enters with --m-panel-in and ease-out");
assert.ok(/\[data-pane\]\[data-leaving\] \{ animation: pane-out var\(--m-panel-out\) var\(--ease-in\) forwards/.test(css), "pane leaves with --m-panel-out and ease-in");
const px = (sel: string, prop: string) => Number(css.match(new RegExp(`\\[data-pane="${sel}"\\] \\{ --${prop}: (-?\\d+)px`))?.[1]);
assert.deepEqual([px("left", "dx"), px("right", "dx"), px("top", "dy"), px("bottom", "dy")], [-DISTANCE.side, DISTANCE.side, -DISTANCE.chip, DISTANCE.chip]);
assert.ok(css.includes(`--dy: ${DISTANCE.sheet}px`), "phone sheets rise by DISTANCE.sheet");
for (const frame of css.match(/@keyframes pane-(in|out) \{[^\n]*/g) ?? []) assert.ok(/^@keyframes pane-\w+ \{ (from|to) \{ opacity: 0; transform: translate\(var\(--dx\), var\(--dy\)\); \} \}$/.test(frame), `pane keyframes animate opacity and transform only: ${frame}`);
assert.ok(/\[data-pane\] \{ --dx: 0px !important; --dy: 0px !important/.test(css), "reduced motion: panes only fade");
assert.ok(reduced.includes("[data-pane]), *::before"), "the blanket zero-duration rule leaves panes and Radix content to fade");

// The exit timer outlasts the exit it waits for, and a reduced-motion exit is the short fade.
assert.ok(exitMs("panel", false) > MS.panel.out && exitMs("panel", false) < MS.panel.in);
assert.equal(exitMs("panel", true), REDUCED_MS + 20);
assert.equal(reducedMotion(), false, "no matchMedia under node: motion stays on");

const dir = new URL("../src/components/ui/", import.meta.url);
for (const f of readdirSync(dir)) assert.ok(!/data-(open|closed):/.test(readFileSync(new URL(f, dir), "utf8")), `${f} uses data-open/data-closed; Radix sets data-[state=open|closed]`);
console.log("Motion system passes.");

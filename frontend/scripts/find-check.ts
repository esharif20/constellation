// When the "Find by what it does" list appears, and how a hit is shown (docs/design/inspector.md search box, #80).
// Run: npm run find:check
import { strict as assert } from "node:assert";
import { filtersActive, findQuery, findState, NO_FILTERS, oneLine, wantsFind } from "../src/graph/find.ts";
import { searchItems } from "../src/graph/search.ts";

const items = [
  { name: "shadcn", description: "Components for the UI", kind: "skill" },
  { name: "cabinet", description: "Assorted reference material", kind: "skill" },
];
const rows = (q: string) => searchItems(items, q, Infinity);

assert.ok(wantsFind(rows("typography for websites"), "typography for websites")); // no name matches
assert.ok(!wantsFind(rows("shadcn"), "shadcn")); // a name the user knew
assert.ok(!wantsFind(rows("shadnc"), "shadnc")); // a typo of a name: did-you-mean covers it
assert.ok(!wantsFind(rows("cabinet"), "cabinet"));
assert.ok(wantsFind([{ why: 'close to "deploy-preview"' }], "pull request review")); // a phrase is not a typo
assert.ok(!wantsFind([{ why: 'close to "cabinet"' }], "cabinat"));
assert.ok(wantsFind(rows("material"), "material")); // description-only match is not a name match
assert.ok(!wantsFind([], "ab")); // too short to search by meaning
assert.ok(!wantsFind([], "  a ")); // whitespace does not count

assert.equal(oneLine("a\n  b   c"), "a b c");
assert.equal(oneLine("x".repeat(200)).length, 110);
assert.ok(oneLine("x".repeat(200)).endsWith("…"));

const none = { available: true, results: [], note: null };
assert.equal(findState(false, null, false, 0), "off");
assert.equal(findState(true, null, true, 0), "loading");
assert.equal(findState(true, null, false, 0), "off"); // API absent
assert.equal(findState(true, { ...none, note: "Run constellation find" }, false, 0), "note");
assert.equal(findState(true, none, false, 0), "none");
assert.equal(findState(true, none, false, 2), "hits");
assert.equal(findQuery("a b", NO_FILTERS), "q=a%20b&kind=skill");
assert.equal(findQuery("x", { kind: "mcp", forgotten: true, origin: "plugin" }), "q=x&kind=mcp&forgotten=true&origin=plugin");
assert.equal(filtersActive(NO_FILTERS), false);
assert.equal(filtersActive({ ...NO_FILTERS, forgotten: true }), true);
console.log("find ok");

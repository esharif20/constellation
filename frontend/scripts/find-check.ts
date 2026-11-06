// When the "Find by what it does" list appears, and how a hit is shown (docs/design/inspector.md search box, #80).
// Run: npm run find:check
import { strict as assert } from "node:assert";
import { oneLine, wantsFind } from "../src/graph/find.ts";
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
assert.ok(wantsFind(rows("material"), "material")); // description-only match is not a name match
assert.ok(!wantsFind([], "ab")); // too short to search by meaning
assert.ok(!wantsFind([], "  a ")); // whitespace does not count

assert.equal(oneLine("a\n  b   c"), "a b c");
assert.equal(oneLine("x".repeat(200)).length, 110);
assert.ok(oneLine("x".repeat(200)).endsWith("…"));
console.log("find ok");

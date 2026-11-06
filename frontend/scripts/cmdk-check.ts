// The global search shortcut and its hint (#cmdk). Run: npm run cmdk:check
import { strict as assert } from "node:assert";
import { isSearchShortcut, searchHint } from "../src/graph/find.ts";

const e = (o: object) => ({ key: "k", metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...o });
assert.ok(isSearchShortcut(e({ metaKey: true })));
assert.ok(isSearchShortcut(e({ ctrlKey: true })));
assert.ok(isSearchShortcut(e({ ctrlKey: true, key: "K" }))); // caps lock
assert.ok(!isSearchShortcut(e({}))); // plain k is just typing
assert.ok(!isSearchShortcut(e({ metaKey: true, key: "j" })));
assert.ok(!isSearchShortcut(e({ metaKey: true, shiftKey: true }))); // leave browser/app chords alone
assert.ok(!isSearchShortcut(e({ ctrlKey: true, altKey: true })));
assert.equal(searchHint("MacIntel"), "⌘K");
assert.equal(searchHint("iPad"), "⌘K");
assert.equal(searchHint("Win32"), "Ctrl K");
assert.equal(searchHint(""), "Ctrl K");
console.log("cmdk ok");

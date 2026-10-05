import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import * as m from "../src/inventory.js";

test("sorted ascending", () => { const inv = m.createInventory(); ["salve", "key", "rope"].forEach(x => m.addItem(inv, x)); assert.deepEqual(m.sortedItems(inv), ["key", "rope", "salve"]); });
test("totalWeight", () => { const inv = m.createInventory(); ["lantern", "salve", "mystery"].forEach(x => m.addItem(inv, x)); assert.equal(m.totalWeight(inv), 5); });
test("full message", () => { const inv = m.createInventory(); for (let i = 0; i < 8; i++) m.addItem(inv, "key"); assert.throws(() => m.addItem(inv, "key"), { message: "Inventory full (8 slots)" }); });
test("legacyAdd removed", () => { assert.equal(m.legacyAdd, undefined); assert.ok(!fs.readFileSync(new URL("../src/inventory.js", import.meta.url), "utf8").includes("legacyAdd")); });
test("describe uses capacity", () => { const inv = m.createInventory(); m.addItem(inv, "key"); assert.equal(m.describe(inv), "1/8 slots used"); });
test("remove absent is no-op", () => { const inv = m.createInventory(); m.addItem(inv, "key"); m.removeItem(inv, "rope"); assert.deepEqual(inv.items, ["key"]); assert.equal(inv.updated, 1); });

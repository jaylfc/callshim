import test from "node:test";
import assert from "node:assert/strict";
import * as m from "../src/inventory.js";

test("capacity constant", () => { assert.equal(m.CAPACITY, 8); assert.equal(m.MAX_SLOTS, undefined); });
test("remove first item", () => {
  const inv = m.createInventory(); m.addItem(inv, "rope"); m.addItem(inv, "key");
  m.removeItem(inv, "rope"); assert.deepEqual(inv.items, ["key"]);
});

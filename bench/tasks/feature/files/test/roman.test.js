import { test } from "node:test";
import assert from "node:assert/strict";
import { toRoman, fromRoman } from "../src/roman.js";

test("toRoman basics", () => {
  assert.equal(toRoman(1), "I");
  assert.equal(toRoman(4), "IV");
  assert.equal(toRoman(1994), "MCMXCIV");
});
test("fromRoman basics", () => {
  assert.equal(fromRoman("XLII"), 42);
  assert.equal(fromRoman("MMMCMXCIX"), 3999);
});

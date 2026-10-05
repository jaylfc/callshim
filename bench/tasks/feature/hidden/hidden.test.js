import { test } from "node:test";
import assert from "node:assert/strict";
import { toRoman, fromRoman } from "../src/roman.js";

test("round trip 1..3999", () => { for (let n = 1; n <= 3999; n++) assert.equal(fromRoman(toRoman(n)), n); });
test("toRoman range and type", () => {
  for (const bad of [0, -1, 4000, 2.5, NaN, "5"]) assert.throws(() => toRoman(bad), RangeError);
});
test("fromRoman rejects non-canonical", () => {
  for (const bad of ["IIII", "VX", "IC", "", "xlii", "MMMM", "IIV", "VV"]) assert.throws(() => fromRoman(bad), SyntaxError);
});

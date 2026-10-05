import { test } from "node:test";
import assert from "node:assert/strict";
import { mean, median, mode, clampScore } from "../src/stats.js";

test("mean", () => { assert.equal(mean([1, 2, 3, 4]), 2.5); assert.equal(mean([]), 0); });
test("median odd and even, numeric order", () => {
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([10, 2, 33, 4]), 7);
  assert.equal(median([]), 0);
});
test("mode returns the smallest of tied values", () => {
  assert.equal(mode([1, 2, 2, 3, 3]), 2);
  assert.equal(mode([5, 4, 4, 5]), 4);
  assert.equal(mode([7]), 7);
});
test("clampScore", () => {
  assert.equal(clampScore(50), 50);
  assert.equal(clampScore(-5), 0);
  assert.equal(clampScore(150), 100);
  assert.equal(clampScore(15, 10, 20), 15);
});

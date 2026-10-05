import { test } from "node:test";
import assert from "node:assert/strict";
import { formatName } from "../src/names.js";

const p = { first: "Ada", last: "Lovelace" };
test("leaderboard form is the default", () => assert.equal(formatName(p), "Lovelace, Ada"));
test("HUD form", () => assert.equal(formatName(p, { display: true }), "Ada Lovelace"));
test("HUD form trims and handles a missing last name", () => {
  assert.equal(formatName({ first: " Ada ", last: "" }, { display: true }), "Ada");
  assert.equal(formatName({ first: "Ada", last: "" }), "Ada");
});

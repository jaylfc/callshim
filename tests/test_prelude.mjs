// Runs the omp browser prelude against mocks shaped like omp 18.4.4's frozen globals.
import fs from "node:fs";
import assert from "node:assert/strict";
const calls = [];
const makeTab = name => Object.freeze({
  name, toString: () => `<tab ${name}>`,
  evaluate: async f => (calls.push(["evaluate", name, String(f)]), "EVAL"),
  run: async (f, o) => (calls.push(["run", name, String(f)]), "RUN"),
  html: async (s) => (calls.push(["html", name, s]), "<html>"),
  screenshot: async () => "png",
});
globalThis.browser = Object.freeze({
  async open(o) { if (typeof o !== "object") throw new TypeError("browser.open() expects an options object"); calls.push(["open", o]); return makeTab(o.name ?? "main"); },
  tab(n = "main") { if (typeof n !== "string") throw new TypeError("browser.tab() expects a tab name"); return makeTab(n); },
  async tabs() { return []; }, async close() {},
});
globalThis.judge = async (state, questions) => {
  if (!questions || typeof questions !== "object" || Array.isArray(questions)) throw new TypeError("judge(state, questions) expects questions as an object keyed by id");
  calls.push(["judge", state, questions]); return { ok: true };
};
const logs = []; const origLog = console.log; console.log = (...a) => logs.push(a.join(" "));
eval(fs.readFileSync(new URL("../callshim/transforms/prelude_omp_browser.js", import.meta.url), "utf8"));
eval(fs.readFileSync(new URL("../callshim/transforms/prelude_omp_browser.js", import.meta.url), "utf8"));   // idempotent

// 1. positional open with viewport options
const t = await browser.open("http://localhost:8123/", { width: 390, height: 844 });
assert.deepEqual(calls.at(-1), ["open", { name: "main", url: "http://localhost:8123/", viewport: { width: 390, height: 844 } }]);
// 2. page code in tab.run (template IIFE) -> evaluate
await t.run(`(() => { const el = document.getElementById('game'); return [window.__err ?? 'none', el?.width]; })()`);
assert.equal(calls.at(-1)[0], "evaluate");
// 3. bare string with return -> wrapped IIFE
await t.run("const c = document.getElementById('game');\nreturn {w:c.width};");
assert.match(calls.at(-1)[2], /^\(\(\) => \{/);
// 4. real Bun-side run is kept
await t.run(async ({ page }) => page.$("canvas"));
assert.equal(calls.at(-1)[0], "run");
// 5. browser.tab({name}) and html({selector})
await browser.tab({ name: "pwa1" }).html({ selector: "body" });
assert.deepEqual(calls.at(-1), ["html", "pwa1", "body"]);
// 6. judge object form with string questions
await judge({ image: "/tmp/x.png", questions: { bands: "Is the left band red?" } });
assert.deepEqual(calls.at(-1), ["judge", "/tmp/x.png", { bands: { type: "bool", instructions: "Is the left band red?" } }]);
// 7. judge positional with prompt/options
await judge("two screenshots", { q1: { prompt: "Which screen?", options: ["intro", "title menu"] } });
assert.deepEqual(calls.at(-1)[2], { q1: { instructions: "Which screen?", criteria: { intro: null, "title menu": null }, type: "choice" } });
// 8. free-text describe gets a clear error
await assert.rejects(judge({ prompt: "Describe this screenshot", images: ["/tmp/a.png"] }), /read tool/);
// 9. correct shapes untouched
const before = logs.length;
await browser.open({ name: "x", url: "http://y" }); await judge("s", { a: { type: "bool", instructions: "ok?" } });
assert.equal(logs.length, before);
// 10. browser.goto / navigate from elicitation
await browser.goto("http://localhost:8201");
assert.deepEqual(calls.at(-1), ["open", { name: "main", url: "http://localhost:8201" }]);
console.log = origLog;
console.log("prelude ok;", logs.length, "translations logged:", [...new Set(logs)].join(" | ").slice(0, 300));

/* EBMS prelude for oh-my-pi's JS eval browser facade. Idempotent; wraps the frozen globals with translators
   for the shapes the model writes (lab experiments/004-ebms/failure-mining.md). Prints one "[ebms] ..." line
   per translation so runs can be audited. */
if (!globalThis.__ebms_browser && globalThis.browser) { globalThis.__ebms_browser = true; (() => {
  const B = globalThis.browser, J = globalThis.judge;
  const say = m => console.log("[ebms] " + m);
  const PAGE = /\b(document|window|getComputedStyle|innerWidth|innerHeight|localStorage|navigator\.|location\.)/;
  const BUN_ARGS = /^\s*(async\s*)?\(\s*\{[^)]*\b(page|tab|browser|wait|assert)\b/;
  const isPageCode = f => { const s = String(f); return PAGE.test(s) && !BUN_ARGS.test(s); };
  const asIife = s => { const t = s.trim();
    if (/^\(?\s*(async\s*)?(\(\s*\)|function\s*\()/.test(t) && /\)\s*\(\s*\)\s*;?$/.test(t)) return t;   // already an IIFE
    return /\breturn\b/.test(t) ? `(() => { ${t} })()` : t; };
  const wrapTab = t => {
    if (!t || t.__ebms) return t;
    const w = { ...t, __ebms: true, toString: () => String(t) };
    w.run = async (f, opts) => {
      if ((typeof f === "string" || typeof f === "function") && isPageCode(f)) {
        say("tab.run(page code) -> tab.evaluate (tab.run executes in Bun, where document/window do not exist)");
        return t.evaluate(typeof f === "string" ? asIife(f) : f);
      }
      return t.run(f, opts);
    };
    w.html = (sel, ...rest) => (sel && typeof sel === "object" && !Array.isArray(sel) && "selector" in sel)
      ? (say("tab.html({selector}) -> tab.html(selector)"), t.html(sel.selector, ...rest)) : t.html(sel, ...rest);
    return w;
  };
  const openArgs = (a, b) => {
    if (typeof a !== "string") return a;
    const o = { ...(b || {}) };
    const vp = o.viewport ?? (o.width && o.height ? { width: o.width, height: o.height } : undefined);
    delete o.width; delete o.height; delete o.viewport;
    say(`browser.open(url, opts) -> browser.open({name, url${vp ? ", viewport" : ""}})`);
    return { name: o.name ?? "main", url: a, ...o, ...(vp ? { viewport: vp } : {}) };
  };
  globalThis.browser = Object.freeze({
    async open(a, b) { return wrapTab(await B.open(openArgs(a, b))); },
    tab(n = "main") {
      if (n && typeof n === "object") { say("browser.tab({name}) -> browser.tab(name)"); n = n.name ?? "main"; }
      return wrapTab(B.tab(n));
    },
    // Elicitation: with no API docs the model writes browser.goto(url) / browser.navigate(url).
    async goto(a, b) { say("browser.goto(url) -> browser.open({url})"); return wrapTab(await B.open(openArgs(a, b))); },
    async navigate(a, b) { say("browser.navigate(url) -> browser.open({url})"); return wrapTab(await B.open(openArgs(a, b))); },
    tabs: (...x) => B.tabs(...x),
    close: (...x) => B.close(...x),
  });
  if (typeof J === "function") {
    const normQ = q => {
      if (typeof q === "string") return { type: "bool", instructions: q };
      if (!q || typeof q !== "object") return q;
      const out = { ...q };
      out.instructions = out.instructions ?? out.prompt ?? out.question ?? out.text;
      if (Array.isArray(out.options) && !out.criteria) out.criteria = Object.fromEntries(out.options.map(o => [String(o), null]));
      out.type = out.type ?? (out.criteria ? "choice" : "bool");
      for (const k of ["prompt", "question", "text", "options", "images", "image"]) delete out[k];
      return out;
    };
    const normQs = qs => Array.isArray(qs)
      ? Object.fromEntries(qs.map((q, i) => [`q${i + 1}`, normQ(q)]))
      : Object.fromEntries(Object.entries(qs).map(([k, q]) => [k, normQ(q)]));
    globalThis.judge = async (a, b) => {
      let state = a, qs = b;
      if (a && typeof a === "object" && !Array.isArray(a) && b === undefined) {
        state = a.state ?? a.image ?? (Array.isArray(a.images) ? a.images[0] : undefined) ?? a.prompt ?? a.context;
        qs = a.questions ?? (a.question ? { q1: a.question } : undefined);
        if (!qs) throw new Error("[ebms] judge(state, questions) needs questions, e.g. {fits: 'Does X fit?'}. For a free-text look at an image, use the read tool with <path>?q=<question>.");
        say("judge({...}) -> judge(state, questions)");
      }
      if (qs && typeof qs === "object") {
        const n = normQs(qs);
        if (JSON.stringify(n) !== JSON.stringify(qs)) say("judge questions normalised (prompt -> instructions, options -> criteria, type added)");
        qs = n;
      }
      return J(state, qs);
    };
  }
})(); }

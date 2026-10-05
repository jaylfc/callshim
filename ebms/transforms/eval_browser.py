"""Put the browser/judge translator prelude in front of oh-my-pi JS eval cells that use them.

The prelude (prelude_omp_browser.js) wraps the harness's own globals at runtime, so translation happens on
real values rather than by regex on code text. It is idempotent and prints one "[ebms] ..." line per
translation it makes. Python cells are left alone (their browser API shape already matches).
"""
from __future__ import annotations

import pathlib
import re

PRELUDE = (pathlib.Path(__file__).with_name("prelude_omp_browser.js")).read_text()
USES = re.compile(r"\bbrowser\.|\bjudge\s*\(|\.run\s*\(")


def apply(call: dict, ctx) -> dict:
    if call["name"] != "eval" or not isinstance(call["arguments"], dict):
        return call
    args = call["arguments"]
    code = args.get("code")
    lang = str(args.get("language") or "js").lower()
    if not isinstance(code, str) or lang not in ("js", "javascript", "ts", "typescript") or not USES.search(code):
        return call
    if "__ebms_browser" in code:
        return call
    ctx.note("eval_browser", code[:160], "(prelude added)", "browser/judge translator prelude")
    return {**call, "arguments": {**args, "code": PRELUDE + "\n" + code}}

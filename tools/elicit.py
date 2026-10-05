#!/usr/bin/env python3
"""callshim elicitation: ask the model to use vaguely described tools and record the call shapes it invents.

usage: tools/elicit.py BASE_URL MODEL [--samples 3] [--domains edit,browser] [--out FILE]
Production-like settings: medium effort, 3072 thinking budget, temperature 1.0 / top_p 0.95 / top_k 20.
One JSON line per sample: domain, task index, task, the tool-call arguments (or text if no call), timing.
Resumable: samples already in the output file are skipped.
"""
import argparse
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "elicit" / "tasks.json").read_text())
SYSTEM = "You are a coding agent. Use the tools provided to complete the user's request. Call a tool; do not just describe what you would do."


def ask(base, model, domain, task):
    if domain.startswith("open:"):
        # No tools in the request: the model writes the calls it expects, in its own format.
        body = {"model": model, "messages": [{"role": "system", "content": SPEC["open"]["system"]},
                                             {"role": "user", "content": task}],
                "max_tokens": 6144, "stream": False, "reasoning_effort": "medium", "reasoning_budget_tokens": 3072,
                "temperature": 1.0, "top_p": 0.95, "top_k": 20}
        return post(base, body)
    d = SPEC[domain]
    if domain == "edit":
        user = (f"File {d['file']}:\n```js\n{d['content']}```\n\n{task}\n\nUse the edit_file tool to make the change.")
    else:
        user = task + "\n\nUse the browser tool."
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "tools": [d["tool"]], "tool_choice": "auto", "max_tokens": 6144, "stream": False,
            "reasoning_effort": "medium", "reasoning_budget_tokens": 3072,
            "temperature": 1.0, "top_p": 0.95, "top_k": 20}
    return post(base, body)


def post(base, body):
    req = urllib.request.Request(f"{base}/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        out = json.load(r)
    msg = out["choices"][0]["message"]
    calls = [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]} for c in msg.get("tool_calls") or []]
    return {"calls": calls, "text": msg.get("content") or "", "reasoning": (msg.get("reasoning_content") or "")[-1500:], "reasoning_chars": len(msg.get("reasoning_content") or ""),
            "finish": out["choices"][0].get("finish_reason"), "wall_s": round(time.time() - t0, 1),
            "usage": out.get("usage")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("model")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--domains", default="open,edit,browser", help="open = every category in tasks.json 'open'")
    ap.add_argument("--out", default=str(ROOT / "results" / "local" / "elicit.jsonl"))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            done.add((r["domain"], r["task_i"], r["sample"]))
    for sample in range(a.samples):          # one pass over every task before the next sample
        for domain in [d for name in a.domains.split(",") for d in
                       ([f"open:{c}" for c in SPEC["open"]["categories"]] if name == "open" else [name])]:
            tasks = SPEC["open"]["categories"][domain[5:]] if domain.startswith("open:") else SPEC[domain]["tasks"]
            for i, task in enumerate(tasks):
                if (domain, i, sample) in done:
                    continue
                try:
                    res = ask(a.base, a.model, domain, task)
                except Exception as e:  # keep going; a failure is data too
                    res = {"error": repr(e)}
                row = {"domain": domain, "task_i": i, "sample": sample, "task": task,
                       "at": time.strftime("%FT%TZ", time.gmtime()), **res}
                with out.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                first = (res.get("calls") or [{}])[0].get("arguments", res.get("text", res.get("error", "")))
                print(f"{row['at']} {domain:7s} t{i:02d} s{sample} {res.get('wall_s', '-')}s  {str(first)[:110]!r}", flush=True)


if __name__ == "__main__":
    main()

# callshim

Expected-by-model tool-call shims (EBMS).

A model calls tools the way it learned to. When the harness expects something slightly different, the call fails, the model retries, and the session loses time. EBMS takes the opposite approach to prompt engineering:
1. Measure the tool shapes a model actually produces.
2. Translate them into the shapes the harness accepts.

It runs as an OpenAI-compatible proxy between any agent harness and any model server.

```
harness  ->  callshim proxy  ->  model server
              |  request: restore the model's own earlier calls in history, add defaults, strip extras
              |  response: buffer streamed tool calls, translate them, pass text and reasoning through
```

## Why a proxy
- **Harness-agnostic.** Every shim is a rewrite of the model's tool-call arguments, and the proxy sees all of them. It also sees the tool list the harness offers, so it can map an invented name (`read_file`, `Bash`, `list_files`) onto a real tool.
- **Prompt cache safe.** When a later request carries a rewritten call in its history, the proxy restores the model's original call. The model always sees its own tokens, and the server's prompt cache stays an exact prefix.
- **Auditable.** Every rewrite is logged with its before and after. A browser translation also prints one `[callshim] ...` line in the tool output.
- **Conservative.** A rewrite happens only for shapes known to be unambiguous. Anything else is left for the harness to report.

## Transforms
| Transform | What it fixes | Evidence |
| --- | --- | --- |
| `aliases` | Tool names the model invents, mapped onto offered tools. Argument names (`file_path` to `path`, `cmd` to `command`, `directory` to `cwd`). Line ranges (`start_line`/`end_line`, `offset`/`limit`) turned into `path:a-b`. Glob pattern joins. String values coerced to the schema's types. | Open-mode elicitation: with no tool list, the model calls `read_file{path,start_line,end_line}`, `list_files`, `glob{pattern}`, ... |
| `hashline` | Near-miss op headers in oh-my-pi's hash-anchored edit (`PUT 2*:=4:` becomes `PUT 2.=4:`, `PUT 12+:` becomes `PUT >12:`, ...). Literal `\n` bodies. Bare `[HASH]` headers, given the path learned from tool results. | 135 failed edits of 563 |
| `eval_browser` | A runtime prelude for oh-my-pi's JS eval browser facade. It handles Puppeteer-style `browser.open(url, {width,height})`, page code passed to `tab.run`, `browser.tab({name})`, `tab.html({selector})`, and the `judge()` object form. | 146 failed eval calls of 376 |

Profiles (`profiles/*.json`) choose the transforms per model and harness, and can add tool aliases and request defaults, such as sampling fields for a harness that cannot send them.

## Only validated shims run
A shim can also hurt: one report found that a repair proxy lowered a small model's tool-call score. So every transform in a profile carries a validation status for that exact model and harness:

```json
"validation": {"hashline": {"status": "validated", "evidence": "A/B: 36 runs, edit errors 24% -> 9%, pass rate unchanged"}}
```

- The proxy applies only `validated` transforms.
- `--experimental` also runs `experimental` ones, and is meant for A/B tests.
- A transform becomes `validated` only after an A/B on that model + harness shows it helps and does no harm.
- Published profiles contain only validated model/harness combinations.

## Use
```
python -m callshim.proxy --upstream http://127.0.0.1:8080 --listen 127.0.0.1:8090 \
    --profile profiles/qwen3.8-flash-next-coder.json --state callshim-state.json --log callshim-log.jsonl
```
Point the harness's base URL at `http://127.0.0.1:8090/v1`.
- `--off`: everything passes through unchanged, which gives an A/B baseline through the same proxy.
- `--experimental`: also runs transforms not yet validated for this model + harness.

## Finding a model's expected shapes
- `tools/elicit.py` asks the model to use deliberately vague tools, or none at all, and records what it calls.
- The failure-mining notes in the omp-strata lab show how to classify a harness's failed calls.

## Tests
```
python -m unittest discover tests      # transform units + end-to-end proxy with a fake streaming upstream
node tests/test_prelude.mjs            # browser prelude against mocks shaped like oh-my-pi 18.4.4
```

## Status
v0.1, 2026-10-05. Built from one model (Qwen3.8-Flash-Next Coder) on one harness (oh-my-pi). A before/after A/B test on that stack is next. Every transform in the one profile is still `experimental`; the A/B is running. Private until the numbers say whether it works.

# A/B testing callshim on your harness and model

callshim runs a transform only when an A/B test on that exact model and harness shows it helps. This guide shows how to run that test on your own setup and submit the result, so profiles can cover more combinations than any one person can test.

## What you need
- A local OpenAI-compatible model server: llama.cpp, LM Studio, Ollama, vLLM, Strata, ...
- An agent harness that can:
  - point at a custom OpenAI-compatible base URL;
  - run one prompt non-interactively in a given directory, with tools auto-approved.
- Python 3.11+, Node 20+ (the bench tasks are small Node projects) and git.
- About 1–3 hours of machine time for the default run: 4 tasks × 2 arms × 2 reps.

## 1. Point the harness at the proxy, once
The runner starts the proxy on `127.0.0.1:8090` (`--proxy-port` to change), in front of your server. Configure the harness's base URL as `http://127.0.0.1:8090/v1` and leave it there; every arm uses the same harness config.

| Harness | Where the base URL goes (check your version's docs) |
| --- | --- |
| oh-my-pi / pi | `models.yml` provider `baseUrl: http://127.0.0.1:8090/v1` |
| opencode | provider `options.baseURL` in `opencode.json` |
| aider | `--openai-api-base http://127.0.0.1:8090/v1` |
| Hermes agent | the named provider's `base_url` in `~/.hermes/config.yaml` |
| mini-swe-agent / anything using LiteLLM | `api_base` for an `openai/<model>` model |
| others | `OPENAI_BASE_URL=http://127.0.0.1:8090/v1` often works |

Keep everything else fixed across the run: model, quantization, sampling, context size and thinking settings. Write them down for the `--settings` flag.

## 2. Pick or write a profile
- **Your model and harness pair has a profile in `profiles/`:** use it.
- **No profile yet:** copy the closest one, set `model` and `harness`, and leave every transform `experimental`.
- **Find what your model expects first:**
  ```
  python tools/elicit.py http://127.0.0.1:8080/v1 <model-id> --samples 3
  ```
  This asks the model to use deliberately vague tools, or none, and records the names, argument keys and code it produces. It writes `results/local/elicit.jsonl`.

## 3. Run the A/B
```
python tools/ab.py \
  --harness-cmd '<your harness one-shot command, using {prompt_q} and {cwd}>' \
  --upstream http://127.0.0.1:8080 \
  --profile profiles/<profile>.json \
  --model '<model id + quant>' --harness '<harness + version>' --server '<server + version>' \
  --hardware '<GPU / RAM>' --settings '<sampling, thinking, context>' \
  --arms off,on --reps 2 --minutes 20
```

Placeholders in `--harness-cmd`:

| Placeholder | Replaced with |
| --- | --- |
| `{prompt}` | the raw prompt |
| `{prompt_q}` | the prompt, shell-quoted |
| `{prompt_file}` | a file holding the prompt |
| `{cwd}` | the task's working copy (also the command's working directory) |
| `{minutes}`, `{seconds}` | the time limit |
| `{run_dir}` | a folder for anything the harness writes |

The command runs in its own process group and is killed at the time limit.

Example harness commands (adapt them to your version):
```
# oh-my-pi
omp --profile=<yours> -p {prompt_q} --cwd {cwd} --auto-approve --no-title --max-time {minutes}m
# Hermes agent
hermes chat --query-file {prompt_file} --oneshot --yolo --in {cwd} --max-turns 300
# aider
aider --yes-always --no-auto-commits --message {prompt_q}
```

**Arms:**

| Arm | What the proxy does |
| --- | --- |
| `off` | Forwards everything, counts tool calls, translates nothing. This is the baseline. |
| `on` | Every transform in the profile. |
| `only:<name>` | One transform at a time, for example `--arms off,on,only:aliases,only:hashline`. Use these to find which transforms help and which hurt. |

**Tasks:** `bugfix`, `feature`, `looptrap` and `multiedit` (the default set). Add `browserprobe` if your harness has a browser tool. Each task is a small git repo plus a scoring script. A run passes when the script passes; the tests the model must not change are checked.

## 4. Read the result
`results/local/<stamp>/summary.md` shows, for each arm:
- pass rate;
- median time;
- tool calls per run;
- rewritten calls per run.

It also has a task × arm table. `runs/<task>-<arm>-r<rep>/` holds each run's harness log and its proxy log, with every rewrite before and after.

A transform helps when the `on` arm (or its `only:` arm):
- has a pass rate no lower than `off`;
- takes less time or fewer turns.

Rewrites that do nothing are harmless but useless. Rewrites alongside new failures mean it must stay off for this pair.

Two reps is a smoke test, not proof. Use 3–5 reps before marking anything validated.

## 5. Submit
`results/local/<stamp>/submission.json` has:
- the model, harness, server, hardware and settings you gave;
- the profile's name and hash, and the callshim commit;
- per-arm totals and per-run rows.

It contains no paths or hostnames, but read it before you share it.

Open a pull request that adds the file as `results/submissions/<date>-<model>-<harness>.json`. If your result supports validating a transform for your pair, include the profile change in the same PR:

```json
"validation": {"hashline": {"status": "validated", "evidence": "results/submissions/20261005-<model>-<harness>.json: off 7/8 vs on 8/8, edit failures 6 -> 1"}}
```

A maintainer reruns or spot-checks before merging a `validated` status.

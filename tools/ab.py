#!/usr/bin/env python3
"""A/B test callshim transforms on your own harness + model, then write a shareable result.

Point your harness's OpenAI-compatible base URL at the proxy (http://127.0.0.1:PROXY_PORT/v1) once. Each
arm restarts the proxy in a different mode, so the harness configuration never changes between arms:

  off            the proxy forwards and counts calls but transforms nothing (baseline)
  on             every transform in the profile (--experimental)
  only:NAME      one transform at a time (ablation), e.g. only:aliases

usage:
  python tools/ab.py --harness-cmd 'omp -p {prompt_q} --cwd {cwd} --auto-approve --max-time {minutes}m' \\
      --upstream http://127.0.0.1:8080 --profile profiles/qwen3.8-flash-next-coder.json \\
      --model qwen3.8-flash-next-coder-iq1_m --harness 'oh-my-pi 18.4.4' --server 'Strata 0.1.39' \\
      --hardware 'RTX 3060 12GB, 78GB DDR4' --arms off,on --reps 2 --minutes 20

Placeholders in --harness-cmd: {prompt} (raw), {prompt_q} (shell-quoted), {prompt_file}, {cwd}, {minutes},
{seconds}, {run_dir}. The command runs with cwd={cwd} in its own process group and is killed at the time limit.
Output: results/local/<stamp>/runs.jsonl, summary.md and submission.json (no paths or hostnames).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS = ROOT / "bench" / "tasks"


def wait_port(port: int, timeout: float = 15) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"nothing listening on port {port}")


def start_proxy(a, arm: str, log: pathlib.Path) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "callshim.proxy", "--upstream", a.upstream, "--listen", f"127.0.0.1:{a.proxy_port}",
           "--profile", a.profile, "--log", str(log), "--state", str(log.with_suffix(".state.json"))]
    if arm == "off":
        cmd.append("--off")
    elif arm == "on":
        cmd.append("--experimental")
    elif arm.startswith("only:"):
        cmd += ["--transforms", arm[5:]]
    else:
        raise SystemExit(f"unknown arm {arm!r}")
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_port(a.proxy_port)
    return proc


def stop(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def proxy_counts(log: pathlib.Path) -> dict:
    calls, rewritten, restores = 0, 0, 0
    by = collections.Counter()
    tools = collections.Counter()
    if log.exists():
        for line in log.read_text().splitlines():
            e = json.loads(line)
            if e["kind"] == "call":
                calls += 1
                tools[e["tool"]] += 1
                rewritten += e["rewritten"]
            elif e["kind"] == "rewrite":
                for t in {n["transform"] for n in e["notes"]}:   # calls touched per transform, not notes
                    by[t] += 1
            elif e["kind"] == "restore":
                restores += 1
    return {"tool_calls": calls, "rewritten_calls": rewritten, "rewrites_by_transform": dict(by),
            "history_restores": restores, "tools": dict(tools)}


def run_one(a, task: str, arm: str, rep: int, out: pathlib.Path) -> dict:
    tdir = TASKS / task
    run_dir = out / "runs" / f"{task}-{arm.replace(':', '_')}-r{rep}"
    work = run_dir / "work"
    shutil.copytree(tdir / "files", work)
    git("init", "-q", cwd=work)
    git("add", "-A", cwd=work)
    git("-c", "user.name=bench", "-c", "user.email=bench@callshim", "commit", "-qm", "task start", cwd=work)
    prompt = (tdir / "prompt.txt").read_text()
    (run_dir / "prompt.txt").write_text(prompt)
    fill = {"prompt": prompt, "prompt_q": shlex.quote(prompt), "prompt_file": str(run_dir / "prompt.txt"),
            "cwd": str(work), "minutes": str(a.minutes), "seconds": str(a.minutes * 60), "run_dir": str(run_dir)}
    cmd = a.harness_cmd.format(**fill)
    server = None
    if (tdir / "serve.txt").exists():
        server = subprocess.Popen([sys.executable, "-m", "http.server", (tdir / "serve.txt").read_text().strip(),
                                   "--bind", "127.0.0.1", "--directory", str(work)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    log = run_dir / "proxy.jsonl"
    proxy = start_proxy(a, arm, log)
    t0 = time.time()
    with open(run_dir / "harness.log", "w") as hl:
        proc = subprocess.Popen(cmd, shell=True, cwd=work, stdout=hl, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=a.minutes * 60 + 60)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(20)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            rc = "timeout"
    wall = time.time() - t0
    stop(proxy)
    stop(server)
    score = subprocess.run(["bash", str(tdir / "score.sh"), str(work), str(tdir)], capture_output=True, text=True)
    commits = int((git("rev-list", "--count", "HEAD", cwd=work).stdout.strip() or "1")) - 1
    row = {"task": task, "arm": arm, "rep": rep, "pass": score.returncode == 0, "wall_s": round(wall, 1),
           "exit": rc, "commits": commits, **proxy_counts(log),
           "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    print(f"{row['at']} {task:12s} {arm:16s} r{rep} pass={row['pass']!s:5s} {wall / 60:5.1f} min "
          f"calls={row['tool_calls']} rewritten={row['rewritten_calls']}", flush=True)
    return row


def summarize(rows: list[dict], arms: list[str]) -> tuple[str, dict]:
    per = {}
    lines = ["| Arm | Pass | Median time (min) | Tool calls / run | Rewritten calls / run |", "| --- | --- | --- | --- | --- |"]
    for arm in arms:
        r = [x for x in rows if x["arm"] == arm]
        if not r:
            continue
        per[arm] = {"runs": len(r), "pass": sum(x["pass"] for x in r),
                    "median_wall_s": statistics.median(x["wall_s"] for x in r),
                    "tool_calls_per_run": round(sum(x["tool_calls"] for x in r) / len(r), 1),
                    "rewritten_per_run": round(sum(x["rewritten_calls"] for x in r) / len(r), 1)}
        p = per[arm]
        lines.append(f"| {arm} | {p['pass']}/{p['runs']} | {p['median_wall_s'] / 60:.1f} | {p['tool_calls_per_run']} | {p['rewritten_per_run']} |")
    tasks = sorted({x["task"] for x in rows})
    lines += ["", "| Task | " + " | ".join(arms) + " |", "| --- |" + " --- |" * len(arms)]
    for t in tasks:
        cells = []
        for arm in arms:
            r = sorted((x for x in rows if x["task"] == t and x["arm"] == arm), key=lambda x: x["rep"])
            cells.append(" / ".join(f"{x['wall_s'] / 60:.1f}{'' if x['pass'] else ' FAIL'}" for x in r))
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    return "\n".join(lines), per


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--harness-cmd", required=True)
    ap.add_argument("--upstream", required=True, help="your model server, e.g. http://127.0.0.1:8080")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--proxy-port", type=int, default=8090)
    ap.add_argument("--arms", default="off,on")
    ap.add_argument("--tasks", default="bugfix,feature,looptrap,multiedit", help="add browserprobe if your harness has a browser tool")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--model", required=True)
    ap.add_argument("--harness", required=True, help="name and version, e.g. 'oh-my-pi 18.4.4'")
    ap.add_argument("--server", default="", help="e.g. 'llama.cpp b11415', 'Strata 0.1.39', 'LM Studio 1.1.7'")
    ap.add_argument("--hardware", default="")
    ap.add_argument("--settings", default="", help="sampling/thinking settings used, free text")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    arms = a.arms.split(",")
    tasks = a.tasks.split(",")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = pathlib.Path(a.out or ROOT / "results" / "local" / stamp)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    rows = []
    for rep in range(1, a.reps + 1):
        for i, task in enumerate(tasks):
            order = arms if (rep + i) % 2 else list(reversed(arms))   # alternate arm order to spread drift
            for arm in order:
                row = run_one(a, task, arm, rep, out)
                rows.append(row)
                with (out / "runs.jsonl").open("a") as f:
                    f.write(json.dumps(row) + "\n")
    table, per = summarize(rows, arms)
    (out / "summary.md").write_text(f"# callshim A/B: {a.model} on {a.harness}\n\n{table}\n")
    profile_text = pathlib.Path(a.profile).read_text()
    submission = {
        "schema": "callshim-ab/1", "date": stamp[:8], "callshim_commit": git("rev-parse", "--short", "HEAD", cwd=ROOT).stdout.strip(),
        "model": a.model, "harness": a.harness, "server": a.server, "hardware": a.hardware, "settings": a.settings,
        "profile": {"name": json.loads(profile_text).get("name"), "sha256": hashlib.sha256(profile_text.encode()).hexdigest()[:16]},
        "arms": per, "minutes_limit": a.minutes, "runs": [{k: v for k, v in r.items() if k != "at"} for r in rows],
    }
    (out / "submission.json").write_text(json.dumps(submission, indent=1))
    print("\n" + table + f"\n\nwrote {out}/summary.md and submission.json")


if __name__ == "__main__":
    main()

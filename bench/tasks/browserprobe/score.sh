#!/usr/bin/env bash
# usage: score.sh WORKDIR TASKDIR. Pass: report.json has the right values (and is committed).
cd "$1" || exit 1
git ls-files --error-unmatch report.json >/dev/null 2>&1 || { echo "report.json not committed"; exit 1; }
node -e '
const r = JSON.parse(require("fs").readFileSync("report.json", "utf8"));
const ok = r.title === "Lantern Run" && Array.isArray(r.canvas_css) && r.canvas_css[0] === 480 && r.canvas_css[1] === 360
  && r.overlap === true && Number(r.hp) === 37 && Number(r.console_errors) === 1;
if (!ok) { console.log("wrong:", JSON.stringify(r)); process.exit(1); }'

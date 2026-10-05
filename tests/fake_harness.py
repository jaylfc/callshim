#!/usr/bin/env python3
"""A stand-in harness for testing tools/ab.py without a model: one tool-call round trip through the proxy,
then a known-good fix for the bugfix task and a commit."""
import json
import os
import subprocess
import sys
import urllib.request

cwd = sys.argv[1]
port = os.environ.get("CALLSHIM_PORT", "8090")
body = {"model": "m", "stream": True, "messages": [{"role": "user", "content": "fix it"}],
        "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]}
req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=10) as r:
    r.read()
src = os.path.join(cwd, "src", "stats.js")
with open(src) as f:
    s = f.read()
s = s.replace("const s = [...xs].sort();\n  const mid = Math.floor(s.length / 2);\n  return s[mid];",
              "const s = [...xs].sort((a, b) => a - b);\n  const mid = Math.floor(s.length / 2);\n  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;")
s = s.replace("if (c >= bestCount)", "if (c > bestCount || (c === bestCount && x < best))")
s = s.replace("Math.min(x, lo)", "Math.min(x, hi)")
with open(src, "w") as f:
    f.write(s)
subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "fix"], cwd=cwd)

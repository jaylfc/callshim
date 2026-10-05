"""Repairs for oh-my-pi's hash-anchored edit ("hashline") input.

From 135 failed edits (lab experiments/004-ebms/failure-mining.md): the model keeps the format but writes
near-miss op headers, puts the body on the header line with literal "\\n", or omits the path from the
"[path#HASH]" header. Only those shapes are rewritten. Stale or foreign hashes and edits to lines the model
never displayed are left for the harness to report: guessing there could edit the wrong lines.
"""
from __future__ import annotations

import re

OP = re.compile(r"^(PUT|CUT)\s+(\d+)\s*([.*+]?)\s*(:?)\s*(?:=\s*(\d+)?)?\s*(:?)\s*$")
VALID = re.compile(r"^(?:PUT\s+(?:\d+\.=\d+:|\d+:|[<>]\d+:?|\d+\*:|\d+-\d+:|\d+\.:|\d+=\d+:|>\d+(?:\s+@\w+)?|\d+\.=\d+\s+@\w+)"
                   r"|CUT\s+(?:\d+\.=\d+:?|\d+:?|\d+\*))\s*$")
BARE_HASH = re.compile(r"^\[([0-9A-Fa-f]{3,8})\]\s*$")


def fix_op(line: str) -> str | None:
    """Return the repaired header for a known near-miss, or None when the line is fine or unknown."""
    stripped = line.strip()
    if VALID.match(stripped):
        return None
    m = OP.match(stripped)
    if not m:
        return None
    op, a, mark, _c1, b, _c2 = m.groups()
    if op == "CUT":
        return f"CUT {a}.={b}" if b and b != a else f"CUT {a}"
    if mark == "+" and not b:
        return f"PUT >{a}:"
    if b:
        return f"PUT {a}.={b}:"          # "1.:=3:", "2*:=4:", "7:=8:" all mean replace a..b
    if mark == "*":
        return f"PUT {a}*:"              # "4*=" means replace the block that opens on line 4
    return None


def apply(call: dict, ctx) -> dict:
    if call["name"] != "edit" or not isinstance(call["arguments"], dict):
        return call
    text = call["arguments"].get("input")
    if not isinstance(text, str):
        return call
    fixed = text
    # Body written on the header line with literal \n escapes.
    if fixed.count("\n") <= 1 and "\\n+" in fixed:
        fixed = fixed.replace("\\n", "\n")
        ctx.note("hashline", text, fixed, "unescaped literal \\n body")
    lines = fixed.split("\n")
    # "[HASH]" with no path: fill the path from the read or edit that issued the tag.
    if lines and BARE_HASH.match(lines[0].strip()):
        tag = BARE_HASH.match(lines[0].strip()).group(1).upper()
        path = ctx.state.hash_paths.get(tag)
        if path:
            ctx.note("hashline", lines[0], f"[{path}#{tag}]", "path added to a bare hash header")
            lines[0] = f"[{path}#{tag}]"
    for i, line in enumerate(lines):
        if line.startswith("+"):
            continue
        repaired = fix_op(line)
        # A colonless "PUT A.=B" is omp's clipboard form; it only means "replace with these rows" when body rows
        # follow. Without a body, adding ":" would turn it into a delete, so leave it for omp to explain.
        if repaired and repaired.startswith("PUT") and not line.rstrip().endswith(":") and "=" in line:
            if not (i + 1 < len(lines) and lines[i + 1].startswith("+")):
                continue
        if repaired:
            ctx.note("hashline", line, repaired, "op header repaired")
            lines[i] = repaired
    fixed = "\n".join(lines)
    if fixed == text:
        return call
    return {**call, "arguments": {**call["arguments"], "input": fixed}}

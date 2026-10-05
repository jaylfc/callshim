"""Tool-name and argument aliases, plus type coercion.

The model calls the tools it was trained with (read_file, Bash, list_files, WebSearch, ...). When that name is
not one the harness offered, map it onto an offered tool, rename the arguments it knows, and coerce string
values to the schema's types (Qwen's XML tool calls send every argument as a string). A rename is kept only
when the result has every required parameter of the target tool; otherwise the call is left unchanged.
"""
from __future__ import annotations

import json

# Harness tool name -> names a model may use for it. A profile can extend or override these.
TOOL_ALIASES = {
    "read": ["read_file", "readfile", "view", "view_file", "open_file", "cat", "file_read", "get_file", "show_file", "read_many_files"],
    "write": ["write_file", "writefile", "create_file", "save_file", "file_write", "create"],
    "edit": ["edit_file", "update_text_file", "replace", "str_replace", "str_replace_editor", "apply_edit", "modify_file", "multiedit"],
    "bash": ["run_shell_command", "shell", "execute_bash", "execute_shell", "terminal", "run_command", "execute_command", "exec", "sh", "run"],
    "grep": ["search", "search_file_content", "grep_search", "find_in_files", "ripgrep", "rg", "code_search", "search_code"],
    "glob": ["list_files", "list_dir", "list_directory", "ls", "find_files", "file_search", "glob_files", "list"],
    "find": ["list_files", "list_dir", "list_directory", "ls", "find_files", "file_search"],
    "web_search": ["websearch", "google_web_search", "search_web", "internet_search", "tavily_search", "brave_search", "google_search"],
    "fetch": ["web_fetch", "webfetch", "fetch_url", "http_get", "browse", "open_url"],
    "read@url": ["web_fetch", "webfetch", "fetch_url", "http_get", "browse", "open_url"],   # harnesses that read URLs
    "todo": ["todowrite", "todo_write", "write_todos", "update_plan"],
    "task": ["agent", "invoke_agent", "spawn_agent", "delegate", "subagent"],
}

# Argument name -> names a model may use for it.
ARG_ALIASES = {
    "path": ["file_path", "absolute_path", "filepath", "filename", "file", "target_file", "dir_path", "directory", "dir", "folder", "url"],
    "command": ["cmd", "script", "shell_command", "bash_command", "commands"],
    "cwd": ["workdir", "working_directory", "directory", "dir"],
    "pattern": ["regex", "search_pattern", "query", "search", "glob"],
    "content": ["text", "file_text", "contents", "data", "body"],
    "old_string": ["context", "old_str", "search", "find", "original", "old_text"],
    "new_string": ["replacement", "new_str", "replace", "new_text", "updated"],
    "query": ["q", "search_query", "search_term", "prompt"],
    "timeout": ["timeout_ms", "timeout_seconds"],
}

RANGE_START = ("start_line", "line_start", "from_line", "startLine", "offset", "start")
RANGE_END = ("end_line", "line_end", "to_line", "endLine", "end")
RANGE_LIMIT = ("limit", "count", "num_lines")


def _offered(name: str, tools: dict) -> str | None:
    if name in tools:
        return name
    low = {t.lower(): t for t in tools}
    return low.get(name.lower())


def _target_tool(name: str, tools: dict, profile: dict) -> str | None:
    direct = _offered(name, tools)
    if direct:
        return direct
    table = {**TOOL_ALIASES, **profile.get("tool_aliases", {})}
    key = name.lower()
    for target, names in table.items():
        if key == target or key in (n.lower() for n in names):
            hit = _offered(target.split("@")[0], tools)
            if hit:
                return hit
    return None


def _unwrap(name: str, args):
    """Wrappers the model invents: call_generic{tool, arguments}, or {"arguments": {...}} inside the real call."""
    name = name.strip()
    if isinstance(args, dict) and name.lower() in ("call_generic", "call_tool", "use_tool", "invoke_tool") \
            and isinstance(args.get("tool"), str) and isinstance(args.get("arguments"), dict):
        return args["tool"].strip(), args["arguments"]
    if isinstance(args, dict) and set(args) == {"arguments"} and isinstance(args["arguments"], dict):
        return name, args["arguments"]
    return name, args


def _coerce(value, schema: dict):
    kind = schema.get("type")
    if not isinstance(value, str) or kind in (None, "string"):
        return value
    text = value.strip()
    try:
        if kind == "integer":
            return int(float(text))
        if kind == "number":
            return float(text)
        if kind == "boolean" and text.lower() in ("true", "false"):
            return text.lower() == "true"
        if kind in ("array", "object") and text[:1] in "[{":
            return json.loads(text)
    except (ValueError, json.JSONDecodeError):
        pass
    return value


def _fit_args(args: dict, schema: dict, tool: str, ctx, call_name: str) -> dict:
    props = schema.get("properties") or {}
    out = dict(args)
    # Line ranges: fold start/end or offset/limit into "path:a-b" when the tool takes no range arguments.
    if "path" in props and not any(k in props for k in RANGE_START + RANGE_END + RANGE_LIMIT):
        start = next((out.pop(k) for k in RANGE_START if k in out), None)
        end = next((out.pop(k) for k in RANGE_END if k in out), None)
        limit = next((out.pop(k) for k in RANGE_LIMIT if k in out), None)
        path_key = next((k for k in ["path", *ARG_ALIASES["path"]] if k in out), None)
        if path_key and (start is not None or end is not None or limit is not None):
            try:
                a = int(start) if start is not None else 1
                b = int(end) if end is not None else (a + int(limit) - 1 if limit is not None else None)
                rng = f"{a}-{b}" if b is not None else f"{a}-"
                ctx.note("aliases", args, None, f"{call_name}: line range -> path suffix :{rng}")
                out[path_key] = f"{out[path_key]}:{rng}"
            except (TypeError, ValueError):
                pass
    for canonical, names in ARG_ALIASES.items():
        if canonical in props and canonical not in out:
            for n in names:
                if n in out and n not in props:
                    out[canonical] = out.pop(n)
                    break
    # glob-style tools that take the pattern in `path`: join a directory and a pattern.
    if tool in ("glob", "find") and "pattern" not in props and "pattern" in out:
        pattern = str(out.pop("pattern"))
        base = str(out.get("path") or "").rstrip("/")
        out["path"] = f"{base}/{pattern}" if base and not pattern.startswith("/") else pattern
    # bash timeouts given in milliseconds.
    if tool == "bash" and "timeout_ms" in args and "timeout" in out:
        try:
            out["timeout"] = max(1, round(float(out["timeout"]) / 1000))
        except (TypeError, ValueError):
            pass
    for key, sub in props.items():
        if key in out:
            out[key] = _coerce(out[key], sub)
    return out


def apply(call: dict, ctx) -> dict:
    name, args = _unwrap(call["name"], call["arguments"])
    if not isinstance(args, dict):
        return call
    target = _target_tool(name, ctx.tools, ctx.profile)
    if target is None:
        return call
    schema = ctx.tools.get(target) or {}
    fitted = _fit_args(args, schema, target, ctx, name)
    required = schema.get("required") or []
    if any(r not in fitted for r in required):
        return call   # cannot make a valid call; let the harness explain the real tool
    if target != call["name"] or fitted != call["arguments"]:
        ctx.note("aliases", {"name": call["name"], "arguments": call["arguments"]}, {"name": target, "arguments": fitted},
                 f"{call['name']} -> {target}" if target != call["name"] else f"{name}: arguments")
    return {**call, "name": target, "arguments": fitted}

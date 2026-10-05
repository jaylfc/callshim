"""Request-side rules: what the proxy changes before a request reaches the model server.

- restore: put each earlier tool call back exactly as the model wrote it (from State.originals), so the model
  keeps seeing its own tokens and the server's prompt cache stays an exact prefix.
- learn: read hashline tags ("[path#HASH]") out of tool results, for the hashline transform.
- defaults: fields to add when the client did not send them (sampling, thinking budget), from the profile.
- strip: client-specific extras a server may reject (cache_control parts, metadata), when the profile says so.
"""
from __future__ import annotations

import json


def tool_schemas(body: dict) -> dict:
    out = {}
    for t in body.get("tools") or []:
        fn = t.get("function") or {}
        if fn.get("name"):
            out[fn["name"]] = fn.get("parameters") or {}
    return out


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def prepare(body: dict, profile: dict, state, log) -> dict:
    restored = 0
    for msg in body.get("messages") or []:
        if msg.get("role") == "assistant":
            for call in msg.get("tool_calls") or []:
                orig = state.originals.get(call.get("id"))
                fn = call.get("function") or {}
                if orig and (fn.get("name"), fn.get("arguments")) != (orig["name"], orig["arguments"]):
                    fn["name"], fn["arguments"] = orig["name"], orig["arguments"]
                    restored += 1
        elif msg.get("role") == "tool":
            state.learn_hashes(_text(msg.get("content")))
    if restored:
        log({"kind": "restore", "calls": restored})
    for key, value in (profile.get("request_defaults") or {}).items():
        body.setdefault(key, value)
    if profile.get("strip_cache_markers"):
        body.pop("metadata", None)
        for msg in body.get("messages") or []:
            if isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict):
                        part.pop("cache_control", None)
        for tool in body.get("tools") or []:
            tool.pop("cache_control", None)
    return body


def dumps(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode()

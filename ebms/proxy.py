"""EBMS proxy: an OpenAI-compatible pass-through that translates a model's tool calls into the shapes the
harness expects.

usage: python -m ebms.proxy --upstream http://127.0.0.1:8080 --listen 127.0.0.1:8090 --profile profiles/X.json
       [--state FILE] [--log FILE] [--off]

Only POST .../chat/completions is rewritten; every other path is passed through. Streamed tool-call deltas are
buffered until the call is complete, rewritten, and sent as one delta; text and reasoning stream through
unchanged. --off forwards everything untouched (for A/B runs through the same proxy).
"""
from __future__ import annotations

import argparse
import http.client
import json
import pathlib
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .request import dumps, prepare, tool_schemas
from .state import State
from .transforms import Context, call_transforms

HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "host", "te", "trailer", "upgrade"}
ARGS = None
UP = None
PROFILE: dict = {}
STATE: State | None = None
LOG_LOCK = threading.Lock()


def log(entry: dict) -> None:
    entry = {"at": time.strftime("%FT%TZ", time.gmtime()), **entry}
    if ARGS.log:
        with LOG_LOCK, open(ARGS.log, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def rewrite_call(call: dict, tools: dict) -> tuple[dict, list]:
    """call: {"id", "name", "arguments": raw JSON string}. Returns the rewritten call and the notes."""
    try:
        args = json.loads(call["arguments"] or "{}")
    except ValueError:
        return call, []
    ctx = Context(profile=PROFILE, tools=tools, state=STATE)
    cur = {"id": call["id"], "name": call["name"], "arguments": args}
    for name, fn in call_transforms():
        if ctx.enabled(name):
            try:
                cur = fn(cur, ctx)
            except Exception as e:  # a broken transform must never break the call
                ctx.note(name, "", "", f"transform error: {e!r}")
    if ctx.notes:
        STATE.originals[call["id"]] = {"name": call["name"], "arguments": call["arguments"]}
        new = {"id": call["id"], "name": cur["name"], "arguments": json.dumps(cur["arguments"], ensure_ascii=False)}
        return new, ctx.notes
    return call, []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        if ARGS.verbose:
            sys.stderr.write("ebms: " + (fmt % a) + "\n")

    def do_GET(self):
        self._forward("GET", b"", rewrite=False)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        rewrite = not ARGS.off and self.path.rstrip("/").endswith("/chat/completions")
        if rewrite:
            try:
                body = json.loads(raw)
                tools = tool_schemas(body)
                body = prepare(body, PROFILE, STATE, log)
                raw = dumps(body)
                self._tools = tools
                self._stream = bool(body.get("stream"))
            except ValueError:
                rewrite = False
        self._forward("POST", raw, rewrite)

    def _send_headers(self, resp, chunked: bool, length: int | None = None):
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", str(length or 0))
        self.send_header("Connection", "close")
        self.end_headers()

    def _chunk(self, data: bytes):
        if data:
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

    def _forward(self, method: str, raw: bytes, rewrite: bool):
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        hdrs["Content-Length"] = str(len(raw))
        conn = http.client.HTTPConnection(UP.hostname, UP.port or 80, timeout=7200)
        try:
            conn.request(method, UP.path.rstrip("/") + self.path, body=raw or None, headers=hdrs)
            resp = conn.getresponse()
            if not rewrite or resp.status != 200:
                self._send_headers(resp, chunked=True)
                while chunk := resp.read1(65536):
                    self._chunk(chunk)
                self.wfile.write(b"0\r\n\r\n")
            elif self._stream:
                self._send_headers(resp, chunked=True)
                self._relay_stream(resp)
                self.wfile.write(b"0\r\n\r\n")
            else:
                body = json.loads(resp.read())
                self._rewrite_message(body)
                data = dumps(body)
                self._send_headers(resp, chunked=False, length=len(data))
                self.wfile.write(data)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            msg = dumps({"error": {"message": f"ebms proxy: {e!r}"}})
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(msg)
            except Exception:
                pass
        finally:
            conn.close()
            self.close_connection = True
            STATE.save()

    def _rewrite_message(self, body: dict):
        for choice in body.get("choices") or []:
            msg = choice.get("message") or {}
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                new, notes = rewrite_call({"id": tc.get("id"), "name": fn.get("name"), "arguments": fn.get("arguments")}, self._tools)
                if notes:
                    fn["name"], fn["arguments"] = new["name"], new["arguments"]
                    log({"kind": "rewrite", "id": tc.get("id"), "tool": new["name"], "notes": notes})

    def _relay_stream(self, resp):
        pending: dict[int, dict] = {}
        template = None

        def flush():
            if not pending:
                return
            calls = []
            for idx in sorted(pending):
                c = pending[idx]
                new, notes = rewrite_call({"id": c["id"], "name": c["name"], "arguments": c["arguments"]}, self._tools)
                if notes:
                    log({"kind": "rewrite", "id": c["id"], "tool": new["name"], "notes": notes})
                calls.append({"index": idx, "id": new["id"], "type": "function",
                              "function": {"name": new["name"], "arguments": new["arguments"]}})
            out = dict(template or {"object": "chat.completion.chunk"})
            out["choices"] = [{"index": 0, "delta": {"tool_calls": calls}, "finish_reason": None}]
            out.pop("usage", None)
            self._chunk(b"data: " + dumps(out) + b"\n\n")
            pending.clear()

        buf = b""
        while chunk := resp.read1(65536):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.strip()
                if not text.startswith(b"data:"):
                    self._chunk(line + b"\n")
                    continue
                payload = text[5:].strip()
                if payload == b"[DONE]":
                    flush()
                    self._chunk(line + b"\n")
                    continue
                try:
                    obj = json.loads(payload)
                except ValueError:
                    self._chunk(line + b"\n")
                    continue
                template = template or {k: v for k, v in obj.items() if k != "choices"}
                choices = obj.get("choices") or []
                ch = choices[0] if choices else None
                delta = (ch or {}).get("delta") or {}
                if "tool_calls" in delta:
                    for tc in delta.pop("tool_calls") or []:
                        idx = tc.get("index", 0)
                        p = pending.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        p["id"] = tc.get("id") or p["id"]
                        fn = tc.get("function") or {}
                        p["name"] += fn.get("name") or ""
                        p["arguments"] += fn.get("arguments") or ""
                    if not any(delta.get(k) for k in ("content", "reasoning_content", "reasoning")) and not ch.get("finish_reason"):
                        continue
                if ch and ch.get("finish_reason"):
                    flush()
                self._chunk(b"data: " + dumps(obj) + b"\n")
        if buf:
            self._chunk(buf)
        flush()


def main():
    global ARGS, UP, PROFILE, STATE
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--upstream", required=True)
    p.add_argument("--listen", default="127.0.0.1:8090")
    p.add_argument("--profile", required=True)
    p.add_argument("--state", default="")
    p.add_argument("--log", default="")
    p.add_argument("--off", action="store_true", help="forward unchanged (A/B baseline through the same proxy)")
    p.add_argument("--verbose", action="store_true")
    ARGS = p.parse_args()
    UP = urllib.parse.urlparse(ARGS.upstream)
    PROFILE = json.loads(pathlib.Path(ARGS.profile).read_text())
    STATE = State(pathlib.Path(ARGS.state) if ARGS.state else None)
    host, port = ARGS.listen.rsplit(":", 1)
    print(f"ebms proxy {'(off) ' if ARGS.off else ''}on {ARGS.listen} -> {ARGS.upstream}, profile {PROFILE.get('name')}, "
          f"transforms {PROFILE.get('transforms')}", flush=True)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()

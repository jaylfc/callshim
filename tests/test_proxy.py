"""End-to-end: fake streaming upstream -> ebms proxy -> client. Checks buffering, rewrite and history restore."""
import json
import pathlib
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEEN = []


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Fake(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        base = {"id": "x", "object": "chat.completion.chunk", "model": "m"}
        chunks = [
            {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "reasoning_content": "thinking"}, "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": ""}}]}, "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"path\": \"server/net.js\", "}}]}, "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\"start_line\": 40, \"end_line\": 80}"}}]}, "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            {**base, "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        ]
        data = b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n"
        self.send_response(200); self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


class ProxyEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        up = free_port(); cls.port = free_port()
        cls.server = ThreadingHTTPServer(("127.0.0.1", up), Fake)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.log = ROOT / "tests" / ".proxy-test.log"; cls.log.unlink(missing_ok=True)
        cls.proc = subprocess.Popen([sys.executable, "-m", "ebms.proxy", "--upstream", f"http://127.0.0.1:{up}",
                                     "--listen", f"127.0.0.1:{cls.port}", "--profile", str(ROOT / "profiles/qwen3.8-flash-next-coder.json"),
                                     "--log", str(cls.log)], cwd=ROOT, stdout=subprocess.DEVNULL)
        for _ in range(50):
            try: socket.create_connection(("127.0.0.1", cls.port), 0.2).close(); break
            except OSError: time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate(); cls.server.shutdown(); cls.log.unlink(missing_ok=True)

    def post(self, messages):
        body = {"model": "m", "stream": True, "messages": messages,
                "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode()

    def test_stream_rewrite_and_restore(self):
        out = self.post([{"role": "user", "content": "show lines 40-80 of server/net.js"}])
        events = [json.loads(l[5:]) for l in out.splitlines() if l.startswith("data:") and "[DONE]" not in l]
        calls = [tc for e in events for c in e.get("choices", []) for tc in (c.get("delta") or {}).get("tool_calls", [])]
        self.assertEqual(len(calls), 1)                                        # buffered into one delta
        self.assertEqual(calls[0]["function"]["name"], "read")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"path": "server/net.js:40-80"})
        self.assertTrue(any((c.get("delta") or {}).get("reasoning_content") for e in events for c in e.get("choices", [])))
        self.assertTrue(any(c.get("finish_reason") == "tool_calls" for e in events for c in e.get("choices", [])))
        self.assertIn("[DONE]", out)
        # Next turn: the harness sends back the rewritten call; upstream must see the model's original.
        history = [{"role": "user", "content": "x"},
                   {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": calls[0]["function"]}]},
                   {"role": "tool", "tool_call_id": "call_1", "content": "[server/net.js#AB12]\n40 ..."}]
        self.post(history)
        sent = SEEN[-1]["messages"][1]["tool_calls"][0]["function"]
        self.assertEqual(sent["name"], "read_file")
        self.assertEqual(json.loads(sent["arguments"]), {"path": "server/net.js", "start_line": 40, "end_line": 80})
        log = [json.loads(l) for l in self.log.read_text().splitlines()]
        self.assertTrue(any(e["kind"] == "rewrite" for e in log) and any(e["kind"] == "restore" for e in log))


if __name__ == "__main__":
    unittest.main()

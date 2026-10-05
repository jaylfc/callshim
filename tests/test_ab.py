"""tools/ab.py end to end with a fake upstream and a fake harness (no model needed)."""
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_proxy import Fake, free_port   # noqa: E402  (streams one read_file call)


class AbRunner(unittest.TestCase):
    def test_off_vs_on(self):
        up, port = free_port(), free_port()
        server = ThreadingHTTPServer(("127.0.0.1", up), Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as out:
                cmd = [sys.executable, "tools/ab.py", "--harness-cmd", f"CALLSHIM_PORT={port} {sys.executable} {ROOT}/tests/fake_harness.py {{cwd}}",
                       "--upstream", f"http://127.0.0.1:{up}", "--profile", "profiles/qwen3.8-flash-next-coder.json",
                       "--proxy-port", str(port), "--arms", "off,on", "--tasks", "bugfix", "--reps", "1", "--minutes", "1",
                       "--model", "fake", "--harness", "fake-harness 0", "--out", out]
                res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
                self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                sub = json.loads(pathlib.Path(out, "submission.json").read_text())
                self.assertEqual(sub["arms"]["off"]["pass"], 1)
                self.assertEqual(sub["arms"]["on"]["pass"], 1)
                runs = {r["arm"]: r for r in sub["runs"]}
                self.assertEqual(runs["off"]["tool_calls"], 1); self.assertEqual(runs["off"]["rewritten_calls"], 0)
                self.assertEqual(runs["on"]["rewritten_calls"], 1)          # read_file -> read
                self.assertEqual(runs["on"]["rewrites_by_transform"], {"aliases": 1})
                self.assertNotIn(out, json.dumps(sub))                      # no local paths in a submission
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()

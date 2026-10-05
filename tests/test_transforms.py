"""Unit tests from real failing calls (omp-strata-lab experiments/004-ebms/failure-mining.md)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ebms.state import State
from ebms.transforms import Context, aliases, eval_browser, hashline

OMP_TOOLS = {
    "read": {"type": "object", "properties": {"path": {"type": "string"}, "i": {"type": "string"}}, "required": ["path"]},
    "write": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    "edit": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]},
    "bash": {"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}, "timeout": {"type": "number"}}, "required": ["command"]},
    "grep": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "case": {"type": "boolean"}}, "required": ["pattern"]},
    "glob": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "eval": {"type": "object", "properties": {"code": {"type": "string"}, "language": {"type": "string"}}, "required": ["code"]},
    "web_search": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]},
}
PROFILE = {"transforms": ["aliases", "hashline", "eval_browser"]}


def ctx():
    return Context(profile=PROFILE, tools=OMP_TOOLS, state=State(None))


def call(name, args):
    return {"id": "c1", "name": name, "arguments": args}


class HashlineOps(unittest.TestCase):
    def test_near_misses(self):
        cases = {"PUT 1.:=3:": "PUT 1.=3:", "PUT 2*:=4:": "PUT 2.=4:", "PUT 2*=4:": "PUT 2.=4:", "PUT 4*=": "PUT 4*:",
                 "PUT 7:=8:": "PUT 7.=8:", "PUT 12+:": "PUT >12:", "CUT 13:=": "CUT 13", "PUT 5:=5:": "PUT 5.=5:"}
        for bad, good in cases.items():
            self.assertEqual(hashline.fix_op(bad), good, bad)

    def test_valid_untouched(self):
        for ok in ["PUT 3.=5:", "PUT 4:", "PUT >12:", "PUT <2:", "PUT 9*:", "CUT 4.=6", "CUT 4", "CUT 9*", "PUT 3-4:"]:
            self.assertIsNone(hashline.fix_op(ok), ok)

    def test_call(self):
        c = ctx()
        out = hashline.apply(call("edit", {"input": "[src/a.js#1A2B]\nPUT 2*:=4:\n+x = 1"}), c)
        self.assertEqual(out["arguments"]["input"], "[src/a.js#1A2B]\nPUT 2.=4:\n+x = 1")
        self.assertTrue(c.notes)

    def test_body_rows_untouched(self):
        out = hashline.apply(call("edit", {"input": "[a.js#1A2B]\nPUT 1.=1:\n+PUT 2*:=4: stays as text"}), ctx())
        self.assertIn("+PUT 2*:=4: stays as text", out["arguments"]["input"])

    def test_escaped_newlines(self):
        out = hashline.apply(call("edit", {"input": "[a.js#1A2B]\nPUT 4*:\\n+// zones\\n+x()"}), ctx())
        self.assertEqual(out["arguments"]["input"], "[a.js#1A2B]\nPUT 4*:\n+// zones\n+x()")

    def test_bare_hash_gets_path(self):
        c = ctx(); c.state.learn_hashes("[src/stats.js#CCC3]\n1 export ...")
        out = hashline.apply(call("edit", {"input": "[CCC3]\nPUT 2.=4:\n+y"}), c)
        self.assertTrue(out["arguments"]["input"].startswith("[src/stats.js#CCC3]\n"))

    def test_bare_hash_unknown_left(self):
        out = hashline.apply(call("edit", {"input": "[ABCD]\nPUT 2.=4:\n+y"}), ctx())
        self.assertTrue(out["arguments"]["input"].startswith("[ABCD]"))


class Aliases(unittest.TestCase):
    def test_read_file_range(self):  # open-mode elicitation: read_file{path,start_line,end_line}
        out = aliases.apply(call("read_file", {"path": "server/net.js", "start_line": 40, "end_line": 80}), ctx())
        self.assertEqual(out["name"], "read"); self.assertEqual(out["arguments"], {"path": "server/net.js:40-80"})

    def test_read_offset_limit(self):
        out = aliases.apply(call("Read", {"file_path": "a.js", "offset": "10", "limit": "5"}), ctx())
        self.assertEqual(out["arguments"], {"path": "a.js:10-14"})

    def test_list_files_to_glob(self):
        out = aliases.apply(call("list_files", {"path": "client/js"}), ctx())
        self.assertEqual(out["name"], "glob")

    def test_glob_pattern_joined(self):
        out = aliases.apply(call("glob", {"pattern": "**/*.test.js"}), ctx())
        self.assertEqual(out["arguments"], {"path": "**/*.test.js"})

    def test_bash_aliases(self):
        out = aliases.apply(call("run_shell_command", {"cmd": "npm test", "directory": "/work"}), ctx())
        self.assertEqual(out, {"id": "c1", "name": "bash", "arguments": {"command": "npm test", "cwd": "/work"}})

    def test_type_coercion(self):
        out = aliases.apply(call("grep", {"pattern": "x", "case": "true"}), ctx())
        self.assertIs(out["arguments"]["case"], True)

    def test_unmappable_left_alone(self):
        orig = call("update_text_file", {"path": "a.js", "context": "x", "replacement": "y"})
        self.assertEqual(aliases.apply(orig, ctx()), orig)   # hashline edit cannot be built from context/replacement

    def test_known_tool_untouched(self):
        orig = call("read", {"path": "a.js", "i": "note"})
        self.assertEqual(aliases.apply(orig, ctx()), orig)

    def test_web_search(self):
        out = aliases.apply(call("google_web_search", {"q": "ios text select"}), ctx())
        self.assertEqual(out["name"], "web_search"); self.assertEqual(out["arguments"], {"query": "ios text select"})


class EvalBrowser(unittest.TestCase):
    def test_prelude_added_to_js(self):
        out = eval_browser.apply(call("eval", {"language": "js", "code": "const t = await browser.open('http://x')"}), ctx())
        self.assertIn("__ebms_browser", out["arguments"]["code"])

    def test_python_untouched(self):
        orig = call("eval", {"language": "py", "code": "t = await browser.open(name='a', url='x')"})
        self.assertEqual(eval_browser.apply(orig, ctx()), orig)

    def test_no_browser_untouched(self):
        orig = call("eval", {"language": "js", "code": "1 + 1"})
        self.assertEqual(eval_browser.apply(orig, ctx()), orig)


if __name__ == "__main__":
    unittest.main()

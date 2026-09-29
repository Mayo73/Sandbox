import os
import tempfile
import unittest
from pathlib import Path

from copilot_bridge.config import Config
from copilot_bridge.tools import REGISTRY, ToolContext, ToolError, call_tool, load_all

load_all()


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.config = Config()
        self.config.policy.allowed_roots = [str(self.root)]
        self.ctx = ToolContext(config=self.config, roots=self.config.allowed_roots())
        self.addCleanup(self.tmp.cleanup)

    def run_tool(self, name: str, **args):
        return call_tool(REGISTRY[name], self.ctx, args)


class TestSandbox(ToolTestCase):
    def test_path_inside_the_root_is_allowed(self):
        target = self.ctx.resolve(str(self.root / "sub" / "file.txt"))
        self.assertTrue(str(target).startswith(str(self.root)))

    def test_path_outside_the_root_is_refused(self):
        with self.assertRaises(ToolError) as ctx:
            self.ctx.resolve("/etc/passwd" if os.name != "nt" else r"C:\Windows\win.ini")
        self.assertIn("outside the allowed roots", str(ctx.exception))

    def test_dotdot_cannot_escape_the_root(self):
        with self.assertRaises(ToolError):
            self.ctx.resolve(str(self.root / ".." / ".." / "etc"))

    def test_without_roots_file_tools_are_disabled(self):
        empty = ToolContext(config=Config(), roots=[])
        with self.assertRaises(ToolError) as ctx:
            empty.resolve(str(self.root))
        self.assertIn("no allowed_roots", str(ctx.exception))

    def test_environment_variables_are_expanded(self):
        os.environ["CB_TEST_ROOT"] = str(self.root)
        self.addCleanup(os.environ.pop, "CB_TEST_ROOT", None)
        self.assertEqual(self.ctx.resolve("%CB_TEST_ROOT%" if os.name == "nt" else "$CB_TEST_ROOT"), self.root)

    def test_empty_path_is_refused(self):
        with self.assertRaises(ToolError):
            self.ctx.resolve("   ")


class TestFileTools(ToolTestCase):
    def test_write_then_read_round_trip(self):
        path = str(self.root / "notiz.txt")
        written = self.run_tool("fs.write", path=path, content="Hallo Welt\nZeile 2")
        self.assertEqual(written["chars_written"], 18)
        self.assertFalse(written["existed_before"])
        read = self.run_tool("fs.read", path=path)
        self.assertEqual(read["text"], "Hallo Welt\nZeile 2")

    def test_write_creates_missing_parents(self):
        path = str(self.root / "a" / "b" / "c.txt")
        self.run_tool("fs.write", path=path, content="x")
        self.assertTrue(Path(path).exists())

    def test_append_mode(self):
        path = str(self.root / "log.txt")
        self.run_tool("fs.write", path=path, content="eins\n")
        self.run_tool("fs.write", path=path, content="zwei\n", mode="a")
        self.assertEqual(self.run_tool("fs.read", path=path)["text"], "eins\nzwei\n")

    def test_invalid_mode_is_refused(self):
        with self.assertRaises(ToolError):
            self.run_tool("fs.write", path=str(self.root / "x"), content="x", mode="wb")

    def test_read_truncates_and_says_so(self):
        path = str(self.root / "gross.txt")
        self.run_tool("fs.write", path=path, content="y" * 1000)
        read = self.run_tool("fs.read", path=path, max_bytes=100)
        self.assertTrue(read["truncated"])
        self.assertEqual(len(read["text"]), 100)
        self.assertEqual(read["bytes"], 1000)

    def test_read_survives_invalid_bytes(self):
        path = self.root / "binaer.bin"
        path.write_bytes(b"\xff\xfe\x00gut")
        read = self.run_tool("fs.read", path=str(path))
        self.assertIn("replaced invalid bytes", read["encoding"])

    def test_list_sorts_directories_first(self):
        (self.root / "zzz_dir").mkdir()
        (self.root / "aaa.txt").write_text("x")
        entries = self.run_tool("fs.list", path=str(self.root))["entries"]
        self.assertEqual(entries[0]["type"], "dir")
        self.assertEqual(entries[0]["name"], "zzz_dir")

    def test_list_respects_the_limit(self):
        for i in range(10):
            (self.root / f"f{i}.txt").write_text("x")
        result = self.run_tool("fs.list", path=str(self.root), limit=4)
        self.assertEqual(len(result["entries"]), 4)
        self.assertTrue(result["truncated"])

    def test_list_on_a_file_is_refused(self):
        path = self.root / "datei.txt"
        path.write_text("x")
        with self.assertRaises(ToolError):
            self.run_tool("fs.list", path=str(path))

    def test_delete_needs_recursive_for_directories(self):
        (self.root / "ordner").mkdir()
        with self.assertRaises(ToolError):
            self.run_tool("fs.delete", path=str(self.root / "ordner"))
        self.run_tool("fs.delete", path=str(self.root / "ordner"), recursive=True)
        self.assertFalse((self.root / "ordner").exists())

    def test_the_root_itself_cannot_be_deleted(self):
        with self.assertRaises(ToolError) as ctx:
            self.run_tool("fs.delete", path=str(self.root), recursive=True)
        self.assertIn("refusing to delete", str(ctx.exception))

    def test_move_refuses_to_overwrite_silently(self):
        src, dst = self.root / "a.txt", self.root / "b.txt"
        src.write_text("A")
        dst.write_text("B")
        with self.assertRaises(ToolError):
            self.run_tool("fs.move", src=str(src), dst=str(dst))
        self.run_tool("fs.move", src=str(src), dst=str(dst), overwrite=True)
        self.assertEqual(dst.read_text(), "A")
        self.assertFalse(src.exists())

    def test_search_finds_the_line(self):
        (self.root / "eins.txt").write_text("nichts\nSchluessel: 42\n")
        (self.root / "zwei.txt").write_text("nichts")
        hits = self.run_tool("fs.search", path=str(self.root), needle="Schluessel")["hits"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["line"], 2)

    def test_missing_file_reports_clearly(self):
        with self.assertRaises(ToolError) as ctx:
            self.run_tool("fs.read", path=str(self.root / "gibtsnicht.txt"))
        self.assertIn("does not exist", str(ctx.exception))


class TestShellTool(ToolTestCase):
    def test_denylist_blocks_before_running(self):
        self.config.policy.shell_denylist = ["gefaehrlich"]
        with self.assertRaises(ToolError) as ctx:
            self.run_tool("shell.run", cmd="echo GEFAEHRLICH")
        self.assertIn("shell_denylist", str(ctx.exception))

    def test_denylist_is_case_insensitive(self):
        self.config.policy.shell_denylist = ["FORMAT "]
        with self.assertRaises(ToolError):
            self.run_tool("shell.run", cmd="format c:")

    @unittest.skipIf(os.name == "nt", "posix shell")
    def test_output_and_returncode(self):
        result = self.run_tool("shell.run", cmd="echo hallo; exit 3", shell="sh")
        self.assertEqual(result["returncode"], 3)
        self.assertEqual(result["stdout"].strip(), "hallo")

    @unittest.skipIf(os.name == "nt", "posix shell")
    def test_timeout_is_reported(self):
        with self.assertRaises(ToolError) as ctx:
            self.run_tool("shell.run", cmd="sleep 5", shell="sh", timeout=1)
        self.assertIn("timed out", str(ctx.exception))

    @unittest.skipIf(os.name == "nt", "posix shell")
    def test_output_is_capped(self):
        self.config.policy.max_output_chars = 50
        result = self.run_tool("shell.run", cmd="head -c 2000 /dev/zero | tr '\\0' 'a'", shell="sh")
        self.assertEqual(len(result["stdout"]), 50)
        self.assertTrue(result["truncated"])

    def test_cwd_is_sandboxed(self):
        with self.assertRaises(ToolError):
            self.run_tool("shell.run", cmd="echo x", cwd="/")

    def test_unknown_shell_is_refused(self):
        with self.assertRaises(ToolError):
            self.run_tool("shell.run", cmd="echo x", shell="fish")


class TestRegistry(ToolTestCase):
    def test_unknown_argument_is_rejected(self):
        with self.assertRaises(ToolError) as ctx:
            self.run_tool("sys.info", schnickschnack=1)
        self.assertIn("unknown argument", str(ctx.exception))

    def test_every_tool_has_a_description(self):
        for spec in REGISTRY.values():
            self.assertTrue(spec.description.strip(), spec.name)

    def test_write_tools_are_never_marked_safe(self):
        for name in ("fs.write", "fs.delete", "fs.move", "shell.run", "proc.kill", "ui.click"):
            self.assertFalse(REGISTRY[name].safe, f"{name} must require confirmation")

    def test_bridge_tools_lists_the_registry(self):
        listed = self.run_tool("bridge.tools")
        self.assertEqual(listed["count"], len(REGISTRY))

    def test_bridge_tools_marks_denied_tools_disabled(self):
        self.config.policy.denied_tools = ["shell.run"]
        entries = {t["name"]: t for t in self.run_tool("bridge.tools")["tools"]}
        self.assertFalse(entries["shell.run"]["enabled"])
        self.assertTrue(entries["sys.info"]["enabled"])

    def test_sys_env_redacts_secrets(self):
        os.environ["CB_TEST_API_KEY"] = "geheim"
        os.environ["CB_TEST_PLAIN"] = "sichtbar"
        self.addCleanup(os.environ.pop, "CB_TEST_API_KEY", None)
        self.addCleanup(os.environ.pop, "CB_TEST_PLAIN", None)
        env = self.run_tool("sys.env")
        self.assertEqual(env["CB_TEST_API_KEY"], "<redacted>")
        self.assertEqual(env["CB_TEST_PLAIN"], "sichtbar")

    def test_app_open_refuses_odd_schemes(self):
        with self.assertRaises(ToolError) as ctx:
            self.run_tool("app.open", target="file:///etc/passwd")
        self.assertIn("scheme", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

"""End-to-end: CDP client -> watcher -> protocol -> policy -> tool -> responder.

Everything runs against tests/fake_devtools.py, a stand-in for Edge's DevTools
endpoint, so no browser is needed.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from copilot_bridge.audit import AuditLog
from copilot_bridge.cdp import CdpClient, CdpError, browser_version, list_targets
from copilot_bridge.cli import SeenCalls, process_message
from copilot_bridge.config import Config
from copilot_bridge.edge import attach_chat, launch
from copilot_bridge.executor import Executor
from copilot_bridge.policy import Policy
from copilot_bridge.responder import Responder
from copilot_bridge.watcher import ChatWatcher

from .fake_devtools import FakeDevTools

CALL = '{"bridge":1,"tool":"fs.write","args":{"path":"%s","content":"hallo"},"id":"w1"}'


class IntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDevTools()
        self.addCleanup(self.fake.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

        self.cfg = Config()
        self.cfg.edge.port = self.fake.http_port
        self.cfg.edge.attach_only = True
        self.cfg.watch.stable_ms = 150
        self.cfg.watch.poll_ms = 50
        self.cfg.policy.mode = "auto"
        self.cfg.policy.allowed_roots = [str(self.root)]
        self.audit = AuditLog(self.root / "audit.jsonl")

        self.client = CdpClient(self.fake.ws_url).connect()
        self.addCleanup(self.client.close)
        self.watcher = ChatWatcher(self.client, self.cfg)
        self.responder = Responder(self.client, self.cfg)
        self.executor = Executor(self.cfg, Policy(self.cfg, interactive=False), self.audit)
        # The first poll primes the watcher: whatever is already on screen counts
        # as history. Prime against an empty transcript so each test starts fresh.
        self.watcher.poll()

    def poll_until_stable(self, tries=12):
        """Poll like the run loop does until the watcher releases a message."""
        for _ in range(tries):
            messages = self.watcher.poll()
            if messages:
                return messages
            time.sleep(self.cfg.watch.stable_ms / 1000.0 / 2)
        return []


class TestDevToolsDiscovery(IntegrationTestCase):
    def test_http_endpoints_answer(self):
        self.assertIn("Edge", browser_version(self.fake.http_port)["Browser"])
        targets = list_targets(self.fake.http_port)
        self.assertEqual(targets[0]["url"], self.fake.state.url)

    def test_launch_attaches_to_an_open_port(self):
        self.assertIsNone(launch(self.cfg, quiet=True), "must not start a browser")

    def test_attach_chat_picks_the_copilot_target(self):
        client, target = attach_chat(self.cfg, quiet=True)
        self.addCleanup(client.close)
        self.assertIn("copilot.microsoft.com", target["url"])

    def test_attach_only_without_a_port_fails_clearly(self):
        cfg = Config()
        cfg.edge.attach_only = True
        cfg.edge.port = 1  # nothing listens here
        with self.assertRaises(CdpError) as ctx:
            launch(cfg, quiet=True)
        self.assertIn("attach_only", str(ctx.exception))


class TestAdapterInstall(IntegrationTestCase):
    def test_adapter_is_injected_once(self):
        self.assertEqual(self.fake.state.install_count, 1, "setUp's priming poll installed it")
        for _ in range(5):
            self.watcher.read_raw()
        self.assertEqual(self.fake.state.install_count, 1, "no reinstall while it is present")

    def test_adapter_is_reinstalled_after_a_navigation(self):
        self.fake.state.installed = False        # a page load wipes window.__copilotBridge
        self.watcher.read_raw()
        self.assertEqual(self.fake.state.install_count, 2)

    def test_js_exception_surfaces_as_cdp_error(self):
        self.fake.state.evaluate_error = "TypeError: boom"
        with self.assertRaises(CdpError) as ctx:
            self.watcher.read_raw()
        self.assertIn("boom", str(ctx.exception))


class TestStreamingDetection(IntegrationTestCase):
    def test_a_growing_message_is_not_released_early(self):
        self.fake.state.set_transcript([{"role": "assistant", "text": "Ich schrei"}])
        self.assertEqual(self.watcher.poll(), [])
        for chunk in ("Ich schreibe ", "Ich schreibe gerade ", "Ich schreibe gerade noch"):
            self.fake.state.set_transcript([{"role": "assistant", "text": chunk}])
            time.sleep(0.1)
            self.assertEqual(self.watcher.poll(), [], "still streaming")
        time.sleep(0.2)
        released = self.watcher.poll()
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0].text, "Ich schreibe gerade noch")

    def test_a_message_is_released_only_once(self):
        self.fake.state.set_transcript([{"role": "assistant", "text": "fertige Antwort"}])
        self.assertEqual(len(self.poll_until_stable()), 1)
        time.sleep(0.3)
        self.assertEqual(self.watcher.poll(), [], "no repeat on later polls")

    def test_history_on_screen_at_startup_is_not_replayed(self):
        self.fake.state.set_transcript(
            [{"role": "assistant", "text": "alte Antwort von gestern"}]
        )
        watcher = ChatWatcher(self.client, self.cfg)   # starts unprimed, like a fresh run
        self.assertEqual(watcher.poll(), [])
        time.sleep(0.3)
        self.assertEqual(watcher.poll(), [])

    def test_execute_backlog_replays_history(self):
        self.cfg.watch.execute_backlog = True
        self.fake.state.set_transcript([{"role": "assistant", "text": "alte Antwort"}])
        watcher = ChatWatcher(self.client, self.cfg)   # unprimed, backlog enabled
        watcher.poll()
        time.sleep(0.3)
        self.assertEqual(len(watcher.poll()), 1)

    def test_user_messages_are_ignored_by_default(self):
        self.fake.state.set_transcript(
            [{"role": "user", "text": "meine Frage"}, {"role": "assistant", "text": "die Antwort"}]
        )
        released = self.poll_until_stable()
        self.assertEqual([m.role for m in released], ["assistant"])

    def test_unknown_roles_are_accepted_when_configured(self):
        self.fake.state.set_transcript([{"role": "unknown", "text": "wer auch immer"}])
        self.assertEqual(len(self.poll_until_stable()), 1)

    def test_unknown_roles_can_be_refused(self):
        self.cfg.watch.accept_unknown_role = False
        watcher = ChatWatcher(self.client, self.cfg)
        watcher.poll()                                  # prime on an empty chat
        self.fake.state.set_transcript([{"role": "unknown", "text": "wer auch immer"}])
        watcher.poll()
        time.sleep(0.3)
        self.assertEqual(watcher.poll(), [])

    def test_navigation_clears_the_state(self):
        self.fake.state.set_transcript([{"role": "assistant", "text": "erster Chat"}])
        self.assertEqual(len(self.poll_until_stable()), 1)
        self.fake.state.url = "https://copilot.microsoft.com/chats/andere"
        time.sleep(0.3)
        self.watcher.poll()                             # first poll after navigating primes again
        time.sleep(0.3)
        self.assertEqual(self.watcher.poll(), [], "the new page is not replayed")


class TestFullLoop(IntegrationTestCase):
    def test_a_call_in_a_code_block_runs_and_is_reported_back(self):
        target = self.root / "ergebnis.txt"
        self.fake.state.set_transcript(
            [
                {"role": "user", "text": "Schreib mir bitte eine Datei"},
                {
                    "role": "assistant",
                    "text": "Klar, ich lege sie an:",
                    "code": [{"lang": "json", "text": CALL % str(target).replace("\\", "\\\\")}],
                },
            ]
        )
        messages = self.poll_until_stable()
        self.assertEqual(len(messages), 1)

        results = process_message(
            messages[0], self.executor, self.responder, self.cfg, SeenCalls()
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok, results[0].payload)
        self.assertEqual(target.read_text(), "hallo")

        self.assertEqual(len(self.fake.state.sent), 1)
        posted = self.fake.state.sent[0]["text"]
        self.assertTrue(posted.startswith("[bridge] Ergebnis"))
        envelope = json.loads(posted.split("\n", 1)[1])
        self.assertEqual(envelope["id"], "w1")
        self.assertTrue(envelope["ok"])

    def test_the_same_call_is_never_run_twice(self):
        target = self.root / "einmal.txt"
        payload = CALL % str(target).replace("\\", "\\\\")
        self.fake.state.set_transcript(
            [{"role": "assistant", "text": "los", "code": [{"lang": "json", "text": payload}]}]
        )
        message = self.poll_until_stable()[0]
        seen = SeenCalls()
        first = process_message(message, self.executor, self.responder, self.cfg, seen)
        second = process_message(message, self.executor, self.responder, self.cfg, seen)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_a_denied_tool_still_answers_the_chat(self):
        self.cfg.policy.denied_tools = ["fs.write"]
        executor = Executor(self.cfg, Policy(self.cfg, interactive=False), self.audit)
        self.fake.state.set_transcript(
            [
                {
                    "role": "assistant",
                    "text": "los",
                    "code": [{"lang": "json", "text": CALL % str(self.root / "nope.txt")}],
                }
            ]
        )
        message = self.poll_until_stable()[0]
        results = process_message(message, executor, self.responder, self.cfg, SeenCalls())
        self.assertFalse(results[0].ok)
        self.assertTrue(results[0].skipped)
        envelope = json.loads(self.fake.state.sent[0]["text"].split("\n", 1)[1])
        self.assertIn("denied", envelope["error"])

    def test_a_failing_tool_reports_the_error_to_the_chat(self):
        payload = '{"bridge":1,"tool":"fs.read","args":{"path":"/nicht/erlaubt"},"id":"e1"}'
        self.fake.state.set_transcript([{"role": "assistant", "text": payload}])
        message = self.poll_until_stable()[0]
        results = process_message(message, self.executor, self.responder, self.cfg, SeenCalls())
        self.assertFalse(results[0].ok)
        envelope = json.loads(self.fake.state.sent[0]["text"].split("\n", 1)[1])
        self.assertFalse(envelope["ok"])
        self.assertIn("outside the allowed roots", envelope["error"])

    def test_several_calls_in_one_message_run_in_order(self):
        one = self.root / "eins.txt"
        two = self.root / "zwei.txt"
        batch = json.dumps(
            {
                "bridge": 1,
                "calls": [
                    {"tool": "fs.write", "args": {"path": str(one), "content": "1"}, "id": "a"},
                    {"tool": "fs.write", "args": {"path": str(two), "content": "2"}, "id": "b"},
                ],
            }
        )
        self.fake.state.set_transcript(
            [{"role": "assistant", "text": "beide", "code": [{"lang": "json", "text": batch}]}]
        )
        message = self.poll_until_stable()[0]
        results = process_message(message, self.executor, self.responder, self.cfg, SeenCalls())
        self.assertEqual([r.ok for r in results], [True, True])
        self.assertEqual(one.read_text(), "1")
        self.assertEqual(two.read_text(), "2")
        self.assertEqual(len(self.fake.state.sent), 1, "one reply carries both results")

    def test_the_bridges_own_reply_never_triggers_a_call(self):
        self.fake.state.set_transcript([{"role": "assistant", "text": "start"}])
        self.poll_until_stable()
        reply = '[bridge] Ergebnis:\n{"bridge_result":1,"id":"w1","ok":true,"result":{"x":1}}'
        self.fake.state.set_transcript([{"role": "assistant", "text": reply}])
        message = self.poll_until_stable()[0]
        self.assertEqual(
            process_message(message, self.executor, self.responder, self.cfg, SeenCalls()), []
        )

    def test_audit_log_records_every_call(self):
        target = self.root / "protokoll.txt"
        self.fake.state.set_transcript(
            [
                {
                    "role": "assistant",
                    "text": CALL % str(target).replace("\\", "\\\\"),
                }
            ]
        )
        message = self.poll_until_stable()[0]
        process_message(message, self.executor, self.responder, self.cfg, SeenCalls())
        lines = [json.loads(l) for l in self.audit.path.read_text().splitlines()]
        self.assertEqual(lines[-1]["kind"], "executed")
        self.assertEqual(lines[-1]["tool"], "fs.write")
        self.assertEqual(lines[-1]["id"], "w1")

    def test_audit_log_shrinks_huge_results(self):
        big = self.root / "gross.txt"
        big.write_text("z" * 50_000)
        payload = json.dumps(
            {"bridge": 1, "tool": "fs.read", "args": {"path": str(big)}, "id": "big"}
        )
        self.fake.state.set_transcript([{"role": "assistant", "text": payload}])
        message = self.poll_until_stable()[0]
        process_message(message, self.executor, self.responder, self.cfg, SeenCalls())
        line = self.audit.path.read_text().splitlines()[-1]
        self.assertLess(len(line), 4000, "the log must not swallow the whole file")
        self.assertIn("chars]", json.loads(line)["result"])

    def test_respond_disabled_keeps_the_chat_untouched(self):
        self.cfg.respond.enabled = False
        target = self.root / "still.txt"
        self.fake.state.set_transcript(
            [{"role": "assistant", "text": CALL % str(target).replace("\\", "\\\\")}]
        )
        message = self.poll_until_stable()[0]
        results = process_message(message, self.executor, self.responder, self.cfg, SeenCalls())
        self.assertTrue(results[0].ok)
        self.assertEqual(self.fake.state.sent, [])


class TestResponder(IntegrationTestCase):
    def test_enter_is_pressed_when_no_send_button_exists(self):
        self.fake.state.send_button_present = False
        self.assertTrue(self.responder.post("hallo"))
        types = [k["type"] for k in self.fake.state.keys]
        self.assertIn("rawKeyDown", types)
        self.assertIn("keyUp", types)
        self.assertTrue(all(k.get("key") == "Enter" for k in self.fake.state.keys))

    def test_no_enter_when_the_button_was_clicked(self):
        self.assertTrue(self.responder.post("hallo"))
        self.assertEqual(self.fake.state.keys, [])

    def test_missing_composer_is_reported(self):
        self.fake.state.composer_present = False
        self.assertFalse(self.responder.post("hallo"))

    def test_the_adapter_is_reinstalled_before_posting(self):
        self.fake.state.installed = False        # as if the page had navigated
        before = self.fake.state.install_count
        self.assertTrue(self.responder.post("nach dem Reload"))
        self.assertEqual(self.fake.state.install_count, before + 1)
        self.assertEqual(self.fake.state.sent[-1]["text"], "nach dem Reload")

    def test_submit_flag_is_passed_to_the_page(self):
        self.cfg.respond.submit = False
        self.responder.post("nur einfuegen")
        self.assertFalse(self.fake.state.sent[0]["submit"])


class TestCdpClient(IntegrationTestCase):
    def test_unsupported_method_raises(self):
        with self.assertRaises(CdpError) as ctx:
            self.client.send("Gibts.Nicht")
        self.assertIn("unsupported", str(ctx.exception))

    def test_calls_after_close_are_refused(self):
        client = CdpClient(self.fake.ws_url).connect()
        client.close()
        self.assertFalse(client.connected)
        with self.assertRaises(CdpError):
            client.evaluate("1+1")

    def test_concurrent_requests_get_their_own_answers(self):
        import threading

        results = {}

        def ask(name):
            results[name] = self.client.evaluate("window.__copilotBridge.read('')")

        threads = [threading.Thread(target=ask, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(r["url"] == self.fake.state.url for r in results.values()))


if __name__ == "__main__":
    unittest.main()

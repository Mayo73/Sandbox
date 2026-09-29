import unittest

from copilot_bridge.config import Config
from copilot_bridge.policy import Policy, RateLimiter, Verdict
from copilot_bridge.protocol import ToolCall
from copilot_bridge.tools import REGISTRY, load_all

load_all()

SAFE = REGISTRY["sys.info"]
UNSAFE = REGISTRY["shell.run"]


def call(tool: str, **args) -> ToolCall:
    return ToolCall(tool=tool, args=args, id="t", digest=tool)


class TestRateLimiter(unittest.TestCase):
    def test_blocks_past_the_limit(self):
        limiter = RateLimiter(per_minute=3)
        self.assertEqual([limiter.allow() for _ in range(4)], [True, True, True, False])

    def test_zero_means_unlimited(self):
        limiter = RateLimiter(per_minute=0)
        self.assertTrue(all(limiter.allow() for _ in range(100)))


class TestPolicy(unittest.TestCase):
    def policy(self, **overrides) -> Policy:
        cfg = Config()
        for key, value in overrides.items():
            setattr(cfg.policy, key, value)
        return Policy(cfg, interactive=False)

    def test_ask_mode_asks_even_for_safe_tools(self):
        verdict = self.policy(mode="ask").evaluate(call("sys.info"), SAFE).verdict
        self.assertIs(verdict, Verdict.ASK)

    def test_auto_safe_runs_read_only_tools(self):
        policy = self.policy(mode="auto_safe")
        self.assertIs(policy.evaluate(call("sys.info"), SAFE).verdict, Verdict.ALLOW)
        self.assertIs(policy.evaluate(call("shell.run"), UNSAFE).verdict, Verdict.ASK)

    def test_auto_runs_everything(self):
        verdict = self.policy(mode="auto").evaluate(call("shell.run"), UNSAFE).verdict
        self.assertIs(verdict, Verdict.ALLOW)

    def test_unknown_tool_is_denied(self):
        decision = self.policy(mode="auto").evaluate(call("does.not.exist"), None)
        self.assertIs(decision.verdict, Verdict.DENY)
        self.assertIn("unknown tool", decision.reason)

    def test_denylist_beats_auto_mode(self):
        decision = self.policy(mode="auto", denied_tools=["shell.run"]).evaluate(
            call("shell.run"), UNSAFE
        )
        self.assertIs(decision.verdict, Verdict.DENY)

    def test_allowlist_excludes_everything_else(self):
        policy = self.policy(mode="auto", allowed_tools=["sys.info"])
        self.assertIs(policy.evaluate(call("sys.info"), SAFE).verdict, Verdict.ALLOW)
        self.assertIs(policy.evaluate(call("shell.run"), UNSAFE).verdict, Verdict.DENY)

    def test_empty_allowlist_means_all_tools(self):
        policy = self.policy(mode="auto", allowed_tools=[])
        self.assertIs(policy.evaluate(call("shell.run"), UNSAFE).verdict, Verdict.ALLOW)

    def test_rate_limit_denies_the_overflow(self):
        policy = self.policy(mode="auto", max_calls_per_minute=2)
        verdicts = [policy.evaluate(call("sys.info"), SAFE).verdict for _ in range(3)]
        self.assertEqual(verdicts, [Verdict.ALLOW, Verdict.ALLOW, Verdict.DENY])

    def test_session_allow_skips_the_prompt(self):
        policy = self.policy(mode="ask")
        policy.session_allow.add("shell.run")
        self.assertIs(policy.evaluate(call("shell.run"), UNSAFE).verdict, Verdict.ALLOW)

    def test_session_deny_beats_session_allow(self):
        policy = self.policy(mode="auto")
        policy.session_deny.add("shell.run")
        self.assertIs(policy.evaluate(call("shell.run"), UNSAFE).verdict, Verdict.DENY)

    def test_non_interactive_confirmation_is_a_no(self):
        policy = self.policy(mode="ask")
        self.assertFalse(policy.confirm(call("shell.run", cmd="dir"), UNSAFE))

    def test_invalid_mode_is_rejected_at_construction(self):
        cfg = Config()
        cfg.policy.mode = "yolo"
        with self.assertRaises(ValueError):
            Policy(cfg, interactive=False)


if __name__ == "__main__":
    unittest.main()

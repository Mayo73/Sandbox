"""The gate between the chat and your machine."""
from __future__ import annotations

import json
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .config import Config
from .protocol import ToolCall
from .tools import ToolSpec

WINDOWS = os.name == "nt"


class Verdict(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class Decision:
    verdict: Verdict
    reason: str = ""


@dataclass
class RateLimiter:
    per_minute: int
    _stamps: deque[float] = field(default_factory=deque)

    def allow(self) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        while self._stamps and now - self._stamps[0] > 60:
            self._stamps.popleft()
        if len(self._stamps) >= self.per_minute:
            return False
        self._stamps.append(now)
        return True


def read_key(prompt: str, valid: str, timeout: float) -> str:
    """Read one keypress, returning '' when the timeout expires."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    deadline = time.monotonic() + timeout

    if WINDOWS:
        import msvcrt

        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in ("\x00", "\xe0"):   # function / arrow key prefix
                    msvcrt.getwch()
                    continue
                char = char.lower()
                if char in valid:
                    sys.stdout.write(char + "\n")
                    sys.stdout.flush()
                    return char
            time.sleep(0.05)
        sys.stdout.write("\n")
        return ""

    import select

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            sys.stdout.write("\n")
            return ""
        ready, _, _ = select.select([sys.stdin], [], [], min(remaining, 0.5))
        if not ready:
            continue
        line = sys.stdin.readline().strip().lower()
        if line and line[0] in valid:
            return line[0]
        if not line and "\n" in valid:
            return "\n"


class Policy:
    """Applies the configured rules and, when needed, asks at the console."""

    MODES = ("ask", "auto_safe", "auto")

    def __init__(self, config: Config, interactive: bool = True) -> None:
        if config.policy.mode not in self.MODES:
            raise ValueError(
                f"policy.mode must be one of {', '.join(self.MODES)}, "
                f"got {config.policy.mode!r}"
            )
        self.config = config
        self.interactive = interactive
        self.limiter = RateLimiter(config.policy.max_calls_per_minute)
        self.session_allow: set[str] = set()
        self.session_deny: set[str] = set()

    # -- rules -------------------------------------------------------------
    def evaluate(self, call: ToolCall, spec: ToolSpec | None) -> Decision:
        policy = self.config.policy
        if spec is None:
            return Decision(Verdict.DENY, f"unknown tool {call.tool!r}")
        if call.tool in self.session_deny:
            return Decision(Verdict.DENY, "denied earlier in this session")
        if call.tool in policy.denied_tools:
            return Decision(Verdict.DENY, "listed in policy.denied_tools")
        if policy.allowed_tools and call.tool not in policy.allowed_tools:
            return Decision(Verdict.DENY, "not in policy.allowed_tools")
        if not self.limiter.allow():
            return Decision(
                Verdict.DENY, f"rate limit of {policy.max_calls_per_minute}/min reached"
            )
        if policy.mode == "auto":
            return Decision(Verdict.ALLOW, "policy.mode = auto")
        if call.tool in self.session_allow:
            return Decision(Verdict.ALLOW, "allowed for this session")
        if policy.mode == "auto_safe" and spec.safe:
            return Decision(Verdict.ALLOW, "read-only tool, policy.mode = auto_safe")
        return Decision(Verdict.ASK, "needs confirmation")

    # -- console prompt ----------------------------------------------------
    def confirm(self, call: ToolCall, spec: ToolSpec) -> bool:
        if not self.interactive:
            print(f"[policy] denied {call.tool} (non-interactive run, mode={self.config.policy.mode})")
            return False
        args = json.dumps(call.args, ensure_ascii=False, default=str)
        if len(args) > 1200:
            args = args[:1200] + " ...[cut]"
        print()
        print("=" * 72)
        print(f"  TOOL CALL   {call.tool}      (id {call.id})")
        print(f"  {spec.description}")
        print(f"  args        {args}")
        print(f"  source      {call.source}")
        print("=" * 72)
        answer = read_key(
            "  [y] run once   [a] always this tool   [n] skip   [x] never this tool > ",
            "yanx",
            self.config.policy.confirm_timeout_s,
        )
        if answer == "y":
            return True
        if answer == "a":
            self.session_allow.add(call.tool)
            print(f"  -> {call.tool} is now allowed for the rest of this session")
            return True
        if answer == "x":
            self.session_deny.add(call.tool)
            print(f"  -> {call.tool} is blocked for the rest of this session")
            return False
        if answer == "":
            print(f"  -> no answer within {self.config.policy.confirm_timeout_s}s, skipping")
        return False

    def describe(self) -> str:
        policy = self.config.policy
        bits = [f"mode={policy.mode}", f"rate={policy.max_calls_per_minute}/min"]
        if policy.allowed_tools:
            bits.append(f"allowed={len(policy.allowed_tools)} tools")
        if policy.denied_tools:
            bits.append(f"denied={','.join(policy.denied_tools)}")
        return "  ".join(bits)

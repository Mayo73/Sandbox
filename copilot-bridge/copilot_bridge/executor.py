"""Run a parsed tool call through policy, tool and audit log."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from typing import Any

from .audit import AuditLog
from .config import Config
from .policy import Policy, Verdict
from .protocol import ToolCall
from .tools import REGISTRY, ToolContext, ToolError, call_tool, load_all


@dataclass
class ExecResult:
    call: ToolCall
    ok: bool
    payload: Any
    duration_ms: int = 0
    skipped: bool = False


class Executor:
    def __init__(self, config: Config, policy: Policy, audit: AuditLog | None = None) -> None:
        self.config = config
        self.policy = policy
        self.audit = audit or AuditLog()
        load_all()
        self.ctx = ToolContext(config=config, roots=config.allowed_roots())

    def run(self, call: ToolCall) -> ExecResult:
        spec = REGISTRY.get(call.tool)
        decision = self.policy.evaluate(call, spec)

        if decision.verdict is Verdict.DENY:
            self.audit.write(
                "denied", tool=call.tool, id=call.id, args=call.args, reason=decision.reason
            )
            print(f"[deny] {call.tool}: {decision.reason}")
            return ExecResult(call, False, f"denied: {decision.reason}", skipped=True)

        assert spec is not None
        if decision.verdict is Verdict.ASK and not self.policy.confirm(call, spec):
            self.audit.write("skipped", tool=call.tool, id=call.id, args=call.args)
            return ExecResult(call, False, "skipped by the user at the console", skipped=True)

        started = time.monotonic()
        try:
            payload: Any = call_tool(spec, self.ctx, call.args)
            ok = True
        except ToolError as exc:
            payload, ok = str(exc), False
        except Exception as exc:  # a tool blowing up must not kill the loop
            payload = f"{type(exc).__name__}: {exc}"
            ok = False
            traceback.print_exc()
        duration = int((time.monotonic() - started) * 1000)

        self.audit.write(
            "executed" if ok else "failed",
            tool=call.tool,
            id=call.id,
            args=call.args,
            ms=duration,
            result=payload if ok else None,
            error=None if ok else payload,
        )
        status = "ok" if ok else "error"
        print(f"[{status}] {call.tool} ({duration} ms)")
        if not ok:
            print(f"        {payload}")
        return ExecResult(call, ok, payload, duration)

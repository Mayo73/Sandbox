"""Tools that describe the bridge itself."""
from __future__ import annotations

import datetime as _dt
from typing import Any

from . import REGISTRY, ToolContext, tool


@tool("bridge.ping", "Check that the bridge is alive.", {}, safe=True)
def bridge_ping(ctx: ToolContext) -> dict[str, Any]:
    return {"pong": True, "time": _dt.datetime.now().isoformat(timespec="seconds")}


@tool("bridge.tools", "List every tool the bridge can run.", {}, safe=True)
def bridge_tools(ctx: ToolContext) -> dict[str, Any]:
    policy = ctx.config.policy
    tools = []
    for spec in sorted(REGISTRY.values(), key=lambda s: s.name):
        allowed = spec.name not in policy.denied_tools and (
            not policy.allowed_tools or spec.name in policy.allowed_tools
        )
        tools.append(
            {
                "name": spec.name,
                "signature": spec.signature(),
                "description": spec.description,
                "safe": spec.safe,
                "enabled": allowed,
            }
        )
    return {"mode": policy.mode, "count": len(tools), "tools": tools}


@tool("bridge.limits", "Show the active policy limits.", {}, safe=True)
def bridge_limits(ctx: ToolContext) -> dict[str, Any]:
    policy = ctx.config.policy
    return {
        "mode": policy.mode,
        "allowed_roots": [str(r) for r in ctx.roots],
        "denied_tools": policy.denied_tools,
        "allowed_tools": policy.allowed_tools or "(all)",
        "max_calls_per_minute": policy.max_calls_per_minute,
        "shell_denylist": policy.shell_denylist,
    }

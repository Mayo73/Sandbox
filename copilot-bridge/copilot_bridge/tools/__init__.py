"""Tool registry.

Every tool is a plain function registered with @tool. `safe=True` marks a
read-only tool that policy mode "auto_safe" may run without asking.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..config import Config


class ToolError(RuntimeError):
    """Raised by a tool when the call cannot be carried out."""


@dataclass
class ToolSpec:
    name: str
    func: Callable[..., Any]
    description: str
    params: dict[str, str] = field(default_factory=dict)
    safe: bool = False

    def signature(self) -> str:
        args = ", ".join(f"{k}: {v}" for k, v in self.params.items())
        return f"{self.name}({args})"


REGISTRY: dict[str, ToolSpec] = {}


def tool(
    name: str,
    description: str,
    params: dict[str, str] | None = None,
    safe: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if name in REGISTRY:
            raise RuntimeError(f"duplicate tool name: {name}")
        REGISTRY[name] = ToolSpec(
            name=name, func=func, description=description, params=params or {}, safe=safe
        )
        return func

    return decorator


@dataclass
class ToolContext:
    """Everything a tool is allowed to touch."""

    config: Config
    roots: list[Path] = field(default_factory=list)

    def resolve(self, raw: str, must_exist: bool = False) -> Path:
        """Expand and sandbox-check a path coming from the chat."""
        import os

        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("path must be a non-empty string")
        path = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise ToolError(f"cannot resolve path {raw!r}: {exc}") from exc
        if not self.roots:
            raise ToolError(
                "no allowed_roots are configured, so file tools are disabled. "
                "Add paths to [policy].allowed_roots."
            )
        for root in self.roots:
            if resolved == root or root in resolved.parents:
                break
        else:
            allowed = ", ".join(str(r) for r in self.roots)
            raise ToolError(f"path {resolved} is outside the allowed roots ({allowed})")
        if must_exist and not resolved.exists():
            raise ToolError(f"path does not exist: {resolved}")
        return resolved


def call_tool(spec: ToolSpec, ctx: ToolContext, args: dict[str, Any]) -> Any:
    """Invoke a tool, rejecting unknown keyword arguments up front."""
    signature = inspect.signature(spec.func)
    accepted = {
        name
        for name, param in signature.parameters.items()
        if param.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    accepted.discard("ctx")
    unknown = set(args) - accepted
    if unknown:
        raise ToolError(
            f"unknown argument(s) for {spec.name}: {', '.join(sorted(unknown))}. "
            f"Expected: {', '.join(sorted(accepted)) or '(none)'}"
        )
    return spec.func(ctx, **args)


def load_all() -> dict[str, ToolSpec]:
    """Import the tool modules so their @tool decorators run."""
    from . import bridge_meta, fs, shell, system  # noqa: F401

    try:
        from . import desktop  # noqa: F401
    except Exception:
        # Optional deps (pyautogui etc.) are reported per-call instead.
        pass
    return REGISTRY

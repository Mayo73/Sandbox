"""Command execution."""
from __future__ import annotations

import locale
import os
import subprocess
from typing import Any

from . import ToolContext, ToolError, tool

WINDOWS = os.name == "nt"
MAX_TIMEOUT = 600


def _decode(raw: bytes) -> str:
    for codec in ("utf-8", locale.getpreferredencoding(False), "cp1252"):
        if not codec:
            continue
        try:
            return raw.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def _argv(cmd: str, shell: str) -> list[str]:
    if shell == "auto":
        shell = "powershell" if WINDOWS else "sh"
    if shell == "powershell":
        prelude = "$ErrorActionPreference='Continue'; " \
                  "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", prelude + cmd]
    if shell == "pwsh":
        return ["pwsh", "-NoProfile", "-NonInteractive", "-Command", cmd]
    if shell == "cmd":
        return ["cmd", "/d", "/c", "chcp 65001>nul & " + cmd]
    if shell == "sh":
        return ["/bin/sh", "-c", cmd]
    raise ToolError(f"unknown shell {shell!r} (use powershell, pwsh, cmd, sh or auto)")


@tool(
    "shell.run",
    "Run a command line and return its output.",
    {
        "cmd": "str",
        "shell": "str = 'auto'  (powershell|pwsh|cmd|sh)",
        "cwd": "str = ''",
        "timeout": "int = 60",
    },
)
def shell_run(
    ctx: ToolContext,
    cmd: str,
    shell: str = "auto",
    cwd: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    if not isinstance(cmd, str) or not cmd.strip():
        raise ToolError("cmd must be a non-empty string")
    lowered = cmd.lower()
    for pattern in ctx.config.policy.shell_denylist:
        if pattern.lower() in lowered:
            raise ToolError(f"command blocked by shell_denylist entry {pattern!r}")

    workdir = str(ctx.resolve(cwd, must_exist=True)) if cwd else None
    seconds = max(1, min(int(timeout), MAX_TIMEOUT))
    argv = _argv(cmd, shell)

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            cwd=workdir,
            timeout=seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if WINDOWS else 0,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"shell not available: {exc}") from exc
    except subprocess.TimeoutExpired:
        raise ToolError(f"command timed out after {seconds}s") from None

    cap = ctx.config.policy.max_output_chars
    stdout = _decode(proc.stdout)
    stderr = _decode(proc.stderr)
    result = {
        "cmd": cmd,
        "shell": shell,
        "cwd": workdir or os.getcwd(),
        "returncode": proc.returncode,
        "stdout": stdout[:cap],
        "stderr": stderr[:cap],
    }
    if len(stdout) > cap or len(stderr) > cap:
        result["truncated"] = True
    return result

"""System, process and clipboard tools."""
from __future__ import annotations

import datetime as _dt
import getpass
import os
import platform
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

from . import ToolContext, ToolError, tool

WINDOWS = os.name == "nt"
SECRET_HINTS = ("key", "token", "secret", "password", "passwd", "pwd", "credential")


def _psutil():
    try:
        import psutil  # type: ignore[import-not-found]

        return psutil
    except ModuleNotFoundError:
        return None


@tool("sys.info", "Machine, OS and user overview.", {}, safe=True)
def sys_info(ctx: ToolContext) -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "user": getpass.getuser(),
        "python": sys.version.split()[0],
        "cwd": os.getcwd(),
        "local_time": _dt.datetime.now().isoformat(timespec="seconds"),
        "cpu_count": os.cpu_count(),
    }
    ps = _psutil()
    if ps is not None:
        mem = ps.virtual_memory()
        info["memory_total_gb"] = round(mem.total / 1024**3, 2)
        info["memory_used_pct"] = mem.percent
    disks = []
    for path in (["C:\\"] if WINDOWS else ["/"]):
        try:
            usage = shutil.disk_usage(path)
            disks.append(
                {
                    "path": path,
                    "total_gb": round(usage.total / 1024**3, 1),
                    "free_gb": round(usage.free / 1024**3, 1),
                }
            )
        except OSError:
            continue
    info["disks"] = disks
    return info


@tool(
    "sys.env",
    "Read environment variables (secret-looking values are redacted).",
    {"name": "str = ''  (empty = all)"},
    safe=True,
)
def sys_env(ctx: ToolContext, name: str = "") -> dict[str, Any]:
    def mask(key: str, value: str) -> str:
        return "<redacted>" if any(h in key.lower() for h in SECRET_HINTS) else value

    if name:
        if name not in os.environ:
            raise ToolError(f"environment variable {name} is not set")
        return {name: mask(name, os.environ[name])}
    return {key: mask(key, value) for key, value in sorted(os.environ.items())}


@tool(
    "proc.list",
    "List running processes.",
    {"name_contains": "str = ''", "limit": "int = 60"},
    safe=True,
)
def proc_list(ctx: ToolContext, name_contains: str = "", limit: int = 60) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    needle = (name_contains or "").lower()
    ps = _psutil()
    rows: list[dict[str, Any]] = []
    if ps is not None:
        for proc in ps.process_iter(["pid", "name", "memory_info"]):
            try:
                info = proc.info
                pname = info.get("name") or ""
                if needle and needle not in pname.lower():
                    continue
                mem = info.get("memory_info")
                rows.append(
                    {
                        "pid": info.get("pid"),
                        "name": pname,
                        "memory_mb": round(mem.rss / 1024**2, 1) if mem else None,
                    }
                )
            except Exception:
                continue
            if len(rows) >= limit:
                break
        rows.sort(key=lambda r: r["memory_mb"] or 0, reverse=True)
        return {"source": "psutil", "count": len(rows), "processes": rows}

    if not WINDOWS:
        raise ToolError("proc.list needs psutil on this platform (pip install psutil)")
    out = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=20
    ).stdout
    import csv
    import io

    for row in csv.reader(io.StringIO(out)):
        if len(row) < 5:
            continue
        if needle and needle not in row[0].lower():
            continue
        rows.append({"pid": row[1], "name": row[0], "memory": row[4]})
        if len(rows) >= limit:
            break
    return {"source": "tasklist", "count": len(rows), "processes": rows}


@tool("proc.kill", "Terminate a process by PID.", {"pid": "int", "force": "bool = false"})
def proc_kill(ctx: ToolContext, pid: int, force: bool = False) -> dict[str, Any]:
    pid = int(pid)
    if pid in (0, os.getpid()):
        raise ToolError("refusing to kill this PID")
    ps = _psutil()
    if ps is not None:
        try:
            proc = ps.Process(pid)
            name = proc.name()
            proc.kill() if force else proc.terminate()
        except Exception as exc:
            raise ToolError(f"could not terminate PID {pid}: {exc}") from exc
        return {"pid": pid, "name": name, "terminated": True, "forced": bool(force)}
    if not WINDOWS:
        raise ToolError("proc.kill needs psutil on this platform (pip install psutil)")
    argv = ["taskkill", "/PID", str(pid)] + (["/F"] if force else [])
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    if proc.returncode != 0:
        raise ToolError(proc.stderr.strip() or f"taskkill returned {proc.returncode}")
    return {"pid": pid, "terminated": True, "forced": bool(force)}


@tool(
    "app.open",
    "Open a file, folder or URL with the default application.",
    {"target": "str"},
)
def app_open(ctx: ToolContext, target: str) -> dict[str, Any]:
    if not isinstance(target, str) or not target.strip():
        raise ToolError("target must be a non-empty string")
    target = target.strip()
    parsed = urlparse(target)
    if parsed.scheme in ("http", "https"):
        opened = target
    elif parsed.scheme and len(parsed.scheme) > 1:
        raise ToolError(f"refusing to open the {parsed.scheme}: scheme")
    else:
        opened = str(ctx.resolve(target, must_exist=True))

    if WINDOWS:
        if parsed.scheme in ("http", "https"):
            subprocess.Popen(["cmd", "/c", "start", "", opened], shell=False)
        else:
            os.startfile(opened)  # type: ignore[attr-defined]
    else:
        launcher = shutil.which("xdg-open") or shutil.which("open")
        if not launcher:
            raise ToolError("no xdg-open/open available")
        subprocess.Popen([launcher, opened])
    return {"opened": opened}


@tool("clipboard.get", "Read the Windows clipboard as text.", {}, safe=True)
def clipboard_get(ctx: ToolContext) -> dict[str, Any]:
    if WINDOWS:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0:
            return {"text": proc.stdout.rstrip("\r\n")}
    try:
        import pyperclip  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise ToolError("clipboard access needs pyperclip (pip install pyperclip)") from exc
    return {"text": pyperclip.paste()}


@tool("clipboard.set", "Put text on the clipboard.", {"text": "str"})
def clipboard_set(ctx: ToolContext, text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ToolError("text must be a string")
    if WINDOWS:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
            input=text,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0:
            return {"chars": len(text)}
    try:
        import pyperclip  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise ToolError("clipboard access needs pyperclip (pip install pyperclip)") from exc
    pyperclip.copy(text)
    return {"chars": len(text)}

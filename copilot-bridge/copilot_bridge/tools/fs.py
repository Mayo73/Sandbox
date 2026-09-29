"""File system tools. Every path goes through ToolContext.resolve()."""
from __future__ import annotations

import datetime as _dt
import shutil
from pathlib import Path
from typing import Any

from . import ToolContext, ToolError, tool

MAX_READ_BYTES = 400_000


def _stat(path: Path) -> dict[str, Any]:
    info = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "type": "dir" if path.is_dir() else "file",
        "size": info.st_size,
        "modified": _dt.datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
    }


@tool(
    "fs.list",
    "List the entries of a directory.",
    {"path": "str", "pattern": "str = '*'", "recursive": "bool = false", "limit": "int = 300"},
    safe=True,
)
def fs_list(
    ctx: ToolContext,
    path: str,
    pattern: str = "*",
    recursive: bool = False,
    limit: int = 300,
) -> dict[str, Any]:
    target = ctx.resolve(path, must_exist=True)
    if not target.is_dir():
        raise ToolError(f"not a directory: {target}")
    limit = max(1, min(int(limit), 2000))
    globber = target.rglob if recursive else target.glob
    entries: list[dict[str, Any]] = []
    truncated = False
    for item in globber(pattern):
        if len(entries) >= limit:
            truncated = True
            break
        try:
            entries.append(_stat(item))
        except OSError:
            continue
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return {"path": str(target), "count": len(entries), "truncated": truncated, "entries": entries}


@tool(
    "fs.stat",
    "Metadata for one file or directory.",
    {"path": "str"},
    safe=True,
)
def fs_stat(ctx: ToolContext, path: str) -> dict[str, Any]:
    return _stat(ctx.resolve(path, must_exist=True))


@tool(
    "fs.read",
    "Read a text file.",
    {"path": "str", "max_bytes": f"int = {MAX_READ_BYTES}", "encoding": "str = 'utf-8'"},
    safe=True,
)
def fs_read(
    ctx: ToolContext,
    path: str,
    max_bytes: int = MAX_READ_BYTES,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    target = ctx.resolve(path, must_exist=True)
    if target.is_dir():
        raise ToolError(f"{target} is a directory")
    cap = max(1, min(int(max_bytes), MAX_READ_BYTES))
    data = target.read_bytes()
    truncated = len(data) > cap
    chunk = data[:cap]
    try:
        text = chunk.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = chunk.decode("utf-8", "replace")
        encoding = "utf-8 (replaced invalid bytes)"
    return {
        "path": str(target),
        "bytes": len(data),
        "truncated": truncated,
        "encoding": encoding,
        "text": text,
    }


@tool(
    "fs.write",
    "Write a text file (mode 'w' overwrites, 'a' appends).",
    {"path": "str", "content": "str", "mode": "str = 'w'", "encoding": "str = 'utf-8'"},
)
def fs_write(
    ctx: ToolContext,
    path: str,
    content: str,
    mode: str = "w",
    encoding: str = "utf-8",
) -> dict[str, Any]:
    if mode not in ("w", "a"):
        raise ToolError("mode must be 'w' or 'a'")
    if not isinstance(content, str):
        raise ToolError("content must be a string")
    target = ctx.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    with target.open(mode, encoding=encoding, newline="") as fh:
        fh.write(content)
    return {
        "path": str(target),
        "mode": mode,
        "existed_before": existed,
        "chars_written": len(content),
        "size": target.stat().st_size,
    }


@tool("fs.mkdir", "Create a directory (parents included).", {"path": "str"})
def fs_mkdir(ctx: ToolContext, path: str) -> dict[str, Any]:
    target = ctx.resolve(path)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target), "created": True}


@tool(
    "fs.delete",
    "Delete a file, or a directory when recursive is true.",
    {"path": "str", "recursive": "bool = false"},
)
def fs_delete(ctx: ToolContext, path: str, recursive: bool = False) -> dict[str, Any]:
    target = ctx.resolve(path, must_exist=True)
    if target in ctx.roots:
        raise ToolError(f"refusing to delete the configured root {target}")
    if target.is_dir():
        if not recursive:
            raise ToolError(f"{target} is a directory - pass recursive: true to delete it")
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"path": str(target), "deleted": True}


@tool(
    "fs.move",
    "Move or rename a file or directory.",
    {"src": "str", "dst": "str", "overwrite": "bool = false"},
)
def fs_move(ctx: ToolContext, src: str, dst: str, overwrite: bool = False) -> dict[str, Any]:
    source = ctx.resolve(src, must_exist=True)
    destination = ctx.resolve(dst)
    if destination.exists():
        if not overwrite:
            raise ToolError(f"{destination} exists - pass overwrite: true to replace it")
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return {"src": str(source), "dst": str(destination), "moved": True}


@tool(
    "fs.copy",
    "Copy a file or directory tree.",
    {"src": "str", "dst": "str", "overwrite": "bool = false"},
)
def fs_copy(ctx: ToolContext, src: str, dst: str, overwrite: bool = False) -> dict[str, Any]:
    source = ctx.resolve(src, must_exist=True)
    destination = ctx.resolve(dst)
    if destination.exists() and not overwrite:
        raise ToolError(f"{destination} exists - pass overwrite: true to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=overwrite)
    else:
        shutil.copy2(source, destination)
    return {"src": str(source), "dst": str(destination), "copied": True}


@tool(
    "fs.search",
    "Search file contents for a literal string.",
    {"path": "str", "needle": "str", "pattern": "str = '*'", "limit": "int = 50"},
    safe=True,
)
def fs_search(
    ctx: ToolContext,
    path: str,
    needle: str,
    pattern: str = "*",
    limit: int = 50,
) -> dict[str, Any]:
    if not isinstance(needle, str) or not needle:
        raise ToolError("needle must be a non-empty string")
    root = ctx.resolve(path, must_exist=True)
    limit = max(1, min(int(limit), 500))
    hits: list[dict[str, Any]] = []
    scanned = 0
    for item in root.rglob(pattern):
        if len(hits) >= limit:
            break
        if not item.is_file():
            continue
        scanned += 1
        try:
            if item.stat().st_size > 5_000_000:
                continue
            text = item.read_text("utf-8", "ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if needle in line:
                hits.append({"path": str(item), "line": lineno, "text": line.strip()[:300]})
                break
    return {"root": str(root), "files_scanned": scanned, "hits": hits}

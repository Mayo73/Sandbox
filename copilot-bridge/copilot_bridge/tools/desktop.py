"""Mouse, keyboard, screenshot and window tools.

These need extra packages:  pip install pyautogui pygetwindow pillow
Each tool reports the missing package instead of failing at import time.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from . import ToolContext, ToolError, tool
from ..config import app_dir


def _pyautogui():
    try:
        import pyautogui  # type: ignore[import-not-found]
    except Exception as exc:  # ImportError, or no display / X11 error
        raise ToolError(
            f"desktop control needs pyautogui (pip install pyautogui pillow): {exc}"
        ) from exc
    pyautogui.FAILSAFE = True  # slamming the pointer into a corner aborts
    return pyautogui


def _screens_dir() -> Path:
    path = app_dir() / "screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


@tool("ui.screen_size", "Screen resolution in pixels.", {}, safe=True)
def ui_screen_size(ctx: ToolContext) -> dict[str, Any]:
    pyautogui = _pyautogui()
    width, height = pyautogui.size()
    return {"width": int(width), "height": int(height)}


@tool(
    "ui.screenshot",
    "Save a screenshot and return the file path.",
    {"path": "str = ''  (default: CopilotBridge/screenshots)", "region": "[x, y, w, h] = null"},
    safe=True,
)
def ui_screenshot(ctx: ToolContext, path: str = "", region: list[int] | None = None) -> dict[str, Any]:
    pyautogui = _pyautogui()
    if path:
        target = ctx.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = _screens_dir() / f"shot-{stamp}.png"
    kwargs = {}
    if region:
        if len(region) != 4:
            raise ToolError("region must be [x, y, width, height]")
        kwargs["region"] = tuple(int(v) for v in region)
    image = pyautogui.screenshot(**kwargs)
    image.save(str(target))
    return {"path": str(target), "width": image.width, "height": image.height}


@tool(
    "ui.click",
    "Click the mouse, optionally at absolute coordinates.",
    {"x": "int = null", "y": "int = null", "button": "str = 'left'", "clicks": "int = 1"},
)
def ui_click(
    ctx: ToolContext,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
) -> dict[str, Any]:
    pyautogui = _pyautogui()
    if button not in ("left", "right", "middle"):
        raise ToolError("button must be left, right or middle")
    clicks = max(1, min(int(clicks), 5))
    if x is None or y is None:
        pyautogui.click(button=button, clicks=clicks)
        position = pyautogui.position()
    else:
        pyautogui.click(x=int(x), y=int(y), button=button, clicks=clicks)
        position = (int(x), int(y))
    return {"x": int(position[0]), "y": int(position[1]), "button": button, "clicks": clicks}


@tool("ui.move", "Move the mouse pointer.", {"x": "int", "y": "int", "duration": "float = 0.2"})
def ui_move(ctx: ToolContext, x: int, y: int, duration: float = 0.2) -> dict[str, Any]:
    pyautogui = _pyautogui()
    pyautogui.moveTo(int(x), int(y), duration=max(0.0, min(float(duration), 5.0)))
    return {"x": int(x), "y": int(y)}


@tool("ui.type", "Type text on the keyboard.", {"text": "str", "interval": "float = 0.01"})
def ui_type(ctx: ToolContext, text: str, interval: float = 0.01) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ToolError("text must be a string")
    pyautogui = _pyautogui()
    pyautogui.write(text, interval=max(0.0, min(float(interval), 1.0)))
    return {"chars": len(text)}


@tool(
    "ui.key",
    "Press single keys or a hotkey combination, e.g. ['ctrl', 's'].",
    {"keys": "str | list[str]"},
)
def ui_key(ctx: ToolContext, keys: Any) -> dict[str, Any]:
    pyautogui = _pyautogui()
    if isinstance(keys, str):
        sequence = [keys]
    elif isinstance(keys, list) and all(isinstance(k, str) for k in keys):
        sequence = keys
    else:
        raise ToolError("keys must be a string or a list of strings")
    if len(sequence) == 1:
        pyautogui.press(sequence[0])
    else:
        pyautogui.hotkey(*sequence)
    return {"keys": sequence}


@tool("ui.scroll", "Scroll the mouse wheel (positive = up).", {"amount": "int"})
def ui_scroll(ctx: ToolContext, amount: int) -> dict[str, Any]:
    pyautogui = _pyautogui()
    pyautogui.scroll(int(amount))
    return {"amount": int(amount)}


def _pygetwindow():
    try:
        import pygetwindow  # type: ignore[import-not-found]

        return pygetwindow
    except Exception as exc:
        raise ToolError(
            f"window tools need pygetwindow (pip install pygetwindow): {exc}"
        ) from exc


@tool("window.list", "List open window titles.", {"title_contains": "str = ''"}, safe=True)
def window_list(ctx: ToolContext, title_contains: str = "") -> dict[str, Any]:
    gw = _pygetwindow()
    needle = (title_contains or "").lower()
    windows = []
    for win in gw.getAllWindows():
        title = (win.title or "").strip()
        if not title or (needle and needle not in title.lower()):
            continue
        windows.append(
            {
                "title": title,
                "x": win.left,
                "y": win.top,
                "width": win.width,
                "height": win.height,
                "active": bool(getattr(win, "isActive", False)),
            }
        )
    return {"count": len(windows), "windows": windows}


@tool("window.focus", "Bring the first window matching a title to the front.", {"title": "str"})
def window_focus(ctx: ToolContext, title: str) -> dict[str, Any]:
    gw = _pygetwindow()
    if not isinstance(title, str) or not title.strip():
        raise ToolError("title must be a non-empty string")
    matches = [w for w in gw.getAllWindows() if title.lower() in (w.title or "").lower()]
    if not matches:
        raise ToolError(f"no window matching {title!r}")
    win = matches[0]
    try:
        if getattr(win, "isMinimized", False):
            win.restore()
        win.activate()
    except Exception as exc:
        raise ToolError(f"could not focus {win.title!r}: {exc}") from exc
    return {"title": win.title, "focused": True}

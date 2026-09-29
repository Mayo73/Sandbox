"""A small, synchronous Chrome DevTools Protocol client.

Only what the bridge needs: connect to a page target's WebSocket, call methods,
evaluate JavaScript, dispatch key events. A background thread reads frames and
hands results to the waiting caller.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

try:
    import websocket  # websocket-client
except ModuleNotFoundError:  # pragma: no cover
    websocket = None  # type: ignore[assignment]


class CdpError(RuntimeError):
    pass


def http_json(port: int, path: str, method: str = "GET", timeout: float = 5.0) -> Any:
    """Call the DevTools HTTP endpoint on 127.0.0.1:<port>."""
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method=method)
    # The DevTools HTTP endpoint rejects unknown Host headers on newer builds.
    req.add_header("Host", f"127.0.0.1:{port}")
    try:
        # Never route DevTools traffic through a proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise CdpError(f"DevTools endpoint {url} not reachable: {exc}") from exc
    body = body.strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def list_targets(port: int) -> list[dict[str, Any]]:
    data = http_json(port, "/json/list")
    return data if isinstance(data, list) else []


def browser_version(port: int) -> dict[str, Any]:
    data = http_json(port, "/json/version")
    return data if isinstance(data, dict) else {}


def new_tab(port: int, url: str) -> dict[str, Any]:
    """Open a tab. Chromium 111+ wants PUT here; older builds only accept GET."""
    quoted = urllib.parse.quote(url, safe="")
    for method in ("PUT", "GET"):
        try:
            data = http_json(port, f"/json/new?{quoted}", method=method)
        except CdpError:
            continue
        if isinstance(data, dict) and data.get("webSocketDebuggerUrl"):
            return data
    raise CdpError(f"could not open a new tab for {url}")


class CdpClient:
    """One WebSocket connection to a single DevTools target."""

    def __init__(self, ws_url: str, timeout: float = 20.0) -> None:
        if websocket is None:
            raise CdpError(
                "websocket-client is missing. Install it with:\n"
                "    pip install websocket-client"
            )
        self.ws_url = ws_url
        self.timeout = timeout
        self._ws: Any = None
        self._next_id = 0
        self._lock = threading.Lock()
        self._pending: dict[int, dict[str, Any]] = {}
        self._reader: threading.Thread | None = None
        self._closed = threading.Event()
        self._event_handlers: list[Callable[[str, dict[str, Any]], None]] = []

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> "CdpClient":
        # Chromium 111+ refuses DevTools WebSockets that carry an Origin
        # header, so suppress it (and pass --remote-allow-origins on launch).
        self._ws = websocket.create_connection(
            self.ws_url,
            timeout=self.timeout,
            suppress_origin=True,
            enable_multithread=True,
            max_size=64 * 1024 * 1024,
        )
        self._ws.settimeout(None)
        self._closed.clear()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return self

    def close(self) -> None:
        self._closed.set()
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        with self._lock:
            for slot in self._pending.values():
                slot["error"] = {"message": "connection closed"}
                slot["event"].set()

    def __enter__(self) -> "CdpClient":
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._closed.is_set()

    def on_event(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._event_handlers.append(handler)

    # -- plumbing ----------------------------------------------------------
    def _read_loop(self) -> None:
        while not self._closed.is_set():
            ws = self._ws
            if ws is None:
                break
            try:
                raw = ws.recv()
            except Exception:
                break
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            msg_id = msg.get("id")
            if msg_id is not None:
                with self._lock:
                    slot = self._pending.get(msg_id)
                if slot is not None:
                    slot["result"] = msg.get("result")
                    slot["error"] = msg.get("error")
                    slot["event"].set()
            else:
                method = msg.get("method", "")
                params = msg.get("params") or {}
                for handler in list(self._event_handlers):
                    try:
                        handler(method, params)
                    except Exception:
                        pass
        self._closed.set()
        with self._lock:
            for slot in self._pending.values():
                slot.setdefault("error", {"message": "connection lost"})
                slot["event"].set()

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.connected:
            raise CdpError("not connected")
        with self._lock:
            self._next_id += 1
            msg_id = self._next_id
            slot: dict[str, Any] = {"event": threading.Event()}
            self._pending[msg_id] = slot
        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}})
        try:
            self._ws.send(payload)
        except Exception as exc:
            with self._lock:
                self._pending.pop(msg_id, None)
            raise CdpError(f"send failed for {method}: {exc}") from exc

        if not slot["event"].wait(timeout if timeout is not None else self.timeout):
            with self._lock:
                self._pending.pop(msg_id, None)
            raise CdpError(f"timeout waiting for {method}")
        with self._lock:
            self._pending.pop(msg_id, None)
        if slot.get("error"):
            raise CdpError(f"{method} failed: {slot['error']}")
        return slot.get("result") or {}

    # -- convenience -------------------------------------------------------
    def evaluate(
        self,
        expression: str,
        await_promise: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """Run JS in the page and return the value (must be JSON-serialisable)."""
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "userGesture": True,
            },
            timeout=timeout,
        )
        details = result.get("exceptionDetails")
        if details:
            text = details.get("exception", {}).get("description") or details.get("text")
            raise CdpError(f"JS error: {text}")
        return result.get("result", {}).get("value")

    def key_event(self, key: str, event_type: str, **extra: Any) -> None:
        keymap = {
            "Enter": {"windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter", "text": "\r"},
            "Escape": {"windowsVirtualKeyCode": 27, "key": "Escape", "code": "Escape"},
            "Backspace": {"windowsVirtualKeyCode": 8, "key": "Backspace", "code": "Backspace"},
        }
        params: dict[str, Any] = {"type": event_type}
        params.update(keymap.get(key, {"key": key, "code": key}))
        params.update(extra)
        self.send("Input.dispatchKeyEvent", params)

    def press(self, key: str, **extra: Any) -> None:
        self.key_event(key, "rawKeyDown", **extra)
        if key == "Enter":
            self.key_event(key, "char", **extra)
        self.key_event(key, "keyUp", **extra)


def wait_for_port(port: int, timeout: float = 25.0, interval: float = 0.4) -> bool:
    """Poll the DevTools HTTP endpoint until it answers."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            browser_version(port)
            return True
        except CdpError:
            time.sleep(interval)
    return False

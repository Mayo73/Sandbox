"""A stand-in for Edge's DevTools endpoint.

Serves /json/version, /json/list and /json/new over HTTP and speaks just enough
CDP over a WebSocket for the bridge to talk to it. The page it simulates has a
scripted transcript the test can change between polls.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from websockets.sync.server import serve

SEND_RE = re.compile(r"window\.__copilotBridge\.send\((.*),\s*(true|false)\)\s*$", re.S)


class PageState:
    """What the fake page would show, and what it received."""

    def __init__(self) -> None:
        self.url = "https://copilot.microsoft.com/chats/test"
        self.messages: list[dict[str, Any]] = []
        self.installed = False
        self.install_count = 0
        self.sent: list[dict[str, Any]] = []
        self.keys: list[dict[str, Any]] = []
        self.evaluate_error: str | None = None
        self.strategy = 'selector:[data-content="ai-message"]'
        self.composer_present = True
        self.send_button_present = True
        self.lock = threading.Lock()

    def set_transcript(self, messages: list[dict[str, Any]]) -> None:
        with self.lock:
            self.messages = [
                {
                    "index": i,
                    "role": m.get("role", "assistant"),
                    "text": m.get("text", ""),
                    "code": m.get("code", []),
                }
                for i, m in enumerate(messages)
            ]

    def read_payload(self) -> dict[str, Any]:
        with self.lock:
            return {
                "url": self.url,
                "title": "Copilot",
                "strategy": self.strategy,
                "messages": list(self.messages),
                "composer": "DIV#composer" if self.composer_present else None,
            }


class FakeDevTools:
    def __init__(self) -> None:
        self.state = PageState()
        self._ws_server = serve(self._ws_handler, "127.0.0.1", 0)
        self.ws_port = self._ws_server.socket.getsockname()[1]
        self.ws_url = f"ws://127.0.0.1:{self.ws_port}/devtools/page/FAKE"

        state = self.state
        ws_url = self.ws_url

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # keep test output clean
                pass

            def _json(self, payload: Any, code: int = 200) -> None:
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _target(self) -> dict[str, Any]:
                return {
                    "id": "FAKE",
                    "type": "page",
                    "title": "Copilot",
                    "url": state.url,
                    "webSocketDebuggerUrl": ws_url,
                }

            def do_GET(self) -> None:
                if self.path.startswith("/json/version"):
                    self._json({"Browser": "Edge/FakeForTests", "Protocol-Version": "1.3"})
                elif self.path.startswith("/json/list") or self.path == "/json":
                    self._json([self._target()])
                elif self.path.startswith("/json/new"):
                    self._json({}, code=405)
                else:
                    self._json({"error": "not found"}, code=404)

            def do_PUT(self) -> None:
                if self.path.startswith("/json/new"):
                    self._json(self._target())
                else:
                    self._json({"error": "not found"}, code=404)

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.http_port = self._http.server_address[1]
        self._threads = [
            threading.Thread(target=self._http.serve_forever, daemon=True),
            threading.Thread(target=self._ws_server.serve_forever, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    # -- CDP ---------------------------------------------------------------
    def _evaluate(self, expression: str) -> dict[str, Any]:
        state = self.state
        if state.evaluate_error:
            return {
                "result": {"type": "undefined"},
                "exceptionDetails": {"text": state.evaluate_error},
            }
        if expression.startswith("typeof window.__copilotBridge"):
            return {"result": {"type": "number", "value": 4 if state.installed else False}}
        if "window.__copilotBridge.read(" in expression:
            return {"result": {"type": "object", "value": state.read_payload()}}
        if "window.__copilotBridge.probe(" in expression:
            payload = state.read_payload()
            payload["selectorCounts"] = [{"selector": "x", "hits": len(payload["messages"])}]
            payload["sendButton"] = "Senden"
            return {"result": {"type": "object", "value": payload}}
        match = SEND_RE.search(expression.strip())
        if match:
            if not state.composer_present:
                return {
                    "result": {"type": "object", "value": {"ok": False, "error": "no composer found"}}
                }
            text = json.loads(match.group(1))
            with state.lock:
                state.sent.append({"text": text, "submit": match.group(2) == "true"})
            return {
                "result": {
                    "type": "object",
                    "value": {
                        "ok": True,
                        "method": "execCommand",
                        "clicked": state.send_button_present,
                        "tag": "DIV",
                    },
                }
            }
        # Anything else is the adapter source being injected.
        state.installed = True
        state.install_count += 1
        return {"result": {"type": "string", "value": "installed"}}

    def _ws_handler(self, connection: Any) -> None:
        for raw in connection:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            method = message.get("method", "")
            params = message.get("params") or {}
            if method == "Runtime.evaluate":
                result = self._evaluate(params.get("expression", ""))
            elif method == "Input.dispatchKeyEvent":
                with self.state.lock:
                    self.state.keys.append(params)
                result = {}
            elif method in ("Runtime.enable", "Page.enable", "DOM.enable"):
                result = {}
            else:
                connection.send(
                    json.dumps(
                        {"id": message.get("id"), "error": {"message": f"unsupported: {method}"}}
                    )
                )
                continue
            connection.send(json.dumps({"id": message.get("id"), "result": result}))

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._http.shutdown()
        self._http.server_close()
        self._ws_server.shutdown()

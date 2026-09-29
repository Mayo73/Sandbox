"""Poll the chat transcript and emit messages once they stop changing."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cdp import CdpClient, CdpError
from .config import Config

PROFILE_DIR = Path(__file__).parent / "profiles"


def load_profile(name: str) -> str:
    """Read the page adapter JavaScript."""
    if name in ("", "auto", "default"):
        name = "default"
    path = PROFILE_DIR / f"{name}.js"
    if not path.exists():
        candidates = ", ".join(sorted(p.stem for p in PROFILE_DIR.glob("*.js")))
        raise FileNotFoundError(f"no page profile {name!r} (have: {candidates})")
    return path.read_text(encoding="utf-8")


def ensure_adapter(client: CdpClient, script: str) -> None:
    """(Re)inject the page adapter - a navigation wipes window.__copilotBridge."""
    try:
        present = client.evaluate(
            "typeof window.__copilotBridge === 'object' && window.__copilotBridge.version"
        )
    except CdpError:
        present = None
    if not present:
        client.evaluate(script)


@dataclass
class ChatMessage:
    key: str
    index: int
    role: str
    text: str
    code: list[dict[str, str]] = field(default_factory=list)


@dataclass
class _Slot:
    digest: str
    first_seen: float
    emitted: bool = False


class ChatWatcher:
    def __init__(self, client: CdpClient, config: Config, selector: str = "") -> None:
        self.client = client
        self.config = config
        self.selector = selector
        self.script = load_profile(config.watch.profile)
        self.state: dict[str, _Slot] = {}
        self.url: str | None = None
        self.strategy: str = "?"
        self._primed = False

    # -- page adapter ------------------------------------------------------
    def ensure_installed(self) -> None:
        ensure_adapter(self.client, self.script)

    def read_raw(self) -> dict[str, Any]:
        self.ensure_installed()
        arg = json.dumps(self.selector)
        data = self.client.evaluate(f"window.__copilotBridge.read({arg})")
        if not isinstance(data, dict):
            raise CdpError(f"page adapter returned {type(data).__name__}, expected an object")
        return data

    def probe(self) -> dict[str, Any]:
        self.ensure_installed()
        arg = json.dumps(self.selector)
        return self.client.evaluate(f"window.__copilotBridge.probe({arg})")

    # -- polling -----------------------------------------------------------
    def poll(self) -> list[ChatMessage]:
        """Return messages that have been unchanged for `stable_ms`."""
        data = self.read_raw()
        self.strategy = data.get("strategy", "?")
        url = data.get("url")
        if url != self.url:
            # New conversation or navigation: start over, don't replay history.
            self.url = url
            self.state.clear()
            self._primed = False

        now = time.monotonic()
        stable = self.config.watch.stable_ms / 1000.0
        cap = self.config.watch.max_message_chars
        wanted = set(self.config.watch.roles)
        accept_unknown = self.config.watch.accept_unknown_role
        priming = not self._primed and not self.config.watch.execute_backlog

        ready: list[ChatMessage] = []
        for raw in data.get("messages") or []:
            index = int(raw.get("index", 0))
            role = str(raw.get("role", "unknown"))
            text = str(raw.get("text", ""))[:cap]
            code = [
                {"lang": str(block.get("lang", "")), "text": str(block.get("text", ""))[:cap]}
                for block in (raw.get("code") or [])
                if isinstance(block, dict)
            ]
            key = f"{index}:{role}"
            payload = text + "\u0000" + "\u0000".join(b["text"] for b in code)
            digest = hashlib.sha1(payload.encode("utf-8", "replace")).hexdigest()

            slot = self.state.get(key)
            if slot is None or slot.digest != digest:
                self.state[key] = _Slot(digest=digest, first_seen=now, emitted=priming)
                continue
            if slot.emitted or now - slot.first_seen < stable:
                continue
            slot.emitted = True
            if role not in wanted and not (role == "unknown" and accept_unknown):
                continue
            ready.append(ChatMessage(key=key, index=index, role=role, text=text, code=code))

        self._primed = True
        return ready

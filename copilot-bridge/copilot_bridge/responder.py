"""Write results back into the chat input box."""
from __future__ import annotations

import json
import time

from .cdp import CdpClient, CdpError
from .config import Config
from .watcher import ensure_adapter, load_profile


class Responder:
    def __init__(self, client: CdpClient, config: Config) -> None:
        self.client = client
        self.config = config
        self.script = load_profile(config.watch.profile)

    def post(self, text: str) -> bool:
        if not self.config.respond.enabled:
            return False
        submit = self.config.respond.submit
        payload = json.dumps(text)
        try:
            # The page may have navigated since the last poll.
            ensure_adapter(self.client, self.script)
            result = self.client.evaluate(
                f"window.__copilotBridge.send({payload}, {str(submit).lower()})"
            )
        except CdpError as exc:
            print(f"[respond] could not reach the page: {exc}")
            return False

        if not isinstance(result, dict) or not result.get("ok"):
            reason = (result or {}).get("error", "unknown error")
            print(f"[respond] input box not found: {reason}")
            return False

        if submit and not result.get("clicked"):
            # No send button matched - press Enter as a real key event instead.
            time.sleep(self.config.respond.delay_ms / 1000.0)
            try:
                self.client.press("Enter")
            except CdpError as exc:
                print(f"[respond] Enter key failed: {exc}")
                return False
        return True

"""Append-only JSONL log of everything the bridge was asked to do."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from .config import app_dir


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_dir() / "audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    MAX_FIELD_CHARS = 2000

    def _shrink(self, value: Any) -> Any:
        """Keep one huge result from swamping the log."""
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= self.MAX_FIELD_CHARS:
            return value
        return f"{text[: self.MAX_FIELD_CHARS]}... [{len(text)} chars]"

    def write(self, kind: str, **fields: Any) -> None:
        record = {
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
        }
        record.update({key: self._shrink(value) for key, value in fields.items()})
        line = json.dumps(record, ensure_ascii=False, default=str)
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass  # never let logging break the run

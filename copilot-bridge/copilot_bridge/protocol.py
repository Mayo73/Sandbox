"""Find and parse bridge tool calls inside a chat message.

The wire format is one JSON object carrying the marker key ``bridge``::

    {"bridge": 1, "tool": "fs.list", "args": {"path": "%USERPROFILE%"}, "id": "a1"}

The marker is what makes detection reliable: the browser renders markdown, so
by the time the text reaches us the ``` fences are gone and only the code
block's content survives. We therefore scan the rendered text *and* the
extracted code blocks, and accept balanced JSON wherever it appears.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

MARKER_RE = re.compile(r"<<<\s*BRIDGE(.*?)BRIDGE\s*>>>", re.S | re.I)
FENCE_RE = re.compile(r"```[ \t]*(\w+)?[ \t]*\r?\n(.*?)```", re.S)
SMART_QUOTES = {
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2018": "'", "\u2019": "'", "\u2032": "'", "\u2033": '"',
    "\u00a0": " ",
}

MAX_PAYLOAD_CHARS = 200_000


class ProtocolError(ValueError):
    pass


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    digest: str = ""
    source: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {"bridge": 1, "tool": self.tool, "args": self.args, "id": self.id},
            ensure_ascii=False,
            sort_keys=True,
        )


def _normalise(text: str) -> str:
    for bad, good in SMART_QUOTES.items():
        text = text.replace(bad, good)
    return text


def iter_json_objects(text: str) -> Iterator[str]:
    """Yield substrings of `text` that are balanced ``{...}`` blocks."""
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start : i + 1]
                    start = -1
    return


def _loads(chunk: str) -> Any:
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_normalise(chunk))
    except json.JSONDecodeError:
        return None


def _looks_like_call(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if "bridge" not in obj:
        return False
    return "tool" in obj or "calls" in obj


def _build(obj: dict[str, Any], source: str) -> ToolCall:
    tool = obj.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        raise ProtocolError("'tool' must be a non-empty string")
    args = obj.get("args", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ProtocolError("'args' must be an object")
    call = ToolCall(tool=tool.strip(), args=args, source=source)
    call.digest = hashlib.sha256(call.to_json().encode("utf-8")).hexdigest()
    raw_id = obj.get("id")
    call.id = str(raw_id).strip() if raw_id not in (None, "") else call.digest[:10]
    # Recompute so the digest covers the final id too.
    call.digest = hashlib.sha256(call.to_json().encode("utf-8")).hexdigest()
    return call


def _expand(obj: dict[str, Any], source: str) -> list[ToolCall]:
    calls = obj.get("calls")
    if isinstance(calls, list):
        out: list[ToolCall] = []
        for entry in calls:
            if isinstance(entry, dict):
                merged = dict(entry)
                merged.setdefault("bridge", obj.get("bridge", 1))
                out.append(_build(merged, source))
        return out
    return [_build(obj, source)]


def extract_calls(
    text: str, code_blocks: list[dict[str, str]] | None = None
) -> tuple[list[ToolCall], list[str]]:
    """Return (calls, errors) found in a rendered chat message.

    `code_blocks` are the ``<pre>``/``<code>`` contents the page adapter pulled
    out of the same message; markdown rendering strips the fences, so those are
    usually where the payload actually lives.
    """
    calls: list[ToolCall] = []
    errors: list[str] = []
    seen: set[str] = set()

    def consume(chunk: str, source: str) -> None:
        if len(chunk) > MAX_PAYLOAD_CHARS:
            errors.append(f"payload from {source} exceeds {MAX_PAYLOAD_CHARS} chars")
            return
        obj = _loads(chunk)
        if not _looks_like_call(obj):
            return
        try:
            for call in _expand(obj, source):
                if call.digest in seen:
                    continue
                seen.add(call.digest)
                calls.append(call)
        except ProtocolError as exc:
            errors.append(f"{source}: {exc}")

    sources: list[tuple[str, str]] = []
    for block in code_blocks or []:
        body = block.get("text") or ""
        if body.strip():
            sources.append((body, f"code[{block.get('lang') or 'plain'}]"))
    for match in MARKER_RE.finditer(text or ""):
        sources.append((match.group(1), "marker"))
    for match in FENCE_RE.finditer(text or ""):
        sources.append((match.group(2), f"fence[{match.group(1) or 'plain'}]"))
    if text:
        sources.append((text, "text"))

    for body, source in sources:
        for chunk in iter_json_objects(body):
            consume(chunk, source)

    return calls, errors


def format_result(call_id: str, ok: bool, payload: Any, max_chars: int = 3500) -> str:
    """Render a result the way the chat should see it."""
    body = {"bridge_result": 1, "id": call_id, "ok": ok}
    if ok:
        body["result"] = payload
    else:
        body["error"] = str(payload)
    text = json.dumps(body, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text

    key = "result" if ok else "error"
    raw = json.dumps(body.get(key), ensure_ascii=False, default=str)
    envelope = dict(body)
    envelope["truncated"] = True
    envelope[key] = ""
    overhead = len(json.dumps(envelope, ensure_ascii=False, default=str))
    note = f"... [truncated, {len(raw)} chars total]"
    keep = max_chars - overhead - len(note) - 8   # slack for JSON escaping
    if keep < 40:
        envelope[key] = note.strip(". ")
    else:
        envelope[key] = raw[:keep] + note
    return json.dumps(envelope, ensure_ascii=False, default=str)

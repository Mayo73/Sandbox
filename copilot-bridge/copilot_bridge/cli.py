"""Command line interface and the watch loop."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

from . import __version__
from .audit import AuditLog
from .cdp import CdpError, browser_version
from .config import Config, app_dir
from .edge import attach_chat, describe_targets, find_edge, launch
from .executor import ExecResult, Executor
from .policy import Policy
from .protocol import extract_calls, format_result
from .responder import Responder
from .tools import REGISTRY, load_all
from .watcher import ChatMessage, ChatWatcher

RESULT_PREFIX = "[bridge] Ergebnis"


class SeenCalls:
    """Remembers recently executed calls so a message is never run twice.

    The transcript is re-read every poll and Copilot may repeat a payload, so
    dedup is by call digest rather than by message.
    """

    def __init__(self, maxlen: int = 800) -> None:
        self._order: deque[str] = deque(maxlen=maxlen)
        self._members: set[str] = set()

    def __contains__(self, digest: str) -> bool:
        return digest in self._members

    def add(self, digest: str) -> None:
        if digest in self._members:
            return
        if len(self._order) == self._order.maxlen:
            self._members.discard(self._order[0])
        self._order.append(digest)
        self._members.add(digest)


def process_message(
    message: ChatMessage,
    executor: Executor,
    responder: Responder | None,
    cfg: Config,
    seen: SeenCalls,
) -> list[ExecResult]:
    """Run every new tool call in one chat message and post the results back."""
    if message.text.startswith(RESULT_PREFIX):
        return []
    calls, errors = extract_calls(message.text, message.code)
    for error in errors:
        print(f"[parse] {error}")
    if not calls:
        return []

    print(f"\n[chat] {message.role} message #{message.index}: {len(calls)} tool call(s)")
    results: list[ExecResult] = []
    replies: list[str] = []
    for call in calls:
        if call.digest in seen:
            continue
        seen.add(call.digest)
        result = executor.run(call)
        results.append(result)
        replies.append(
            format_result(call.id, result.ok, result.payload, cfg.respond.max_result_chars)
        )

    if replies and cfg.respond.enabled and responder is not None:
        body = RESULT_PREFIX + ":\n" + "\n".join(replies)
        if responder.post(body):
            print(f"[respond] posted {len(replies)} result(s) back to the chat")
    return results


def apply_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    if getattr(args, "port", None):
        cfg.edge.port = args.port
    if getattr(args, "url", None):
        cfg.edge.start_url = args.url
    if getattr(args, "mode", None):
        cfg.policy.mode = args.mode
    if getattr(args, "attach", False):
        cfg.edge.attach_only = True
    if getattr(args, "no_respond", False):
        cfg.respond.enabled = False
    if getattr(args, "real_profile", False):
        cfg.edge.use_existing_profile = True
    return cfg


def load_config(args: argparse.Namespace) -> Config:
    path = getattr(args, "config", None)
    if path is None:
        default = Path("config.toml")
        path = str(default) if default.exists() else None
    return apply_overrides(Config.load(path), args)


# --------------------------------------------------------------- subcommands
def cmd_tools(args: argparse.Namespace) -> int:
    load_all()
    cfg = load_config(args)
    print(f"{len(REGISTRY)} tools (policy.mode = {cfg.policy.mode})\n")
    for spec in sorted(REGISTRY.values(), key=lambda s: s.name):
        flag = "safe" if spec.safe else "----"
        print(f"  [{flag}] {spec.signature()}")
        print(f"         {spec.description}")
    print("\nallowed_roots:")
    roots = [str(r) for r in cfg.allowed_roots()] or ["(none - file tools are disabled)"]
    for root in roots:
        print(f"  {root}")
    return 0


def cmd_targets(args: argparse.Namespace) -> int:
    cfg = load_config(args)
    try:
        version = browser_version(cfg.edge.port)
    except CdpError as exc:
        print(f"No DevTools endpoint on port {cfg.edge.port}: {exc}")
        return 1
    print(f"Browser: {version.get('Browser')}")
    print(f"Targets on port {cfg.edge.port}:")
    print(describe_targets(cfg.edge.port))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args)
    ok = True
    print(f"copilot-bridge {__version__}")
    print(f"python            {sys.version.split()[0]}")
    print(f"config            {cfg.source}")

    try:
        import websocket  # noqa: F401

        print("websocket-client  installed")
    except ModuleNotFoundError:
        print("websocket-client  MISSING -> pip install websocket-client")
        ok = False
    for name, hint in (
        ("psutil", "process tools"),
        ("pyautogui", "mouse/keyboard/screenshot tools"),
        ("pygetwindow", "window tools"),
        ("pyperclip", "clipboard fallback"),
    ):
        try:
            __import__(name)
            print(f"{name:<17} installed      ({hint})")
        except Exception:
            print(f"{name:<17} not installed  ({hint} unavailable)")

    try:
        print(f"edge              {find_edge(cfg.edge.executable)}")
    except FileNotFoundError as exc:
        print(f"edge              NOT FOUND -> {exc}")
        ok = False

    try:
        version = browser_version(cfg.edge.port)
        print(f"port {cfg.edge.port}         open ({version.get('Browser')})")
    except CdpError:
        print(f"port {cfg.edge.port}         closed (will be opened by 'run')")

    roots = cfg.allowed_roots()
    print(f"allowed_roots     {len(roots)} configured")
    for root in roots:
        print(f"                  {root}{'' if root.exists() else '   (missing)'}")
    if not roots:
        print("                  file tools stay disabled until you add some")
    print(f"state dir         {app_dir()}")
    print(f"policy            {Policy(cfg, interactive=False).describe()}")
    return 0 if ok else 1


def cmd_probe(args: argparse.Namespace) -> int:
    cfg = load_config(args)
    launch(cfg)
    client, _ = attach_chat(cfg)
    try:
        watcher = ChatWatcher(client, cfg, selector=args.selector or "")
        print(json.dumps(watcher.probe(), indent=2, ensure_ascii=False)[:20000])
    finally:
        client.close()
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path or "config.toml")
    template = Path(__file__).parent.parent / "config.example.toml"
    if target.exists() and not args.force:
        print(f"{target} already exists (use --force to overwrite)")
        return 1
    target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"wrote {target.resolve()}")
    return 0


# ------------------------------------------------------------------ run loop
def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args)
    print(f"copilot-bridge {__version__}   config: {cfg.source}")

    proc = launch(cfg)
    client, _ = attach_chat(cfg)

    policy = Policy(cfg, interactive=sys.stdin.isatty())
    executor = Executor(cfg, policy, AuditLog())
    responder = Responder(client, cfg)
    watcher = ChatWatcher(client, cfg, selector=args.selector or "")

    print(f"  policy   {policy.describe()}")
    print(f"  roots    {', '.join(str(r) for r in executor.ctx.roots) or '(none)'}")
    print(f"  respond  {'on' if cfg.respond.enabled else 'off'}")
    print(f"  audit    {executor.audit.path}")
    if cfg.policy.mode == "auto":
        print("\n  !! policy.mode = auto: every call runs without asking.")
    print("\n  Watching the chat. Ctrl+C to stop.\n")

    seen = SeenCalls()
    interval = max(0.1, cfg.watch.poll_ms / 1000.0)
    misses = 0

    try:
        while True:
            try:
                messages = watcher.poll()
                misses = 0
            except CdpError as exc:
                misses += 1
                print(f"[watch] lost the page ({exc}); reattaching...")
                client.close()
                time.sleep(min(2 * misses, 10))
                try:
                    client, _ = attach_chat(cfg, quiet=True)
                except (CdpError, OSError) as exc2:
                    print(f"[watch] reattach failed: {exc2}")
                    if misses > 10:
                        print("[watch] giving up")
                        return 1
                    continue
                responder = Responder(client, cfg)
                watcher = ChatWatcher(client, cfg, selector=args.selector or "")
                continue

            for message in messages:
                process_message(message, executor, responder, cfg, seen)

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        client.close()
        if getattr(args, "close_edge", False) and proc is not None:
            proc.terminate()
            print("  Edge closed.")
    return 0


# ------------------------------------------------------------------ argparse
def global_options() -> argparse.ArgumentParser:
    """Options accepted before *and* after the subcommand.

    SUPPRESS keeps absent flags out of the namespace, so the subparser copy
    never overwrites a value given ahead of the subcommand.
    """
    shared = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    shared.add_argument("-c", "--config", help="path to config.toml")
    shared.add_argument("--port", type=int, help="DevTools port (default 9222)")
    shared.add_argument("--url", help="chat URL to open")
    shared.add_argument(
        "--attach", action="store_true", help="never launch Edge, only attach"
    )
    shared.add_argument(
        "--real-profile",
        action="store_true",
        help="use your normal Edge profile (close all Edge windows first)",
    )
    return shared


def build_parser() -> argparse.ArgumentParser:
    shared = global_options()
    parser = argparse.ArgumentParser(
        prog="copilot-bridge",
        parents=[shared],
        description=(
            "Start Edge with remote debugging, watch a Copilot chat and run the "
            "local tools the chat asks for."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser(
        "run", parents=[shared], help="watch the chat and execute tool calls (default)"
    )
    run.add_argument("--mode", choices=Policy.MODES, help="override policy.mode")
    run.add_argument("--no-respond", action="store_true", help="do not post results back")
    run.add_argument("--selector", default="", help="CSS selector for chat messages")
    run.add_argument("--close-edge", action="store_true", help="close Edge on exit")
    run.set_defaults(func=cmd_run)

    probe = sub.add_parser(
        "probe", parents=[shared], help="show what the page adapter finds in the chat"
    )
    probe.add_argument("--selector", default="", help="CSS selector to try first")
    probe.set_defaults(func=cmd_probe)

    targets = sub.add_parser("targets", parents=[shared], help="list DevTools targets")
    targets.set_defaults(func=cmd_targets)

    doctor = sub.add_parser(
        "doctor", parents=[shared], help="check Edge, ports, packages and config"
    )
    doctor.set_defaults(func=cmd_doctor)

    tools = sub.add_parser("tools", parents=[shared], help="list the available tools")
    tools.set_defaults(func=cmd_tools)

    init = sub.add_parser("init", help="write a config.toml template")
    init.add_argument("path", nargs="?", help="target path (default ./config.toml)")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    return parser


COMMANDS = ("run", "probe", "targets", "doctor", "tools", "init")
VALUE_FLAGS = ("-c", "--config", "--port", "--url", "--mode", "--selector")


def has_subcommand(argv: list[str]) -> bool:
    """True if one of the subcommand names appears as a command, not as a value."""
    skip = False
    for token in argv:
        if skip:
            skip = False
            continue
        if token in VALUE_FLAGS:
            skip = True
            continue
        if token.startswith("-"):
            continue
        return token in COMMANDS
    return False


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    wants_help = any(t in ("-h", "--help", "--version") for t in argv)
    if not wants_help and not has_subcommand(argv):
        argv.insert(0, "run")
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except (CdpError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

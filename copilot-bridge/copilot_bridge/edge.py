"""Find, launch and attach to Microsoft Edge with remote debugging enabled."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .cdp import CdpClient, CdpError, list_targets, new_tab, wait_for_port
from .config import Config

WINDOWS = os.name == "nt"

CANDIDATE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge Beta\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge Dev\Application\msedge.exe",
]


def find_edge(explicit: str = "") -> str:
    """Locate msedge.exe: config value, registry, well-known paths, PATH."""
    if explicit:
        p = Path(os.path.expandvars(explicit))
        if not p.exists():
            raise FileNotFoundError(f"edge.executable does not exist: {p}")
        return str(p)

    if WINDOWS:
        try:
            import winreg  # type: ignore[import-not-found]

            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(
                        root,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
                    )
                    with key:
                        value, _ = winreg.QueryValueEx(key, "")
                    if value and Path(value).exists():
                        return str(value)
                except OSError:
                    continue
        except ModuleNotFoundError:
            pass

    for candidate in CANDIDATE_PATHS:
        if Path(candidate).exists():
            return candidate

    for name in ("msedge", "msedge.exe", "microsoft-edge", "microsoft-edge-stable"):
        found = shutil.which(name)
        if found:
            return found

    raise FileNotFoundError(
        "Microsoft Edge not found. Set edge.executable in the config file."
    )


def edge_is_running() -> bool:
    """True if any msedge process is already up (Windows only, best effort)."""
    if not WINDOWS:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq msedge.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        return False
    return "msedge.exe" in out


def build_args(cfg: Config, executable: str) -> list[str]:
    edge = cfg.edge
    args = [
        executable,
        f"--remote-debugging-port={edge.port}",
        # Chromium 111+ blocks DevTools WebSockets with an Origin header; this
        # flag plus suppress_origin on the client side keeps the socket open.
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if not edge.use_existing_profile:
        profile_dir = edge.resolved_user_data_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        args.append(f"--user-data-dir={profile_dir}")
    args.extend(edge.extra_args)
    if edge.start_url:
        args.append(edge.start_url)
    return args


def launch(cfg: Config, quiet: bool = False) -> subprocess.Popen[bytes] | None:
    """Start Edge with the debugging port open; return None if already up."""
    port = cfg.edge.port
    if wait_for_port(port, timeout=0.6):
        try:
            list_targets(port)
            if not quiet:
                print(f"[edge] debugging port {port} is already open - attaching")
            return None
        except CdpError:
            pass

    if cfg.edge.attach_only:
        raise CdpError(
            f"attach_only is set but nothing is listening on port {port}. "
            "Start Edge with --remote-debugging-port first."
        )

    executable = find_edge(cfg.edge.executable)
    if cfg.edge.use_existing_profile and edge_is_running():
        raise RuntimeError(
            "edge.use_existing_profile is true but Edge is already running.\n"
            "A second Edge process just hands the URL to the running one and the\n"
            "debugging port never opens. Close every Edge window (check the tray\n"
            "and Task Manager for msedge.exe) and try again - or leave\n"
            "use_existing_profile = false to use the separate bridge profile."
        )

    args = build_args(cfg, executable)
    if not quiet:
        print(f"[edge] starting: {executable}")
        print(f"[edge]   port={port} profile={'real' if cfg.edge.use_existing_profile else cfg.edge.resolved_user_data_dir()}")
    creationflags = 0
    if WINDOWS:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    if not wait_for_port(port, timeout=30.0):
        raise CdpError(
            f"Edge started but port {port} never answered.\n"
            "Common causes: another Edge instance owns the profile, or a policy\n"
            "blocks remote debugging. Try a different edge.port."
        )
    return proc


def page_targets(port: int) -> list[dict[str, Any]]:
    """Attachable targets (normal pages plus Edge's sidebar web views)."""
    out = []
    for target in list_targets(port):
        if target.get("type") in ("page", "webview", "iframe") and target.get(
            "webSocketDebuggerUrl"
        ):
            out.append(target)
    return out


def match_target(
    targets: list[dict[str, Any]], patterns: list[str]
) -> dict[str, Any] | None:
    for pattern in patterns:
        needle = pattern.lower()
        for target in targets:
            url = (target.get("url") or "").lower()
            if needle in url:
                return target
    return None


def attach_chat(cfg: Config, quiet: bool = False) -> tuple[CdpClient, dict[str, Any]]:
    """Attach to the Copilot tab, opening it first if it is not there."""
    port = cfg.edge.port
    target = match_target(page_targets(port), cfg.watch.target_url_contains)
    if target is None:
        if not quiet:
            print(f"[edge] no Copilot tab found - opening {cfg.edge.start_url}")
        target = new_tab(port, cfg.edge.start_url)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            found = match_target(page_targets(port), cfg.watch.target_url_contains)
            if found:
                target = found
                break
            time.sleep(0.5)

    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise CdpError(f"target has no WebSocket URL: {target}")
    client = CdpClient(ws_url).connect()
    for domain in ("Runtime.enable", "Page.enable"):
        try:
            client.send(domain)
        except CdpError:
            pass   # not every target type supports both; evaluate works anyway
    if not quiet:
        print(f"[edge] attached to: {target.get('title') or target.get('url')}")
    return client, target


def describe_targets(port: int) -> str:
    lines = []
    for target in list_targets(port):
        lines.append(
            f"  {target.get('type', '?'):<8} {target.get('title', '')[:50]:<52} {target.get('url', '')[:90]}"
        )
    return "\n".join(lines) or "  (none)"

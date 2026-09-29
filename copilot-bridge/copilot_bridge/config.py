"""Configuration loading (TOML) with defaults."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - only on <3.11
    tomllib = None


def app_dir() -> Path:
    """Per-user directory for the bridge's own state (profile, logs)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if not base:
        base = str(Path.home() / ".local" / "state")
    return Path(base) / "CopilotBridge"


def expand(p: str) -> str:
    return os.path.expandvars(os.path.expanduser(p))


@dataclass
class EdgeConfig:
    executable: str = ""                       # "" => auto-detect
    port: int = 9222
    user_data_dir: str = ""                    # "" => <app_dir>/EdgeProfile
    start_url: str = "https://copilot.microsoft.com/"
    use_existing_profile: bool = False         # True => your real Edge profile
    attach_only: bool = False                  # don't launch, just attach
    extra_args: list[str] = field(default_factory=list)

    def resolved_user_data_dir(self) -> Path:
        if self.user_data_dir:
            return Path(expand(self.user_data_dir))
        return app_dir() / "EdgeProfile"


@dataclass
class WatchConfig:
    target_url_contains: list[str] = field(
        default_factory=lambda: [
            "copilot.microsoft.com",
            "m365.cloud.microsoft",
            "www.bing.com/chat",
            "edgeservices.bing.com",
        ]
    )
    poll_ms: int = 700
    stable_ms: int = 1500
    roles: list[str] = field(default_factory=lambda: ["assistant"])
    accept_unknown_role: bool = True
    profile: str = "auto"                      # JS profile name in profiles/
    max_message_chars: int = 40000
    execute_backlog: bool = False              # run calls already on screen at startup


@dataclass
class PolicyConfig:
    mode: str = "ask"                          # ask | auto_safe | auto
    allowed_tools: list[str] = field(default_factory=list)   # [] => every tool
    denied_tools: list[str] = field(default_factory=list)
    allowed_roots: list[str] = field(
        default_factory=lambda: [
            "%USERPROFILE%\\Desktop",
            "%USERPROFILE%\\Documents",
            "%USERPROFILE%\\Downloads",
            "%TEMP%",
        ]
    )
    shell_denylist: list[str] = field(
        default_factory=lambda: [
            "format ", "diskpart", "vssadmin delete", "bcdedit",
            "cipher /w", "rd /s /q c:\\", "rmdir /s /q c:\\",
            "remove-item -recurse -force c:\\", "mklink /j c:\\",
            "shutdown", "reg delete hklm", "takeown /f c:\\",
        ]
    )
    max_calls_per_minute: int = 20
    confirm_timeout_s: int = 180
    max_output_chars: int = 8000


@dataclass
class RespondConfig:
    enabled: bool = True
    max_result_chars: int = 3500
    submit: bool = True                        # press Enter after inserting
    delay_ms: int = 400


@dataclass
class Config:
    edge: EdgeConfig = field(default_factory=EdgeConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    respond: RespondConfig = field(default_factory=RespondConfig)
    source: str = "<defaults>"

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None) -> "Config":
        cfg = cls()
        if path is None:
            return cfg
        p = Path(expand(str(path)))
        if not p.exists():
            raise FileNotFoundError(f"config file not found: {p}")
        if tomllib is None:
            raise RuntimeError(
                "TOML config needs Python 3.11+ (or install 'tomli'). "
                f"Running {sys.version_info.major}.{sys.version_info.minor}."
            )
        with p.open("rb") as fh:
            data: dict[str, Any] = tomllib.load(fh)
        cfg.source = str(p)
        for section, obj in (
            ("edge", cfg.edge),
            ("watch", cfg.watch),
            ("policy", cfg.policy),
            ("respond", cfg.respond),
        ):
            values = data.get(section) or {}
            if not isinstance(values, dict):
                raise ValueError(f"[{section}] must be a table")
            for key, value in values.items():
                if not hasattr(obj, key):
                    raise ValueError(f"unknown option [{section}].{key}")
                setattr(obj, key, value)
        return cfg

    def allowed_roots(self) -> list[Path]:
        roots: list[Path] = []
        for raw in self.policy.allowed_roots:
            expanded = expand(raw)
            if "%" in expanded:      # unresolved Windows var on this machine
                continue
            try:
                roots.append(Path(expanded).resolve())
            except OSError:
                continue
        return roots

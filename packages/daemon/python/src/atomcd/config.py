"""Daemon configuration and environment overrides.

Bind localhost by default; ``ATOMCD_HOST`` / ``ATOMCD_PORT`` override per the RPC contract.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7437
DEFAULT_STATE_DIR = Path.home() / ".atomc"


def generate_token() -> str:
    """Return a random bearer token (>= 32 bytes of entropy, URL-safe)."""
    return secrets.token_urlsafe(32)


class DaemonConfig(BaseSettings):
    """Runtime configuration for one ``atomcd`` instance.

    Loaded from explicit arguments, then environment variables prefixed ``ATOMCD_``.
    """

    model_config = SettingsConfigDict(env_prefix="ATOMCD_", extra="ignore")

    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    project_root: Path = Field(default_factory=Path.cwd)
    state_dir: Path = Field(default_factory=lambda: DEFAULT_STATE_DIR.expanduser())
    token: str = Field(default_factory=generate_token)
    default_lock_ttl_s: int = Field(default=300, ge=1)

    @property
    def state_file(self) -> Path:
        return self.state_dir / "daemon.json"

    @property
    def token_file(self) -> Path:
        return self.state_dir / "token"

    def with_project(self, project: str | Path) -> DaemonConfig:
        """Return a copy pointing at ``project`` (resolved to an absolute path)."""
        root = Path(project).expanduser()
        if not root.is_absolute():
            root = Path.cwd() / root
        return self.model_copy(update={"project_root": root.resolve()})

    @property
    def effective_token(self) -> str:
        """Token from the environment (``ATOMCD_TOKEN``) if set, else a fresh random one."""
        env = os.environ.get("ATOMCD_TOKEN")
        return env if env else self.token


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_STATE_DIR",
    "DaemonConfig",
    "generate_token",
]

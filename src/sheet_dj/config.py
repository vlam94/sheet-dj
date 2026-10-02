"""Settings read from the environment once, at start-up."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

APP_NAME = "sheet-dj"  # what /healthz answers, so the launcher can tell this app from another


@dataclass(frozen=True)
class Config:
    """The app's settings; the defaults are what users get."""

    port: int = 5118
    idle_minutes: float = 20
    max_upload_mb: int = 20
    max_files: int = 20

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        """Read the `SHEETDJ_*` variables; unset ones keep their default."""
        source = os.environ if env is None else env
        defaults = cls()
        return cls(
            port=int(source.get("SHEETDJ_PORT", defaults.port)),
            idle_minutes=float(source.get("SHEETDJ_IDLE_MINUTES", defaults.idle_minutes)),
            max_upload_mb=int(source.get("SHEETDJ_MAX_UPLOAD_MB", defaults.max_upload_mb)),
            max_files=int(source.get("SHEETDJ_MAX_FILES", defaults.max_files)),
        )

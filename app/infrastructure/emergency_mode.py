from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


_ENV_NAME = "AL_MANARA_EMERGENCY_MODE"


@dataclass(frozen=True, slots=True)
class EmergencyModeConfig:
    enabled: bool = False

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "EmergencyModeConfig":
        raw = environment.get(_ENV_NAME, "").strip().lower()
        if raw not in {"", "0", "1", "false", "true", "off", "on"}:
            raise RuntimeError(f"{_ENV_NAME} must be one of: 0, 1, false, true, off, on")
        return cls(enabled=raw in {"1", "true", "on"})

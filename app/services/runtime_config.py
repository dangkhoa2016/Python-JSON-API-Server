from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RateLimitConfig:
    enabled: bool
    max_requests: int
    window_ms: int

    def update(self, updates: Mapping[str, Any]) -> None:
        if "enabled" in updates:
            self.enabled = bool(updates["enabled"])
        if "max" in updates:
            self.max_requests = max(1, int(updates["max"]))
        if "windowMs" in updates:
            self.window_ms = max(1_000, int(updates["windowMs"]))

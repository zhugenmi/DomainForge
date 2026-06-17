from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_retries: int = 2
    cooldown_ms: int = 0

    def should_retry(self, retries: int) -> bool:
        return retries < self.max_retries


__all__ = ["RetryPolicy"]

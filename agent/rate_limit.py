"""Simple client-side request pacing with exponential backoff helpers."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Rolling-window limiter. Default aligns with common Reddit guidance (~60/min)."""

    max_requests: int = 60
    window_seconds: float = 60.0
    _timestamps: deque[float] = field(default_factory=deque)

    def wait_turn(self) -> None:
        now = time.monotonic()
        while self._timestamps and now - self._timestamps[0] >= self.window_seconds:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_requests:
            sleep_for = self.window_seconds - (now - self._timestamps[0]) + 0.01
            if sleep_for > 0:
                time.sleep(sleep_for)
            return self.wait_turn()
        self._timestamps.append(time.monotonic())


def backoff_seconds(attempt: int, base: float = 1.0, cap: float = 32.0) -> float:
    """Exponential delay: 1s, 2s, 4s, 8s… capped."""
    return min(cap, base * (2 ** max(0, attempt)))

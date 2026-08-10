"""Per-agent token bucket — so a looping agent cannot fill the database.

In-process by design: this server is a single process in front of SQLite. When
a Postgres + multi-worker deployment matters, this moves behind an interface;
until then a dict and a clock are the honest implementation.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass
class RateLimiter:
    per_minute: int
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        rate = self.per_minute / 60.0
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = self._buckets[key] = _Bucket(tokens=float(self.per_minute), updated=now)
            b.tokens = min(self.per_minute, b.tokens + (now - b.updated) * rate)
            b.updated = now
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return True
            return False

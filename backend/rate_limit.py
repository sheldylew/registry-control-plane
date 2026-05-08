from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Optional


@dataclass
class FixedWindowRateLimiter:
    max_attempts: int
    window_seconds: float
    _attempts: dict[str, deque[float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def _prune(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def retry_after(self, key: str) -> Optional[int]:
        now = monotonic()
        with self._lock:
            bucket = self._attempts.get(key)
            if not bucket:
                return None
            self._prune(bucket, now)
            if len(bucket) < self.max_attempts:
                if not bucket:
                    self._attempts.pop(key, None)
                return None
            return max(1, int(bucket[0] + self.window_seconds - now))

    def add_failure(self, key: str) -> Optional[int]:
        now = monotonic()
        with self._lock:
            bucket = self._attempts.setdefault(key, deque())
            self._prune(bucket, now)
            bucket.append(now)
            if len(bucket) >= self.max_attempts:
                return max(1, int(bucket[0] + self.window_seconds - now))
            return None

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

"""Retry policy for transient exchange errors.

The trading loop used to repeat the same backoff arithmetic in three
separate exception handlers. The policy lives here so every failure mode
waits the same amount of time and the loop only decides *what* failed.
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_DELAY_SECONDS = 2
MAX_DELAY_SECONDS = 60
BACKOFF_FACTOR = 2


@dataclass
class BackoffPolicy:
    """Exponential backoff with a bounded delay."""

    base_delay: int = BASE_DELAY_SECONDS
    max_delay: int = MAX_DELAY_SECONDS
    factor: int = BACKOFF_FACTOR

    def delay_for(self, attempt: int) -> float:
        """Return the delay to wait before the given retry attempt."""
        if attempt < 1:
            return 0.0
        return min(self.max_delay, self.base_delay * (self.factor ** attempt))

"""Throttled transfer progress logging without URLs or credentials."""
import logging
import time

log = logging.getLogger("shofly_worker")


class TransferProgress:
    def __init__(self, stage: str, interval: float = 3.0):
        self.stage = stage
        self.interval = interval
        self.started = None
        self.last = 0.0
        self.total = None

    def start(self, total: int | None):
        self.started = time.monotonic()
        self.last = 0.0
        self.total = total if total and total > 0 else None
        log.info("%s_started total_mb=%s", self.stage,
                 f"{self.total / 1048576:.1f}" if self.total else "unknown")

    def update(self, current: int):
        now = time.monotonic()
        if now - self.last < self.interval and (not self.total or current < self.total):
            return
        self.last = now
        elapsed = max(now - self.started, 0.001)
        speed = current / elapsed
        percent = f"{100 * current / self.total:.1f}%" if self.total else "unknown"
        eta = f"{max(0, (self.total - current) / speed):.0f}s" if self.total and speed > 0 else "unknown"
        log.info("%s_progress percent=%s transferred_mb=%.1f total_mb=%s speed_mb_s=%.2f eta=%s",
                 self.stage, percent, current / 1048576,
                 f"{self.total / 1048576:.1f}" if self.total else "unknown",
                 speed / 1048576, eta)

    def finish(self, current: int):
        self.update(current)
        log.info("%s_finished transferred_mb=%.1f elapsed_s=%.1f",
                 self.stage, current / 1048576, time.monotonic() - self.started)

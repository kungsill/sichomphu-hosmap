"""นาฬิกากลางของระบบ

ใช้งานจริง: เวลาปัจจุบันของเครื่อง
โหมดสาธิต: นาฬิกาจำลองที่เดินเร็วกว่าเวลาจริง (DEMO_SPEED) เริ่มจาก DEMO_START_TIME ของวันนี้
"""
import threading
import time
from datetime import datetime, timedelta

from . import config


class Clock:
    def __init__(self, speed: float = 1.0, start: datetime | None = None):
        self.speed = speed
        self._lock = threading.Lock()
        self._real0 = time.monotonic()
        self._sim0 = start or datetime.now()
        self._offset = timedelta(0)

    def now(self) -> datetime:
        if self.speed == 1.0 and not config.IS_DEMO:
            return datetime.now().replace(microsecond=0)
        with self._lock:
            elapsed = (time.monotonic() - self._real0) * self.speed
            return (self._sim0 + self._offset + timedelta(seconds=elapsed)).replace(microsecond=0)

    def advance(self, delta: timedelta) -> None:
        """เลื่อนเวลาจำลองไปข้างหน้า (ใช้ตอนอุ่นเครื่องข้อมูลสาธิต)"""
        with self._lock:
            self._offset += delta

    def today(self):
        return self.now().date()


def _demo_start() -> datetime:
    hh, mm = (int(x) for x in config.DEMO_START_TIME.split(":"))
    return datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)


clock = Clock(config.DEMO_SPEED, _demo_start()) if config.IS_DEMO else Clock(1.0)

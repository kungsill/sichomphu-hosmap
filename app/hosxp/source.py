"""อ่านข้อมูลจาก HOSxP V4 (หรือฐานข้อมูลจำลอง) แบบอ่านอย่างเดียว"""
import configparser
import logging
from datetime import date, datetime, time, timedelta

import sqlalchemy as sa

from .. import config

log = logging.getLogger("hosxp.source")


def load_queries(mode: str) -> dict:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config.HOSXP_QUERY_FILE, encoding="utf-8")
    if mode not in parser:
        raise RuntimeError(f"ไม่พบหมวด [{mode}] ใน {config.HOSXP_QUERY_FILE}")
    section = parser[mode]
    return {"visits": section.get("visits", "").strip(), "orders": section.get("orders", "").strip()}


class HosxpSource:
    def __init__(self, url: str, mode: str):
        self.mode = mode
        self.queries = load_queries(mode)
        if not self.queries["visits"]:
            raise RuntimeError("ไม่ได้กำหนดคำสั่ง visits")
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
        else:
            kwargs["pool_recycle"] = 1800
            kwargs["pool_size"] = 2
        self.engine = sa.create_engine(url, **kwargs)
        if self.engine.dialect.name == "mysql":
            @sa.event.listens_for(self.engine, "connect")
            def _read_only(dbapi_conn, _):
                # ป้องกันการเขียนข้อมูลลง HOSxP โดยไม่ตั้งใจ (บัญชีควรมีสิทธิ์ SELECT อย่างเดียวด้วย)
                cur = dbapi_conn.cursor()
                cur.execute("SET SESSION TRANSACTION READ ONLY")
                cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                cur.close()

    def departments(self) -> dict[str, str]:
        with self.engine.connect() as conn:
            rows = conn.execute(sa.text("SELECT depcode, department FROM kskdepartment")).fetchall()
            conn.rollback()
        return {str(r[0]): str(r[1] or "").strip() for r in rows}

    def fetch(self, today: date) -> tuple[list[dict], list[dict] | None]:
        with self.engine.connect() as conn:
            visits = [dict(r._mapping) for r in conn.execute(sa.text(self.queries["visits"]), {"today": today.isoformat()})]
            orders = None
            if self.queries["orders"]:
                orders = [dict(r._mapping) for r in conn.execute(sa.text(self.queries["orders"]), {"today": today.isoformat()})]
            conn.rollback()
        return visits, orders


# ---------------------------------------------------------------- แปลงชนิดข้อมูลจาก HOSxP

def to_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def to_datetime(day: date, value) -> datetime | None:
    """รวมวันที่กับเวลา (HOSxP เก็บเวลาเป็น TIME ซึ่ง PyMySQL คืนเป็น timedelta)"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, timedelta):
        return datetime.combine(day, time()) + value
    if isinstance(value, time):
        return datetime.combine(day, value)
    text = str(value).strip()
    try:
        if len(text) > 10:
            return datetime.fromisoformat(text[:19])
        parts = [int(p) for p in text.split(":")]
        while len(parts) < 3:
            parts.append(0)
        return datetime.combine(day, time(parts[0] % 24, parts[1], parts[2]))
    except ValueError:
        return None


def truthy(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().upper() in ("Y", "1", "T", "TRUE", "YES")


def to_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def to_str(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None

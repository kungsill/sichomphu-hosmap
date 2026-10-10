"""ความรู้สึกของผู้ป่วยระหว่างรอ (กดอารมณ์ / พิมพ์ข้อความจากหน้าใบนำทาง)

- อารมณ์ (อีโมจิ) แสดงบนแผนที่ของเจ้าหน้าที่เท่านั้น — ไม่แสดงบนจอทีวีหรือหน้าผู้ป่วยคนอื่น
- ข้อความที่พิมพ์ เห็นได้เฉพาะหลังบ้าน (รายละเอียดผู้ป่วย และหน้ารายงานผู้บริหาร)
"""
import re
from collections import Counter
from datetime import date, datetime, time as dtime, timedelta

import sqlalchemy as sa

from . import db
from .clock import clock

MOODS = {  # key: (อีโมจิ, ไทย, อังกฤษ) เรียงจากพอใจมาก → ไม่พอใจ
    "great": ("😄", "พอใจมาก", "Very happy"),
    "good": ("🙂", "พอใจ", "Happy"),
    "meh": ("😐", "เฉย ๆ", "Okay"),
    "worried": ("😟", "กังวล", "Worried"),
    "angry": ("😠", "ไม่พอใจ", "Unhappy"),
}
MAX_COMMENT = 300
MIN_INTERVAL_S = 8        # กันกดรัว
MAX_PER_DAY = 30          # ต่อ 1 Visit

_ctrl = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class FeedbackError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def clean_comment(text) -> str | None:
    text = _ctrl.sub("", str(text or "")).strip()
    return text[:MAX_COMMENT] or None


def add(vn: str, vstdate: date, mood: str | None, comment, depcode: str | None, state: str | None) -> dict:
    mood = mood or None
    if mood is not None and mood not in MOODS:
        raise FeedbackError(400, "อารมณ์ไม่ถูกต้อง")
    comment = clean_comment(comment)
    if not mood and not comment:
        raise FeedbackError(400, "กรุณาเลือกความรู้สึกหรือพิมพ์ข้อความ")
    now = clock.now()
    t = db.patient_feedback
    with db.engine.begin() as conn:
        last = conn.execute(sa.select(sa.func.max(t.c.created_at), sa.func.count()).where(
            (t.c.vn == vn) & (t.c.vstdate == vstdate))).first()
        if last[0] and (now - last[0]).total_seconds() < MIN_INTERVAL_S:
            raise FeedbackError(429, "ส่งถี่เกินไป กรุณารอสักครู่")
        if (last[1] or 0) >= MAX_PER_DAY:
            raise FeedbackError(429, "ส่งความรู้สึกครบจำนวนของวันนี้แล้ว ขอบคุณครับ")
        conn.execute(t.insert().values(vn=vn, vstdate=vstdate, mood=mood, comment=comment, depcode=depcode,
                                       state=state, created_at=now))
    return {"ok": True, "mood": mood, "time": now.strftime("%H:%M")}


def latest_moods(day: date) -> dict[str, dict]:
    """อารมณ์ล่าสุดของแต่ละ Visit วันนี้ (สำหรับวาดบนแผนที่เจ้าหน้าที่)"""
    t = db.patient_feedback
    out: dict[str, dict] = {}
    with db.engine.connect() as conn:
        for r in conn.execute(sa.select(t.c.vn, t.c.mood, t.c.comment, t.c.created_at)
                              .where(t.c.vstdate == day).order_by(t.c.id)).mappings():
            cur = out.setdefault(r["vn"], {"mood": None, "time": None, "notes": 0})
            if r["mood"]:
                cur["mood"], cur["time"] = r["mood"], r["created_at"].strftime("%H:%M")
            if r["comment"]:
                cur["notes"] += 1
    return out


def for_visit(vn: str) -> list[dict]:
    t = db.patient_feedback
    with db.engine.connect() as conn:
        rs = conn.execute(sa.select(t).where(t.c.vn == vn).order_by(t.c.id)).mappings().all()
    return [{"time": r["created_at"].strftime("%H:%M"), "mood": r["mood"], "comment": r["comment"],
             "depcode": r["depcode"]} for r in rs]


def summary(d1: date, d2: date, dep_name=lambda d: d, queue_of=None, limit: int = 200) -> dict:
    """สรุปสำหรับหน้ารายงาน: จำนวนแต่ละอารมณ์ + ข้อความล่าสุด (ไม่มีชื่อ/HN)"""
    t = db.patient_feedback
    start, end = datetime.combine(d1, dtime()), datetime.combine(d2 + timedelta(days=1), dtime())
    with db.engine.connect() as conn:
        rs = conn.execute(sa.select(t).where((t.c.created_at >= start) & (t.c.created_at < end))
                          .order_by(t.c.id.desc())).mappings().all()
    # นับอารมณ์ล่าสุดของแต่ละ Visit ต่อจุดบริการ (คนเดียวกดหลายครั้งไม่ถูกนับซ้ำ)
    seen, counts, by_dep = set(), Counter(), {}
    for r in rs:
        if not r["mood"] or (r["vn"], r["depcode"]) in seen:
            continue
        seen.add((r["vn"], r["depcode"]))
        counts[r["mood"]] += 1
        d = by_dep.setdefault(r["depcode"] or "", Counter())
        d[r["mood"]] += 1
    # ข้อความที่ส่งแยกจากปุ่มอารมณ์ → ใช้อารมณ์ล่าสุดของคนนั้น ณ เวลาที่พิมพ์
    mood_at, last = {}, {}
    for r in reversed(rs):
        if r["mood"]:
            last[r["vn"]] = r["mood"]
        mood_at[r["id"]] = r["mood"] or last.get(r["vn"])
    comments = [{"date": r["created_at"].strftime("%d/%m"), "time": r["created_at"].strftime("%H:%M"),
                 "q": queue_of(r["vn"]) if queue_of else None, "where": dep_name(r["depcode"]) if r["depcode"] else "",
                 "mood": mood_at[r["id"]], "comment": r["comment"]} for r in rs if r["comment"]][:limit]
    return {
        "moods": [{"key": k, "emoji": e, "label": th, "n": counts[k]} for k, (e, th, _en) in MOODS.items()],
        "total": sum(counts.values()),
        "by_service": sorted(({"name": dep_name(d) if d else "ไม่ระบุ", "n": sum(c.values()),
                               "unhappy": c["worried"] + c["angry"]} for d, c in by_dep.items()),
                             key=lambda x: (-x["unhappy"], -x["n"]))[:15],
        "comments": comments,
    }

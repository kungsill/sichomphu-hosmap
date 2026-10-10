"""รายงานสำหรับผู้บริหาร: เวลารอ เวลาให้บริการ ช่วงเวลาที่คนแน่น จำนวนผู้ป่วยแต่ละโซน

แหล่งข้อมูล
- ใช้งานจริง: opd_dep_queue ของ HOSxP (มีเวลาเข้าคิว / รับ / เสร็จ ของทุกหน่วยย้อนหลัง) — คำสั่ง [mysql] report_queue
- โหมดสาธิต / ไม่ได้ตั้ง report_queue: เหตุการณ์ที่ระบบนำทางบันทึกเอง (patient_events)
ผลลัพธ์ cache 5 นาที เพื่อไม่ให้เป็นภาระ HOSxP
"""
import statistics
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime, timedelta

import sqlalchemy as sa

from . import db, mapdata
from .clock import clock
from .hosxp.source import to_datetime, to_str

TERMINAL = {"176", "999"}
_cache: dict = {}
_lock = threading.Lock()


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def _p90(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))], 1)


def _minutes(a, b):
    if not a or not b:
        return None
    m = (b - a).total_seconds() / 60
    return m if 0 <= m <= 600 else None


def _rows_from_hosxp(worker, d1: date, d2: date):
    """แถวคิวจาก HOSxP: (vn, depcode, queued, accepted, finished, main_dep, vstdate, vsttime)"""
    sql = worker.source.queries.get("report_queue") if worker else None
    if not sql:
        return None
    with worker.source.engine.connect() as conn:
        res = conn.execute(sa.text(sql), {"d1": d1.isoformat(), "d2": d2.isoformat()})
        rows = [dict(r._mapping) for r in res]
        conn.rollback()
    out = []
    for r in rows:
        day = r.get("vstdate")
        day = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
        out.append({"vn": to_str(r["vn"]), "dep": to_str(r["depcode"]), "main_dep": to_str(r.get("main_dep")),
                    "day": day, "arrive": to_datetime(day, r.get("vsttime")),
                    "queued": to_datetime(day, r.get("queue_datetime")), "accepted": to_datetime(day, r.get("accept_datetime")),
                    "finished": to_datetime(day, r.get("finish_datetime"))})
    return out


def _rows_from_events(d1: date, d2: date):
    """สร้างแถวคิวจากเหตุการณ์ที่ระบบนำทางบันทึก (sent → in_service → service_done/left)"""
    start = datetime.combine(d1, dtime())
    end = datetime.combine(d2 + timedelta(days=1), dtime())
    with db.engine.connect() as conn:
        ev = db.rows(conn.execute(sa.select(db.patient_events).where(
            (db.patient_events.c.event_time >= start) & (db.patient_events.c.event_time < end))
            .order_by(db.patient_events.c.vn, db.patient_events.c.event_time, db.patient_events.c.id)))
        visits = {v["vn"]: v for v in db.rows(conn.execute(sa.select(
            db.patient_visits.c.vn, db.patient_visits.c.main_dep, db.patient_visits.c.vstdate, db.patient_visits.c.vsttime)
            .where((db.patient_visits.c.vstdate >= d1) & (db.patient_visits.c.vstdate <= d2))))}
    out, open_rows = [], {}
    for e in ev:
        vn, dep, t = e["vn"], e.get("depcode"), e["event_time"]
        v = visits.get(vn)
        if not v or not dep:
            continue
        key = (vn, dep)
        if e["event_type"] == "sent":
            row = {"vn": vn, "dep": dep, "main_dep": v["main_dep"], "day": v["vstdate"],
                   "arrive": to_datetime(v["vstdate"], v["vsttime"]), "queued": t, "accepted": None, "finished": None}
            open_rows[key] = row
            out.append(row)
        elif e["event_type"] == "in_service" and key in open_rows and not open_rows[key]["accepted"]:
            open_rows[key]["accepted"] = t
        elif e["event_type"] in ("service_done", "left") and key in open_rows and not open_rows[key]["finished"]:
            open_rows[key]["finished"] = t
    return out


def build(worker, days: int) -> dict:
    days = max(1, min(int(days), 90))
    key = (days, clock.today())
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < 300:
            return hit[1]
    d2 = clock.today()
    d1 = d2 - timedelta(days=days - 1)
    source = "hosxp"
    try:
        rows = _rows_from_hosxp(worker, d1, d2)
    except Exception as exc:  # อ่าน HOSxP ไม่ได้ → ใช้ข้อมูลที่ระบบเก็บเอง
        rows = None
        source_error = str(exc)[:200]
    else:
        source_error = None
    if rows is None:
        rows = _rows_from_events(d1, d2)
        source = "navigation"
    hmap = mapdata.published()
    names = dict(worker.dep_names) if worker else {}

    def dep_name(dep, main_dep=None):
        info = hmap.dep_info(dep, main_dep) if hmap else {}
        return info.get("dep_name") or names.get(dep) or dep

    def zone_of(main_dep):
        if not hmap or not main_dep:
            return "ไม่ระบุโซน"
        m = hmap.resolve_dep(main_dep, None, main_dep)
        room = (m or {}).get("room_id") or (m or {}).get("wait_room_id")
        r = hmap.rooms.get(room)
        return hmap.zone_name(r["floor_id"]) if r else "ไม่ระบุโซน"

    visits: dict[str, dict] = {}
    waits: dict[tuple, list] = defaultdict(list)
    serves: dict[tuple, list] = defaultdict(list)
    counts: Counter = Counter()
    for r in rows:
        if not r["vn"] or not r["dep"]:
            continue
        v = visits.setdefault(r["vn"], {"day": r["day"], "arrive": r["arrive"], "main_dep": r["main_dep"], "last": None})
        for t in (r["finished"], r["accepted"], r["queued"]):
            if t and (v["last"] is None or t > v["last"]):
                v["last"] = t
        if r["dep"] in TERMINAL:
            continue
        k = (r["dep"], dep_name(r["dep"], r["main_dep"]))
        counts[k] += 1
        w = _minutes(r["queued"], r["accepted"])
        if w is not None:
            waits[k].append(w)
        s = _minutes(r["accepted"], r["finished"])
        if s is not None:
            serves[k].append(s)

    all_waits = [w for ws in waits.values() for w in ws]
    all_serves = [s for ss in serves.values() for s in ss]
    stays = [m for m in (_minutes(v["arrive"], v["last"]) for v in visits.values()) if m]

    # ผู้ป่วยมาถึงรายชั่วโมง (เฉลี่ยต่อวัน) + ตารางความร้อน วัน × ชั่วโมง
    per_hour = Counter()
    heat = Counter()
    for v in visits.values():
        if v["arrive"]:
            per_hour[v["arrive"].hour] += 1
            heat[(v["day"].isoformat(), v["arrive"].hour)] += 1
    day_list = [(d1 + timedelta(days=i)).isoformat() for i in range(days)]
    active_days = max(1, len({v["day"] for v in visits.values()}))

    services = []
    for k, n in counts.most_common():
        services.append({"depcode": k[0], "name": k[1], "n": n, "median_wait": _median(waits[k]), "p90_wait": _p90(waits[k]),
                         "median_service": _median(serves[k])})
    zones = Counter(zone_of(v["main_dep"]) for v in visits.values())
    result = {
        "days": days, "from": d1.isoformat(), "to": d2.isoformat(), "source": source, "source_error": source_error,
        "generated": clock.now().strftime("%H:%M"),
        "kpi": {"visits": len(visits), "per_day": round(len(visits) / active_days),
                "median_wait": _median(all_waits), "p90_wait": _p90(all_waits),
                "median_service": _median(all_serves), "median_stay": _median(stays)},
        "hourly": [{"hour": h, "avg": round(per_hour[h] / active_days, 1)} for h in range(6, 21)],
        "heat": {"days": day_list, "cells": [{"day": d, "hour": h, "n": heat[(d, h)]} for d in day_list for h in range(6, 21)]},
        "services": services,
        "zones": [{"name": z, "n": n} for z, n in zones.most_common()],
    }
    with _lock:
        _cache[key] = (time.monotonic(), result)
    return result

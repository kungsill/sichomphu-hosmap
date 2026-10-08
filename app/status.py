"""สร้างภาพรวมสถานะ (snapshot) สำหรับหน้าจอแผนที่ และมุมมองเฉพาะผู้ป่วยแต่ละคน"""
import math
from datetime import timedelta

import sqlalchemy as sa

from . import config, db, mapdata
from .clock import clock
from .db import jload, rows
from .hosxp.worker import FINAL, location_room

STAGE_LABEL = {
    "register": "ลงทะเบียน", "screening": "คัดกรอง", "doctor": "พบแพทย์", "lab": "LAB", "xray": "X-ray",
    "other": "รับบริการ", "finance": "การเงิน", "pharmacy": "รับยา", "home": "กลับบ้าน",
}
STATE_LABEL = {"waiting": "รอรับบริการ", "in_service": "กำลังรับบริการ", "service_done": "รอส่งต่อ",
               "finished": "เสร็จสิ้น", "cancelled": "ยกเลิก"}


def queue_code(hmap, visit) -> str:
    prefix = (hmap.dep_info(visit.get("main_dep")).get("queue_prefix") if hmap else None) or "Q"
    q = visit.get("oqueue")
    return f"{prefix}{q:03d}" if isinstance(q, int) else prefix + str(visit.get("vn"))[-3:]


def stage_steps(hmap, st, stages_done, pending) -> list[dict]:
    md = st.get("main_dep")
    mapped = lambda dep: bool(hmap.dep_info(dep, md))  # noqa: E731
    stages_done = set(stages_done) | {hmap.dep_info(p["depcode"], md).get("stage") or "other"
                                      for p in pending if p.get("status") == "done" and mapped(p["depcode"])}
    # "other" ที่มาจากหน่วยซึ่งไม่ได้อยู่บนแผนที่ (ข้อมูลเก่า) ไม่นับเป็นขั้นตอน
    if "other" in stages_done and not any((m.get("stage") == "other") for ms in hmap.mapping_by_dep.values() for m in ms):
        stages_done.discard("other")
    involved = set(stages_done)
    cur_stage = None
    if st["state"] == "finished":
        cur_stage = "home"
    elif st.get("dest_dep") and mapped(st["dest_dep"]):
        cur_stage = hmap.dep_info(st["dest_dep"], md).get("stage") or "other"
        involved.add(cur_stage)
    for p in pending:
        if mapped(p["depcode"]):
            involved.add(hmap.dep_info(p["depcode"], md).get("stage") or "other")
    seq = ["register", "screening", "doctor"]
    seq += [s for s in ("other", "lab", "xray") if s in involved]
    # การเงิน: แสดงเฉพาะผู้ที่ถูกส่งไปห้องเก็บเงินจริง (บางโซน เช่น คลินิกพิเศษ ชำระเงินที่จุดรับยา)
    seq += (["finance"] if "finance" in involved else []) + ["pharmacy", "home"]
    out = []
    cur_idx = seq.index(cur_stage) if cur_stage in seq else -1
    for i, s in enumerate(seq):
        if s == cur_stage:
            status = "done" if s == "home" else "current"
        elif s in stages_done:
            status = "done"
        elif i < cur_idx and s in ("register", "screening", "doctor"):
            status = "done"  # ขั้นตอนหลักก่อนขั้นปัจจุบันถือว่าผ่านแล้ว
        else:
            status = "todo"
        out.append({"key": s, "label": STAGE_LABEL.get(s, s), "status": status})
    return out


class SnapshotBuilder:
    def __init__(self, worker=None, simulator=None):
        self.worker = worker
        self.simulator = simulator
        self.latest: dict = {}
        self.by_vn: dict = {}

    def build(self) -> dict:
        now = clock.now()
        today = now.date()
        hmap = mapdata.published()
        with db.engine.connect() as conn:
            data = rows(conn.execute(
                sa.select(db.patient_status, db.patient_visits.c.hn, db.patient_visits.c.oqueue,
                          db.patient_visits.c.main_dep, db.patient_visits.c.age, db.patient_visits.c.sex,
                          db.patient_visits.c.vsttime, db.patient_visits.c.vstdate, db.patient_visits.c.vitals)
                .join(db.patient_visits, db.patient_visits.c.vn == db.patient_status.c.vn)
                .where(db.patient_visits.c.vstdate == today)
                .where(db.patient_status.c.state != "cancelled")))
        show_after = now - timedelta(minutes=config.SHOW_FINISHED_MINUTES)
        data = [d for d in data if d["state"] != "finished" or (d.get("finished_at") and d["finished_at"] >= show_after)]

        # ลำดับคิวต่อจุดบริการ (รหัสเดียวกันแต่คนละโซน แยกคิวกัน)
        zkey = lambda dep, md: (hmap.zone_key(dep, md) if hmap else None) or dep  # noqa: E731
        queues: dict[str, list] = {}
        for d in data:
            if d["state"] == "waiting" and d.get("cur_dep") == d.get("dest_dep"):
                queues.setdefault(zkey(d["cur_dep"], d.get("main_dep")), []).append(d)
        position = {}
        for dep, items in queues.items():
            items.sort(key=lambda d: (d.get("cur_dep_time") or now, d["vn"]))
            for i, d in enumerate(items, start=1):
                position[d["vn"]] = i

        ema = self.worker.service_ema if self.worker else {}

        def est_wait(dep, pos, main_dep=None):
            info = hmap.dep_info(dep, main_dep) if hmap else {}
            avg = ema.get(dep) or info.get("avg_service_min") or 5
            servers = max(1, info.get("servers") or 1)
            return math.ceil(pos * avg / servers)

        patients = []
        room_count: dict[str, int] = {}
        by_vn = {}
        for d in data:
            stages_done = jload(d.get("stages_done"), []) or []
            pending = jload(d.get("pending"), []) or []
            room = location_room(hmap, d) if hmap else None
            if room:
                room_count[room] = room_count.get(room, 0) + 1
            dest = d.get("dest_dep")
            md = d.get("main_dep")
            info = hmap.dep_info(dest, md) if (hmap and dest) else {}
            dep_name = info.get("dep_name") or dest or ""
            since = round(((now - d["cur_dep_time"]).total_seconds() / 60)) if d.get("cur_dep_time") else 0
            reg = None
            try:
                hh, mm, *_ = (int(x) for x in str(d.get("vsttime") or "").split(":"))
                reg = d["vstdate"] and now.replace(hour=hh, minute=mm, second=0)
            except ValueError:
                pass
            stay = max(0, round((now - reg).total_seconds() / 60)) if reg else 0
            pos = position.get(d["vn"])
            exact = hmap.resolve_dep(dest, d.get("room_hint"), md) if (hmap and dest) else None
            service_room = exact.get("room_id") if exact and exact.get("exact") else None
            walking = d["state"] == "waiting" and since < config.WALKING_MINUTES
            if d["state"] == "finished":
                label = "กำลังกลับบ้าน"
            elif dest and dest != d.get("cur_dep"):
                label = f"เดินไป{dep_name}"
            elif d["state"] == "in_service":
                if info.get("stage") == "doctor":
                    label = f"พบแพทย์ {hmap.rooms[service_room]['short_name']}" if service_room and service_room in hmap.rooms else "พบแพทย์"
                else:
                    label = f"กำลังรับบริการ{dep_name}"
            elif d["state"] == "service_done":
                label = f"รอส่งต่อจาก{dep_name}"
            elif walking:
                label = f"เดินไป{dep_name}"
            else:
                label = f"รอ{dep_name} ลำดับที่ {pos}" if pos else f"รอ{dep_name}"
            route = jload(d.get("route"))
            p = {
                "vn": d["vn"], "q": queue_code(hmap, d) if hmap else d["vn"], "hn": d.get("hn"),
                "age": d.get("age"), "sex": d.get("sex"), "state": d["state"], "label": label,
                "busy": bool(d.get("busy")), "dep": d.get("cur_dep"), "dest": dest, "dest_name": dep_name,
                "room": room, "service_room": service_room, "walking": walking,
                "route_id": d.get("route_id") or 0, "route": route.get("points") if route else None,
                "route_from": route.get("from") if route else None,
                "since": since, "stay": stay, "pos": pos, "est": est_wait(dest, pos, md) if pos else None,
                "stages": stage_steps(hmap, d, stages_done, pending) if hmap else [],
                "pending": [{"depcode": x["depcode"], "name": (hmap.dep_info(x["depcode"], md).get("dep_name") if hmap else x["depcode"]),
                             "status": x["status"]} for x in pending],
                "vitals": jload(d.get("vitals")) if config.SHOW_VITALS else None,
            }
            patients.append(p)
            by_vn[d["vn"]] = p

        # จุดบริการ
        services = []
        if hmap:
            for dep, items in hmap.mapping_by_dep.items():
                groups: dict[str, dict] = {}
                for m in items:
                    groups.setdefault(m.get("for_main_dep") or "", m)
                for zone, m in groups.items():
                    key = f"{dep}@{zone}" if zone else dep
                    zmd = zone.split(",")[0].strip() if zone else None
                    wait_room = m.get("wait_room_id") or m.get("room_id")
                    cap = (hmap.rooms.get(wait_room) or {}).get("capacity") or 20
                    waiting = len(queues.get(key, []))
                    serving = sum(1 for d in data if d["state"] == "in_service" and d.get("cur_dep") == dep
                                  and zkey(dep, d.get("main_dep")) == key)
                    services.append({"depcode": dep, "zone": zone, "name": m.get("dep_name") or dep, "stage": m.get("stage"),
                                     "waiting": waiting, "serving": serving, "capacity": cap,
                                     "est": est_wait(dep, waiting, zmd) if waiting else 0,
                                     "avg": round(ema.get(dep) or m.get("avg_service_min") or 5, 1),
                                     "room": m.get("room_id"), "wait_room": wait_room,
                                     "floor": (hmap.rooms.get(wait_room) or {}).get("floor_id")})
            services.sort(key=lambda s: (STAGE_ORDER_INDEX.get(s["stage"], 9), s["depcode"]))

        active = [p for p in patients if p["state"] not in FINAL]
        # รอ: นับเฉพาะผู้ป่วยที่อยู่บนแผนที่ และใช้ค่ากลาง (median) เพื่อไม่ให้ Visit ที่ค้างในระบบนาน ๆ ดึงค่าเพี้ยน
        waits = sorted(p["since"] for p in active if p["state"] == "waiting" and p["room"])
        cap_total = sum((r.get("capacity") or 0) for r in (hmap.rooms.values() if hmap else []) if r.get("kind") != "corridor")
        located = sum(c for rid, c in room_count.items() if hmap and hmap.rooms.get(rid, {}).get("kind") != "corridor")
        density = round(100 * located / cap_total) if cap_total else 0
        level = "น้อย" if density < 35 else ("ปานกลาง" if density < 70 else "หนาแน่น")
        snap = {
            "time": now.strftime("%H:%M"), "datetime": now.isoformat(), "demo": config.IS_DEMO,
            "rush": bool(self.simulator and self.simulator.rush),
            "map_version": hmap.version if hmap else None,
            "health": self.worker.health if self.worker else {"ok": False, "error": "worker ไม่ทำงาน"},
            "stats": {"in_hospital": len(active), "avg_wait": waits[len(waits) // 2] if waits else 0,
                      "density": density, "density_level": level},
            "rooms": room_count, "services": services, "patients": patients,
        }
        self.latest = snap
        self.by_vn = by_vn
        return snap


STAGE_ORDER_INDEX = {s: i for i, s in enumerate(["register", "screening", "doctor", "other", "lab", "xray", "finance", "pharmacy"])}


def patient_view(builder: SnapshotBuilder, vn: str, accessible: bool = False) -> dict | None:
    """ข้อมูลสำหรับหน้าใบนำทางของผู้ป่วย (เฉพาะของตนเอง + จำนวนคนในแต่ละพื้นที่)"""
    hmap = mapdata.published()
    p = builder.by_vn.get(vn)
    with db.engine.connect() as conn:
        visit = conn.execute(sa.select(db.patient_visits).where(db.patient_visits.c.vn == vn)).mappings().first()
        st = conn.execute(sa.select(db.patient_status).where(db.patient_status.c.vn == vn)).mappings().first()
        events = rows(conn.execute(sa.select(db.patient_events).where(db.patient_events.c.vn == vn)
                                   .order_by(db.patient_events.c.event_time, db.patient_events.c.id)))
    if not visit or not st:
        return None
    if p is None:  # จบไปนานแล้ว หรือยกเลิก
        p = {"vn": vn, "q": queue_code(hmap, dict(visit)) if hmap else vn, "state": st["state"],
             "label": "เสร็จสิ้นการรับบริการ" if st["state"] == "finished" else STATE_LABEL.get(st["state"], st["state"]),
             "room": None, "dest": None, "dest_name": "", "stages": [], "pending": [], "route": None,
             "route_id": st.get("route_id") or 0, "since": 0, "stay": 0, "pos": None, "est": None,
             "age": visit.get("age"), "hn": visit.get("hn"), "vitals": None}
    hn = str(p.get("hn") or "")
    view = {k: p.get(k) for k in ("vn", "q", "state", "label", "dest", "dest_name", "room", "service_room", "stages",
                                  "pending", "since", "stay", "pos", "est", "age", "route_id", "busy", "walking", "vitals")}
    view["hn_masked"] = ("*" * max(0, len(hn) - 4)) + hn[-4:] if hn else ""
    view["time"] = builder.latest.get("time")
    view["health_ok"] = bool(builder.latest.get("health", {}).get("ok"))
    view["rooms"] = builder.latest.get("rooms", {})
    route = None
    if hmap and p.get("state") not in FINAL and p.get("room"):
        rec = jload(st.get("route"))
        origin = rec.get("from") if rec else None
        if origin == p["room"]:
            origin = None
        route = hmap.route(origin, p["room"], accessible=accessible)
        if route and route.get("ok") and p.get("service_room") and p["service_room"] != p["room"]:
            route["steps"].append(f"นั่งรอเรียกที่{hmap.room_name(p['room'])} จากนั้นเข้า{hmap.room_name(p['service_room'])}")
    elif hmap and p.get("state") == "finished" and p.get("route"):
        rec = jload(st.get("route"))
        origin = rec.get("from") if rec else None
        route = hmap.route(origin, None, accessible=accessible, to_node=hmap.exit_node(origin))
    view["route"] = route
    view["destination"] = None
    if hmap and p.get("room") in hmap.rooms:
        r = hmap.rooms[p["room"]]
        target = hmap.rooms.get(p.get("service_room") or p["room"], r)
        view["destination"] = {"room_id": target["id"], "name": target["name"], "wait_room": r["name"],
                               "floor_id": target["floor_id"], "floor": hmap.floor_label(target["floor_id"])}
    names = {}
    if hmap:
        for dep, items in hmap.mapping_by_dep.items():
            names[dep] = items[0].get("dep_name") or dep
    ev_label = {"registered": "ลงทะเบียน", "sent": "ส่งไป", "in_service": "เริ่มรับบริการ", "service_done": "รับบริการเสร็จ",
                "left": "ออกจาก", "order_added": "ส่งตรวจเพิ่ม", "order_done": "ผลตรวจเสร็จ", "finished": "เสร็จสิ้น",
                "cancelled": "ยกเลิก", "resync": "ปรับปรุงสถานะ"}
    view["events"] = [{"time": e["event_time"].strftime("%H:%M"), "type": e["event_type"],
                       "text": f"{ev_label.get(e['event_type'], e['event_type'])}"
                               + (f" {names.get(e['depcode'], e['depcode'])}" if e.get("depcode") and e["event_type"] in ("sent", "in_service", "service_done", "left") else "")
                               + (f" — {e['detail']}" if e["event_type"] in ("order_added", "order_done", "cancelled", "resync") and e.get("detail") else "")}
                      for e in events if e["event_type"] != "left"]
    return view

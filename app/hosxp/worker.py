"""Integration Worker: อ่านสถานะ Visit จาก HOSxP เป็นรอบ (Polling) แล้วเทียบกับสถานะเดิมเพื่อสร้างเหตุการณ์

หลักการ:
- ใช้การเทียบ "ภาพรวม ณ ปัจจุบัน" ของแต่ละ VN กับสถานะที่เก็บไว้ จึงไม่เกิดเหตุการณ์ซ้ำ
  แม้อ่านข้อมูลซ้ำหรือระบบรีสตาร์ต และกู้คืนสถานะที่ถูกต้องได้เองเมื่อเชื่อมต่อใหม่
- ไม่ถือว่าการเปลี่ยนแผนกคือการ "ส่งกลับ" เสมอไป: บันทึกเป็น left + sent ตามข้อมูลที่เห็นจริง
- VN ที่หายไปจากผลลัพธ์ ต้องหายติดต่อกันหลายรอบก่อนจึงปิดสถานะ (กันอ่านข้อมูลไม่ครบชั่วคราว)
"""
import logging
import secrets
from datetime import datetime, timedelta

import sqlalchemy as sa

from .. import config, db, mapdata
from ..clock import clock
from ..db import jdump, jload, rows
from .source import HosxpSource, to_date, to_datetime, to_float, to_str, truthy

log = logging.getLogger("hosxp.worker")

FINAL = ("finished", "cancelled")
STAGE_ORDER = ["register", "screening", "doctor", "other", "lab", "xray", "finance", "pharmacy"]


def stage_of(hmap, dep, main_dep=None) -> str | None:
    """ขั้นตอนของหน่วยบริการ (None = หน่วยที่ไม่ได้อยู่บนแผนที่ ไม่นับเป็นขั้นตอน)"""
    info = hmap.dep_info(dep, main_dep) if hmap and dep else {}
    return (info.get("stage") or "other") if info else None


def position_room(hmap, dep, hint, at_service: bool, main_dep=None):
    """ห้องที่ผู้ป่วยควรอยู่: ในห้องบริการ (เมื่อรับบริการ) หรือพื้นที่นั่งรอของหน่วยนั้น"""
    if not hmap or not dep:
        return None
    m = hmap.resolve_dep(dep, hint, main_dep)
    if not m:
        return None
    if at_service and m.get("exact"):
        return m.get("room_id") or m.get("wait_room_id")
    return m.get("wait_room_id") or m.get("room_id")


def location_room(hmap, st: dict):
    state = st.get("state")
    if state in FINAL:
        return None
    dest = st.get("dest_dep") or st.get("cur_dep")
    same = dest == st.get("cur_dep")
    hint = st.get("room_hint") if same else None
    at_service = same and state in ("in_service", "service_done")
    return position_room(hmap, dest, hint, at_service, st.get("main_dep"))


def choose_dest(hmap, st: dict, from_room) -> str | None:
    """กฎเลือกปลายทาง: ปกติใช้หน่วยบริการปัจจุบันใน HOSxP
    ถ้ารับบริการที่หน่วยปัจจุบันเสร็จแล้วแต่ยังมีงานค้างหลายห้อง (เช่น LAB + X-ray) จะเลือกตาม priority แล้วระยะทาง
    ไม่เลือก "ห้องล่าสุด" เป็นปลายทางโดยอัตโนมัติ"""
    cur = st.get("cur_dep")
    pending = [p for p in (st.get("pending_list") or []) if p.get("status") != "done"]
    if st.get("state") != "service_done" or not pending or cur in {p["depcode"] for p in pending}:
        return cur

    def key(p):
        info = hmap.dep_info(p["depcode"], st.get("main_dep")) if hmap else {}
        target = position_room(hmap, p["depcode"], None, False, st.get("main_dep"))
        r = hmap.route(from_room, target) if (hmap and target and from_room) else None
        return (0 if p.get("status") == "received" else 1, info.get("priority") or 50,
                r["distance"] if r and r.get("ok") else 9999)

    return min(pending, key=key)["depcode"]


def inferred_stages(stage: str) -> list[str]:
    """ผู้ป่วยที่เห็นครั้งแรกกลาง Visit (เช่น หลังระบบล่ม) ให้อนุมานขั้นตอนหลักก่อนหน้าว่าผ่านแล้ว"""
    if stage not in STAGE_ORDER:
        return []
    idx = STAGE_ORDER.index(stage)
    return [s for s in ("register", "screening", "doctor", "finance") if STAGE_ORDER.index(s) < idx]


def norm_status(value) -> str:
    text = (str(value or "")).strip().lower()
    if text in ("done", "y", "1", "complete", "completed", "reported", "finish", "finished"):
        return "done"
    if text in ("received", "receive", "r", "in_service", "processing"):
        return "received"
    return "ordered"


class Worker:
    def __init__(self):
        url = config.HOSXP_DB_URL
        if config.IS_DEMO:
            from .mock import MOCK_DB_URL
            url = MOCK_DB_URL
        if not url:
            raise RuntimeError("ยังไม่ได้ตั้งค่า HOSXP_DB_URL")
        self.source = HosxpSource(url, "mock" if config.IS_DEMO else "mysql")
        self.health = {"ok": False, "mode": config.HOSXP_MODE, "last_sync": None, "error": None,
                       "visits": 0, "fail_count": 0}
        self.service_ema: dict[str, float] = {}
        self.dep_names: dict[str, str] = {}
        self._dep_names_at = 0.0

    # ------------------------------------------------------------ เรียนรู้เวลาให้บริการเฉลี่ยของแต่ละหน่วย
    def learn(self, dep, since, now):
        if not dep or not since:
            return
        minutes = (now - since).total_seconds() / 60
        if 0.3 <= minutes <= 180:
            old = self.service_ema.get(dep)
            self.service_ema[dep] = minutes if old is None else old * 0.8 + minutes * 0.2

    # ------------------------------------------------------------ รอบการซิงก์
    def refresh_dep_names(self):
        """ชื่อหน่วยบริการจาก kskdepartment (รีเฟรชทุก 10 นาที)"""
        import time as _t
        if self.dep_names and _t.monotonic() - self._dep_names_at < 600:
            return
        try:
            self.dep_names = self.source.departments()
            self._dep_names_at = _t.monotonic()
        except Exception as exc:  # ไม่มีตารางนี้ก็ใช้รหัสแทน
            log.info("อ่านชื่อหน่วยบริการไม่ได้: %s", exc)
            self._dep_names_at = _t.monotonic()

    def sync_once(self) -> bool:
        now = clock.now()
        self.refresh_dep_names()
        today = now.date()
        try:
            visits, orders = self.source.fetch(today)
        except Exception as exc:  # ฐานข้อมูล HOSxP ไม่พร้อม: เก็บสถานะเดิมไว้ แล้วลองใหม่รอบถัดไป
            self.health.update(ok=False, error=str(exc)[:300], fail_count=self.health["fail_count"] + 1)
            log.warning("อ่าน HOSxP ไม่สำเร็จ: %s", exc)
            return False

        hmap = mapdata.published()
        orders_by_vn: dict[str, list] | None = None
        if orders is not None:
            orders_by_vn = {}
            for o in orders:
                vn, dep = to_str(o.get("vn")), to_str(o.get("depcode"))
                if vn and dep:
                    orders_by_vn.setdefault(vn, {})[dep] = norm_status(o.get("status"))

        with db.engine.begin() as conn:
            vis_rows = rows(conn.execute(sa.select(db.patient_visits).where(db.patient_visits.c.vstdate == today)))
            visit_map = {r["vn"]: r for r in vis_rows}
            st_rows = rows(conn.execute(
                sa.select(db.patient_status).where(
                    db.patient_status.c.vn.in_(sa.select(db.patient_visits.c.vn).where(db.patient_visits.c.vstdate == today))
                    | db.patient_status.c.state.notin_(FINAL))))
            existing = {r["vn"]: r for r in st_rows}
            seen = set()
            for v in visits:
                vn = to_str(v.get("vn"))
                if not vn:
                    continue
                seen.add(vn)
                pend = None
                if orders_by_vn is not None:
                    pend = [{"depcode": d, "status": s} for d, s in sorted(orders_by_vn.get(vn, {}).items())]
                try:
                    self._apply(conn, hmap, v, vn, existing.get(vn), visit_map.get(vn), pend, now, today)
                except Exception:
                    log.exception("ประมวลผล VN %s ไม่สำเร็จ", vn)

            for vn, st in existing.items():
                if vn in seen or st["state"] in FINAL:
                    continue
                vis = visit_map.get(vn)
                if vis is None:  # Visit ของวันก่อนที่ค้างอยู่: ปิดเมื่อขึ้นวันใหม่
                    self._close(conn, vn, "finished", "ปิดอัตโนมัติเมื่อขึ้นวันใหม่", now)
                    continue
                missing = (st.get("missing_polls") or 0) + 1
                if missing >= config.MISSING_POLLS_BEFORE_CANCEL:
                    self._close(conn, vn, "cancelled", "ไม่พบ Visit ใน HOSxP", now)
                else:
                    conn.execute(db.patient_status.update().where(db.patient_status.c.vn == vn).values(missing_polls=missing))

        self.health.update(ok=True, error=None, last_sync=now.isoformat(), visits=len(visits), fail_count=0)
        return True

    def _close(self, conn, vn, state, detail, now):
        conn.execute(db.patient_status.update().where(db.patient_status.c.vn == vn).values(
            state=state, busy=False, finished_at=now, updated_at=now))
        self._event(conn, vn, state, None, detail, now)

    @staticmethod
    def _event(conn, vn, kind, dep, detail, when):
        conn.execute(db.patient_events.insert().values(vn=vn, event_type=kind, depcode=dep, detail=detail, event_time=when))

    def _apply(self, conn, hmap, v, vn, st, vis, pending, now, today):
        vstdate = to_date(v.get("vstdate")) or today
        cur_dep = to_str(v.get("cur_dep"))
        busy = truthy(v.get("busy"))
        served = truthy(v.get("served")) and not busy  # บริการที่หน่วยนี้เสร็จแล้ว รอส่งต่อ
        finished = truthy(v.get("finished"))
        hint = to_str(v.get("room_hint"))
        main_dep = to_str(v.get("main_dep"))
        dep_time = to_datetime(vstdate, v.get("cur_dep_time")) or now
        if dep_time > now + timedelta(minutes=5):
            dep_time = now
        vitals = None
        if config.SHOW_VITALS:
            vitals = {k: to_float(v.get(k)) for k in ("bw", "bps", "bpd", "temperature")}
            if not any(vitals.values()):
                vitals = None
        dep_name = lambda d: (hmap.dep_info(d, main_dep).get("dep_name") if hmap else None) or d  # noqa: E731

        # ---------------------------------------------------------- Visit ใหม่
        if st is None:
            if vis is None:
                age = v.get("age")
                conn.execute(db.patient_visits.insert().values(
                    vn=vn, hn=to_str(v.get("hn")) or "", vstdate=vstdate, vsttime=str(v.get("vsttime") or "")[:8],
                    queue_no=to_str(v.get("queue_no")),
                    oqueue=int(v["oqueue"]) if str(v.get("oqueue") or "").isdigit() else None,
                    main_dep=to_str(v.get("main_dep")), age=int(age) if age is not None else None,
                    sex=to_str(v.get("sex")), vitals=jdump(vitals) if vitals else None, created_at=now))
                self._create_token(conn, vn, now)
            reg_time = to_datetime(vstdate, v.get("vsttime")) or now
            self._event(conn, vn, "registered", None, None, min(reg_time, now))
            if cur_dep:
                self._event(conn, vn, "sent", cur_dep, dep_name(cur_dep), dep_time)
            if busy:
                self._event(conn, vn, "in_service", cur_dep, dep_name(cur_dep), now)
            state = "finished" if finished else ("in_service" if busy else ("service_done" if served else "waiting"))
            new = {"vn": vn, "main_dep": main_dep, "cur_dep": cur_dep, "busy": busy, "cur_dep_time": dep_time,
                   "busy_since": now if busy else None, "prev_dep": None, "room_hint": hint, "state": state,
                   "pending_list": pending or [], "finished_at": dep_time if finished else None}
            new["dest_dep"] = cur_dep
            stages = inferred_stages(stage_of(hmap, cur_dep, main_dep))
            if finished:
                stages = inferred_stages("pharmacy") + ["pharmacy"]
            route = None
            if hmap and not finished:
                to_room = location_room(hmap, new)
                fresh = (now - dep_time) < timedelta(minutes=config.WALKING_MINUTES)
                if to_room and fresh:
                    route = hmap.route(None, to_room)
            conn.execute(db.patient_status.insert().values(
                vn=vn, cur_dep=cur_dep, busy=busy, cur_dep_time=dep_time, busy_since=new["busy_since"],
                prev_dep=None, room_hint=hint, state=state, dest_dep=cur_dep, pending=jdump(pending or []),
                stages_done=jdump(stages), route=jdump(self._route_rec(route)) if route and route.get("ok") else None,
                route_id=1 if route else 0, finished_at=new["finished_at"], missing_polls=0, updated_at=now))
            return

        # ---------------------------------------------------------- Visit เดิม: เทียบการเปลี่ยนแปลง
        if vis is not None:
            vis_upd = {}
            if vitals and jload(vis.get("vitals")) != vitals:
                vis_upd["vitals"] = jdump(vitals)
            qno = to_str(v.get("queue_no"))
            if qno and qno != vis.get("queue_no"):  # ใบคิวอาจออกหลังเปิด Visit
                vis_upd["queue_no"] = qno
            if vis_upd:
                conn.execute(db.patient_visits.update().where(db.patient_visits.c.vn == vn).values(**vis_upd))

        old_pending = jload(st.get("pending"), []) or []
        st = dict(st)
        st["main_dep"] = main_dep
        st["pending_list"] = old_pending
        prev_loc = location_room(hmap, st)
        stages = list(jload(st.get("stages_done"), []) or [])
        upd: dict = {}
        events: list[tuple] = []

        def mark(stage):
            if stage and stage not in stages:
                stages.append(stage)

        if st["state"] in FINAL and not finished and st["state"] == "cancelled":
            # VN กลับมาปรากฏอีกครั้ง (เช่น ยกเลิกการจบงานใน HOSxP)
            upd["state"] = "in_service" if busy else "waiting"
            events.append(("resync", cur_dep, "พบ Visit อีกครั้ง", now))
        if finished:
            if st["state"] != "finished":
                mark(stage_of(hmap, st.get("cur_dep"), main_dep))
                events.append(("finished", st.get("cur_dep"), "จบการรับบริการ", now))
                upd.update(state="finished", busy=False, finished_at=now, dest_dep=None)
                if hmap and prev_loc:
                    exit_node = hmap.exit_node(prev_loc)
                    route = hmap.route(prev_loc, None, to_node=exit_node) if exit_node else None
                    if route and route.get("ok"):
                        upd["route"] = jdump(self._route_rec(route))
                        upd["route_id"] = (st.get("route_id") or 0) + 1
        else:
            if st["state"] == "finished":
                # HOSxP ยกเลิกการจบ Visit
                upd.update(state="in_service" if busy else "waiting", finished_at=None)
                events.append(("resync", cur_dep, "ยกเลิกการจบ Visit", now))
            if cur_dep != st.get("cur_dep"):
                if st.get("cur_dep"):
                    events.append(("left", st["cur_dep"], dep_name(st["cur_dep"]), now))
                    mark(stage_of(hmap, st["cur_dep"], main_dep))
                    if st.get("busy"):
                        self.learn(st["cur_dep"], st.get("busy_since"), now)
                if cur_dep:
                    events.append(("sent", cur_dep, dep_name(cur_dep), dep_time))
                if busy:
                    events.append(("in_service", cur_dep, dep_name(cur_dep), now))
                upd.update(cur_dep=cur_dep, prev_dep=st.get("cur_dep"), cur_dep_time=dep_time, busy=busy,
                           busy_since=now if busy else None,
                           state="in_service" if busy else ("service_done" if served else "waiting"))
            else:
                if busy and not st.get("busy"):
                    events.append(("in_service", cur_dep, dep_name(cur_dep), now))
                    upd.update(busy=True, busy_since=now, state="in_service")
                elif not busy and st.get("busy"):
                    events.append(("service_done", cur_dep, dep_name(cur_dep), now))
                    self.learn(cur_dep, st.get("busy_since"), now)
                    upd.update(busy=False, state="service_done")
                elif served and st["state"] == "waiting":
                    # รับและเสร็จภายในรอบเดียว หรือเห็นครั้งแรกหลังเสร็จแล้ว
                    events.append(("service_done", cur_dep, dep_name(cur_dep), now))
                    upd.update(state="service_done")
                elif dep_time != st.get("cur_dep_time") and not busy and not served and st["state"] == "service_done":
                    # ถูกส่งกลับเข้าคิวหน่วยเดิมอีกครั้ง (เช่น กลับมาพบแพทย์หลังได้ผล LAB)
                    events.append(("sent", cur_dep, dep_name(cur_dep), dep_time))
                    upd.update(cur_dep_time=dep_time, state="waiting")
            if hint != st.get("room_hint"):
                upd["room_hint"] = hint

        if pending is not None:
            old = {p["depcode"]: p["status"] for p in old_pending}
            for p in pending:
                before = old.get(p["depcode"])
                if before is None:
                    events.append(("order_added", p["depcode"], f"มีรายการส่งตรวจ {dep_name(p['depcode'])}", now))
                elif p["status"] == "done" and before != "done":
                    events.append(("order_done", p["depcode"], f"{dep_name(p['depcode'])} เสร็จแล้ว", now))
                    mark(stage_of(hmap, p["depcode"], main_dep))
            if pending != old_pending:
                upd["pending"] = jdump(pending)

        merged = {**st, **upd}
        merged["pending_list"] = pending if pending is not None else old_pending
        if merged["state"] not in FINAL:
            dest = choose_dest(hmap, merged, prev_loc)
            if dest != st.get("dest_dep"):
                upd["dest_dep"] = dest
            merged["dest_dep"] = dest
            new_loc = location_room(hmap, merged)
            if hmap and new_loc and new_loc != prev_loc:
                route = hmap.route(prev_loc, new_loc)
                if route and route.get("ok"):
                    upd["route"] = jdump(self._route_rec(route))
                    upd["route_id"] = (st.get("route_id") or 0) + 1
        if jdump(stages) != (st.get("stages_done") or "[]"):
            upd["stages_done"] = jdump(stages)
        if st.get("missing_polls"):
            upd["missing_polls"] = 0

        for kind, dep, detail, when in events:
            self._event(conn, vn, kind, dep, detail, when)
        if upd:
            upd["updated_at"] = now
            conn.execute(db.patient_status.update().where(db.patient_status.c.vn == vn).values(**upd))

    @staticmethod
    def _route_rec(route: dict) -> dict:
        return {"from": route.get("from_room"), "to": route.get("to_room"), "points": route["points"],
                "distance": route.get("distance")}

    @staticmethod
    def _create_token(conn, vn, now):
        conn.execute(db.navigation_tokens.insert().values(
            token=secrets.token_urlsafe(16), vn=vn, created_at=now,
            expires_at=now + timedelta(hours=config.TOKEN_VALID_HOURS), revoked=False))


def get_or_create_token(conn, vn: str) -> str:
    now = clock.now()
    tok = conn.execute(sa.select(db.navigation_tokens.c.token).where(
        (db.navigation_tokens.c.vn == vn) & (db.navigation_tokens.c.revoked == sa.false())
        & (db.navigation_tokens.c.expires_at > now)).order_by(db.navigation_tokens.c.created_at.desc()).limit(1)).scalar()
    if tok:
        return tok
    tok = secrets.token_urlsafe(16)
    conn.execute(db.navigation_tokens.insert().values(token=tok, vn=vn, created_at=now,
                                                      expires_at=now + timedelta(hours=config.TOKEN_VALID_HOURS),
                                                      revoked=False))
    return tok

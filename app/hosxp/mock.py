"""ฐานข้อมูล HOSxP จำลอง + ตัวจำลองผู้ป่วย (ใช้เฉพาะโหมดสาธิต HOSXP_MODE=mock)

จำลองผู้ป่วยบนแผนที่จริงของ รพ.สีชมพู ด้วยรหัสหน่วยบริการจริง และเส้นทางรับบริการที่พบบ่อยของแต่ละโซน
(สรุปจากข้อมูล opd_dep_queue 30 วัน) ตัวจำลองทำหน้าที่แทน "เจ้าหน้าที่ที่ทำงานใน HOSxP":
ลงทะเบียน → ส่งตรวจ → รับผู้ป่วย → ส่งต่อ → จบงาน โดยเขียนลงตาราง ovst / opdscreen / mock_orders เท่านั้น
ระบบนำทางอ่านผ่าน Worker ตัวเดียวกับของจริง
"""
import logging
import math
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .. import config
from ..clock import clock

log = logging.getLogger("hosxp.mock")

MOCK_DB_PATH = config.DATA_DIR / "mock_hosxp.db"
MOCK_DB_URL = f"sqlite:///{MOCK_DB_PATH.as_posix()}"

# รหัส: (ชื่อ, จำนวนช่องบริการ, นาทีต่อคนโดยเฉลี่ย)
DEPARTMENTS = {
    "144": ("3.ซักประวัติ OPD", 3, 4), "138": ("4.ห้องตรวจอายุรกรรม", 4, 7), "145": ("หลังตรวจOPD", 3, 3),
    "019": ("1.LAB", 2, 5), "034": ("8.เอกซ์เรย์", 1, 6), "001": ("15.ห้องเก็บเงิน", 2, 3),
    "010": ("ห้องยาผู้ป่วยนอก", 3, 4), "110": ("ห้องฉุกเฉิน", 2, 15), "189": ("หลังตรวจER", 1, 5),
    "024": ("26.คลินิกพิเศษ", 4, 5), "036": ("ห้องตรวจคลินิกพิเศษ", 4, 8), "188": ("หลังตรวจคลีนิกพิเศษ", 5, 3),
    "039": ("ห้องจ่ายยา - NCD", 2, 5), "047": ("29.คลินิกไข้หวัดใหญ่", 2, 4), "005": ("ห้องตรวจไข้หวัดใหญ่", 3, 6),
    "002": ("หลังตรวจไข้หวัดใหญ่", 1, 3), "190": ("จุดซักประวัติทันตกรรม", 1, 4), "028": ("6.ทันตกรรม", 4, 20),
    "046": ("7.กายภาพบำบัด", 4, 12), "035": ("แพทย์แผนไทย", 6, 40), "033": ("28.ส่งเสริมสุขภาพ", 4, 10),
    "031": ("คลินิกไตเทียม", 12, 60), "185": ("คลินิกจิตเวชและยาเสพติด", 2, 15), "109": ("31.ห้องคลอด", 3, 60),
    "038": ("32.ผู้ป่วยใน (ชาย)", 99, 9999), "037": ("33.ผู้ป่วยใน (หญิง)", 99, 9999),
}
FINISH = {"176": "99.ตรวจเสร็จกลับบ้าน", "999": "999.รับยากลับบ้าน"}
ADMIT = ("038", "037")

# แผนกหลัก: (อักษรคิว neoQ, น้ำหนักการมา, เส้นทางหลัก)
FLOWS = {
    "144": ("G", 30, ["144", "138", "145", "001", "010", "999"]),
    "024": ("C", 18, ["024", "036", "188", "039", "999"]),
    "110": ("E", 8, ["110", "189", "176"]),
    "190": ("D", 8, ["190", "028", "176"]),
    "047": ("F", 7, ["047", "005", "002", "010", "999"]),
    "033": ("A", 6, ["033", "176"]),
    "046": ("P", 5, ["046", "176"]),
    "035": ("T", 4, ["035", "001", "999"]),
    "031": ("K", 4, ["031", "176"]),
    "185": ("M", 3, ["185", "010", "999"]),
}
# หน่วยที่มีหลายห้อง: เลขห้องย่อย (room_hint) = ช่องบริการที่รับผู้ป่วย + ค่าชดเชย
ROOM_HINT = {"144": 0, "138": 0, "036": 0, "024": 0, "005": 0, "028": 0, "185": 0, "145": 3, "188": 4}

SCHEMA = """
CREATE TABLE IF NOT EXISTS kskdepartment (depcode TEXT PRIMARY KEY, department TEXT);
CREATE TABLE IF NOT EXISTS patient (hn TEXT PRIMARY KEY, pname TEXT, fname TEXT, lname TEXT, birthday TEXT, sex TEXT);
CREATE TABLE IF NOT EXISTS ovst (
    vn TEXT PRIMARY KEY, hn TEXT, vstdate TEXT, vsttime TEXT, oqueue INTEGER, main_dep TEXT,
    cur_dep TEXT, cur_dep_busy TEXT, cur_dep_time TEXT, ovstost TEXT, doctor_room TEXT, queue_no TEXT);
CREATE TABLE IF NOT EXISTS opdscreen (vn TEXT PRIMARY KEY, bw REAL, bps INTEGER, bpd INTEGER, temperature REAL);
CREATE TABLE IF NOT EXISTS mock_orders (vn TEXT, vstdate TEXT, depcode TEXT, status TEXT, PRIMARY KEY (vn, depcode));
CREATE INDEX IF NOT EXISTS ix_ovst_date ON ovst(vstdate);
"""


@dataclass
class Agent:
    vn: str
    main_dep: str
    plan: list = field(default_factory=list)   # หน่วยที่ต้องไปต่อ
    dep: str = ""
    queued_at: datetime | None = None
    ready_at: datetime | None = None             # เวลาที่เดินถึงหน่วย (เรียกคิวได้)
    busy_until: datetime | None = None
    server: int = 0
    hold_until: datetime | None = None           # รอเจ้าหน้าที่ส่งต่อ (สถานะ service_done)
    returned: bool = False
    child: bool = False


class Simulator:
    def __init__(self):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.rng = random.Random()
        self.rush = False
        self.agents: dict[str, Agent] = {}
        self.issued: set[str] = set()
        self.busy_servers: dict[str, set] = {d: set() for d in DEPARTMENTS}
        self.last_tick: datetime | None = None
        self.queue_no = 0
        self.prefix_no: dict[str, int] = {}
        self.conn = sqlite3.connect(MOCK_DB_PATH, check_same_thread=False, timeout=15)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.reset()

    # ---------------------------------------------------------------- setup
    def reset(self):
        cur = self.conn.cursor()
        for t in ("ovst", "opdscreen", "mock_orders", "patient", "kskdepartment"):
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.executescript(SCHEMA)
        names = {k: v[0] for k, v in DEPARTMENTS.items()} | FINISH
        cur.executemany("INSERT INTO kskdepartment VALUES (?, ?)", list(names.items()))
        self.conn.commit()
        self.agents.clear()
        self.issued = set()
        self.busy_servers = {d: set() for d in DEPARTMENTS}
        self.queue_no = 0
        self.prefix_no = {}
        self.last_tick = clock.now()

    def warmup(self, minutes: float):
        """เดินเวลาจำลองไปข้างหน้าเพื่อให้มีผู้ป่วยในระบบตั้งแต่เปิดหน้าจอ"""
        step = timedelta(minutes=0.25)
        for _ in range(int(minutes / 0.25)):
            clock.advance(step)
            self.tick()

    # ---------------------------------------------------------------- loop
    def arrival_rate(self, now: datetime) -> float:
        h = now.hour + now.minute / 60
        if h < 7 or h >= 16:
            base = 0.05
        elif h < 9.5:
            base = 1.4
        elif h < 11.5:
            base = 1.0
        elif h < 13:
            base = 0.4
        elif h < 15.5:
            base = 0.6
        else:
            base = 0.15
        return base * (1.8 if self.rush else 1.0)

    def tick(self):
        now = clock.now()
        last = self.last_tick or now
        self.last_tick = now
        minutes = max(0.0, min((now - last).total_seconds() / 60, 5))
        cur = self.conn.cursor()
        for _ in range(self._poisson(self.arrival_rate(now) * minutes)):
            self._register(cur, now)
        for ag in list(self.agents.values()):
            self._advance(cur, ag, now)
        self._call_next(cur, now)
        self.conn.commit()

    def _poisson(self, lam):
        if lam <= 0:
            return 0
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= L:
                return k
            k += 1

    # ---------------------------------------------------------------- "เจ้าหน้าที่" ทำงานใน HOSxP
    def _register(self, cur, now: datetime):
        main = self._weighted([(k, v[1]) for k, v in FLOWS.items()])
        prefix, _, plan = FLOWS[main]
        plan = list(plan)
        # ทางแยกที่พบบ่อยในข้อมูลจริง
        if main == "144" and self.rng.random() < 0.55:
            plan.remove("001")                                   # ไม่ต้องผ่านการเงิน
        if main == "110":
            r = self.rng.random()
            if r < 0.12:
                plan[-1] = self.rng.choice(ADMIT)               # รับไว้นอนโรงพยาบาล
            elif r < 0.35:
                plan[-1:] = ["010", "999"]
        if main == "033" and self.rng.random() < 0.06:
            plan[-1] = "109"                                     # ฝากครรภ์ → ห้องคลอด
        self.queue_no += 1
        self.prefix_no[prefix] = self.prefix_no.get(prefix, 0) + 1
        child = main == "033" and self.rng.random() < 0.4
        age = self.rng.randint(0, 12) if child else self.rng.randint(16, 88)
        hn = f"{self.rng.randint(1, 699999):07d}"
        birthday = date(now.year - age, self.rng.randint(1, 12), self.rng.randint(1, 28))
        cur.execute("INSERT OR REPLACE INTO patient VALUES (?,?,?,?,?,?)",
                    (hn, "", "ผู้ป่วย", "จำลอง", birthday.isoformat(), self.rng.choice(["1", "2"])))
        vn = now.strftime("%y%m%d%H%M%S")
        while vn in self.issued:
            vn = str(int(vn) + 1)
        self.issued.add(vn)
        first = plan.pop(0)
        ag = Agent(vn=vn, main_dep=main, plan=plan, child=child)
        self.agents[vn] = ag
        cur.execute("INSERT INTO ovst (vn, hn, vstdate, vsttime, oqueue, main_dep, cur_dep, cur_dep_busy, cur_dep_time, queue_no) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (vn, hn, now.date().isoformat(), now.strftime("%H:%M:%S"), self.queue_no, main, first, "N",
                     now.strftime("%H:%M:%S"), f"{prefix}{self.prefix_no[prefix]}"))
        self._enter(ag, first, now, walk=0.5)

    def _enter(self, ag: Agent, dep: str, now: datetime, walk: float | None = None):
        ag.dep = dep
        ag.queued_at = now
        ag.ready_at = now + timedelta(minutes=walk if walk is not None else self.rng.uniform(0.8, 2.5))
        ag.busy_until = None
        ag.hold_until = None

    def _send(self, cur, ag: Agent, dep: str, now: datetime):
        if dep in FINISH:
            cur.execute("UPDATE ovst SET cur_dep=?, cur_dep_busy='N', cur_dep_time=?, ovstost='1', doctor_room=NULL WHERE vn=?",
                        (dep, now.strftime("%H:%M:%S"), ag.vn))
            del self.agents[ag.vn]
            return
        cur.execute("UPDATE ovst SET cur_dep=?, cur_dep_busy='N', cur_dep_time=?, doctor_room=NULL WHERE vn=?",
                    (dep, now.strftime("%H:%M:%S"), ag.vn))
        self._enter(ag, dep, now, walk=self.rng.uniform(2, 5) if dep in ADMIT else None)

    def _call_next(self, cur, now: datetime):
        for dep, (_, servers, avg) in DEPARTMENTS.items():
            free = [s for s in range(1, servers + 1) if s not in self.busy_servers[dep]]
            if not free:
                continue
            waiting = sorted((a for a in self.agents.values()
                              if a.dep == dep and a.busy_until is None and a.hold_until is None
                              and a.ready_at and a.ready_at <= now), key=lambda a: a.queued_at)
            for ag, server in zip(waiting, free):
                self.busy_servers[dep].add(server)
                ag.server = server
                factor = 0.5 if ag.returned and dep == "138" else 1.0
                ag.busy_until = now + timedelta(minutes=max(0.5, self.rng.lognormvariate(math.log(avg * factor), 0.35)))
                hint = str(server + ROOM_HINT[dep]) if dep in ROOM_HINT else None
                cur.execute("UPDATE ovst SET cur_dep_busy='Y', doctor_room=? WHERE vn=?", (hint, ag.vn))
                if dep in ("019", "034"):
                    cur.execute("UPDATE mock_orders SET status='received' WHERE vn=? AND depcode=?", (ag.vn, dep))

    def _advance(self, cur, ag: Agent, now: datetime):
        if ag.hold_until is not None:
            if now >= ag.hold_until:
                self._send(cur, ag, ag.plan.pop(0), now)
            return
        if ag.busy_until is None or now < ag.busy_until:
            return
        dep = ag.dep
        self.busy_servers[dep].discard(ag.server)
        if dep in ADMIT:                     # ผู้ป่วยใน: อยู่ที่หอผู้ป่วยต่อ
            ag.busy_until = now + timedelta(hours=12)
            return
        if dep in ("144", "024", "047", "190", "033", "110"):  # จุดคัดกรอง/ซักประวัติ: บันทึกสัญญาณชีพ
            sbp = self.rng.randint(102, 165)
            cur.execute("INSERT OR REPLACE INTO opdscreen VALUES (?,?,?,?,?)",
                        (ag.vn, round(self.rng.uniform(14, 30) if ag.child else self.rng.uniform(42, 92), 1),
                         sbp, self.rng.randint(62, 95), round(self.rng.uniform(36.2, 37.9), 1)))
        if dep in ("019", "034"):
            cur.execute("UPDATE mock_orders SET status='done' WHERE vn=? AND depcode=?", (ag.vn, dep))
        # ห้องตรวจอายุรกรรม: ส่ง LAB / X-ray แล้วกลับมาพบแพทย์
        if dep == "138" and not ag.returned:
            orders = [o for o, p in (("019", 0.3), ("034", 0.1)) if self.rng.random() < p]
            if orders:
                ag.returned = True
                for o in orders:
                    cur.execute("INSERT OR REPLACE INTO mock_orders VALUES (?,?,?,?)", (ag.vn, now.date().isoformat(), o, "ordered"))
                ag.plan = orders + ["138"] + ag.plan
                cur.execute("UPDATE ovst SET cur_dep_busy='N' WHERE vn=?", (ag.vn,))
                ag.busy_until = None
                ag.hold_until = now + timedelta(minutes=self.rng.uniform(1.5, 4))   # รอส่งต่อ (งานค้างหลายห้อง)
                return
        if dep == "005" and self.rng.random() < 0.15:          # ARI → X-ray ของ ARI (034 เฉพาะ main_dep 047)
            ag.plan = ["034"] + ag.plan
        if not ag.plan:
            cur.execute("UPDATE ovst SET cur_dep_busy='N', ovstost='1' WHERE vn=?", (ag.vn,))
            del self.agents[ag.vn]
            return
        self._send(cur, ag, ag.plan.pop(0), now)

    def _weighted(self, items):
        total = sum(w for _, w in items)
        r = self.rng.uniform(0, total)
        for k, w in items:
            r -= w
            if r <= 0:
                return k
        return items[-1][0]

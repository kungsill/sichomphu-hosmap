"""ฐานข้อมูล HOSxP จำลอง + ตัวจำลองผู้ป่วย (ใช้เฉพาะโหมดสาธิต HOSXP_MODE=mock)

ตัวจำลองทำหน้าที่แทน "เจ้าหน้าที่ที่ทำงานใน HOSxP" คือ ลงทะเบียน ส่งตรวจ รับผู้ป่วย ส่งต่อ และจบงาน
โดยเขียนลงตาราง ovst / opdscreen / mock_orders เท่านั้น ระบบนำทางจะอ่านผ่าน Worker ตัวเดียวกับของจริง
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

# รหัสหน่วยบริการสมมติ (ตรงกับตัวอย่างใน seed.py)
DEPARTMENTS = {
    "001": ("เวชระเบียน", 3, 2.5), "002": ("คัดกรอง", 3, 3),
    "010": ("อายุรกรรม", 2, 5.5), "012": ("กุมารเวชกรรม", 1, 6), "013": ("ศัลยกรรม", 1, 8),
    "014": ("ศัลยกรรมกระดูกและข้อ", 1, 8), "040": ("ทันตกรรม", 1, 12), "041": ("กายภาพบำบัด", 2, 15),
    "020": ("ห้องปฏิบัติการ (LAB)", 2, 4), "021": ("รังสีวิทยา (X-ray)", 1, 5),
    "030": ("การเงิน", 2, 2.5), "031": ("ห้องยา", 3, 3.5),
}
DOCTOR_CHOICE = [("010", 45), ("012", 14), ("013", 14), ("014", 12), ("040", 8), ("041", 7)]

SCHEMA = """
CREATE TABLE IF NOT EXISTS kskdepartment (depcode TEXT PRIMARY KEY, department TEXT);
CREATE TABLE IF NOT EXISTS patient (hn TEXT PRIMARY KEY, pname TEXT, fname TEXT, lname TEXT, birthday TEXT, sex TEXT);
CREATE TABLE IF NOT EXISTS ovst (
    vn TEXT PRIMARY KEY, hn TEXT, vstdate TEXT, vsttime TEXT, oqueue INTEGER, main_dep TEXT,
    cur_dep TEXT, cur_dep_busy TEXT, cur_dep_time TEXT, ovstost TEXT, doctor_room TEXT);
CREATE TABLE IF NOT EXISTS opdscreen (vn TEXT PRIMARY KEY, bw REAL, bps INTEGER, bpd INTEGER, temperature REAL);
CREATE TABLE IF NOT EXISTS mock_orders (vn TEXT, vstdate TEXT, depcode TEXT, status TEXT, PRIMARY KEY (vn, depcode));
CREATE INDEX IF NOT EXISTS ix_ovst_date ON ovst(vstdate);
"""


@dataclass
class Agent:
    vn: str
    main_dep: str
    plan: list = field(default_factory=list)   # รายการหน่วยที่ต้องไปต่อ
    dep: str = ""
    queued_at: datetime | None = None
    ready_at: datetime | None = None             # เวลาที่เดินถึงหน่วย (เรียกคิวได้)
    busy_until: datetime | None = None
    server: int = 0
    hold_until: datetime | None = None           # รอเจ้าหน้าที่ส่งต่อ (สถานะ service_done)
    orders: list = field(default_factory=list)
    returned: bool = False


class Simulator:
    def __init__(self):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.rng = random.Random()
        self.rush = False
        self.agents: dict[str, Agent] = {}
        self.busy_servers: dict[str, set] = {d: set() for d in DEPARTMENTS}
        self.last_tick: datetime | None = None
        self.queue_no = 0
        self.conn = sqlite3.connect(MOCK_DB_PATH, check_same_thread=False, timeout=15)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.reset()

    # ---------------------------------------------------------------- setup
    def reset(self):
        cur = self.conn.cursor()
        for t in ("ovst", "opdscreen", "mock_orders", "patient", "kskdepartment"):
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.executescript(SCHEMA)
        cur.executemany("INSERT INTO kskdepartment VALUES (?, ?)", [(k, v[0]) for k, v in DEPARTMENTS.items()])
        self.conn.commit()
        self.agents.clear()
        self.issued = set()
        self.busy_servers = {d: set() for d in DEPARTMENTS}
        self.queue_no = 0
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
            base = 0.03
        elif h < 9.5:
            base = 0.8
        elif h < 11.5:
            base = 0.65
        elif h < 13:
            base = 0.25
        elif h < 15.5:
            base = 0.4
        else:
            base = 0.1
        return base * (1.9 if self.rush else 1.0)

    def tick(self):
        now = clock.now()
        last = self.last_tick or now
        self.last_tick = now
        minutes = max(0.0, min((now - last).total_seconds() / 60, 5))
        cur = self.conn.cursor()
        # ผู้ป่วยมาใหม่ (Poisson)
        lam = self.arrival_rate(now) * minutes
        n = self._poisson(lam)
        for _ in range(n):
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

    # ---------------------------------------------------------------- staff actions in "HOSxP"
    def _register(self, cur, now: datetime):
        self.queue_no += 1
        main = self._weighted(DOCTOR_CHOICE)
        age = self.rng.randint(1, 14) if main == "012" else self.rng.randint(16, 88)
        hn = f"{self.rng.randint(1, 699999):07d}"
        birthday = date(now.year - age, self.rng.randint(1, 12), self.rng.randint(1, 28))
        cur.execute("INSERT OR REPLACE INTO patient VALUES (?,?,?,?,?,?)",
                    (hn, "", "ผู้ป่วย", "จำลอง", birthday.isoformat(), self.rng.choice(["1", "2"])))
        vn = now.strftime("%y%m%d%H%M%S")
        while vn in self.issued:
            vn = str(int(vn) + 1)
        self.issued.add(vn)
        ag = Agent(vn=vn, main_dep=main, plan=["002", main])
        self.agents[vn] = ag
        cur.execute("INSERT INTO ovst (vn, hn, vstdate, vsttime, oqueue, main_dep, cur_dep, cur_dep_busy, cur_dep_time) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (vn, hn, now.date().isoformat(), now.strftime("%H:%M:%S"), self.queue_no, main, "001", "N",
                     now.strftime("%H:%M:%S")))
        self._enter(ag, "001", now, walk=0.5)

    def _enter(self, ag: Agent, dep: str, now: datetime, walk: float | None = None):
        ag.dep = dep
        ag.queued_at = now
        ag.ready_at = now + timedelta(minutes=walk if walk is not None else self.rng.uniform(0.8, 2.5))
        ag.busy_until = None
        ag.hold_until = None

    def _send(self, cur, ag: Agent, dep: str, now: datetime):
        cur.execute("UPDATE ovst SET cur_dep=?, cur_dep_busy='N', cur_dep_time=?, doctor_room=NULL WHERE vn=?",
                    (dep, now.strftime("%H:%M:%S"), ag.vn))
        self._enter(ag, dep, now)

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
                factor = 0.5 if ag.returned and dep == ag.main_dep else 1.0
                ag.busy_until = now + timedelta(minutes=max(0.5, self.rng.lognormvariate(math.log(avg * factor), 0.35)))
                room = str(server) if dep == "010" else None
                cur.execute("UPDATE ovst SET cur_dep_busy='Y', doctor_room=? WHERE vn=?", (room, ag.vn))
                if dep in ("020", "021"):
                    cur.execute("UPDATE mock_orders SET status='received' WHERE vn=? AND depcode=?", (ag.vn, dep))

    def _advance(self, cur, ag: Agent, now: datetime):
        if ag.hold_until is not None:
            if now >= ag.hold_until:
                self._send(cur, ag, ag.plan.pop(0), now)
            return
        if ag.busy_until is None or now < ag.busy_until:
            return
        # ให้บริการเสร็จ
        dep = ag.dep
        self.busy_servers[dep].discard(ag.server)
        if dep == "002":
            sbp = self.rng.randint(102, 165)
            cur.execute("INSERT OR REPLACE INTO opdscreen VALUES (?,?,?,?,?)",
                        (ag.vn, round(self.rng.uniform(14, 30) if ag.main_dep == "012" else self.rng.uniform(42, 92), 1),
                         sbp, self.rng.randint(62, 95), round(self.rng.uniform(36.2, 37.9), 1)))
        if dep in ("020", "021"):
            cur.execute("UPDATE mock_orders SET status='done' WHERE vn=? AND depcode=?", (ag.vn, dep))
        if dep == ag.main_dep and not ag.returned:
            orders = []
            if ag.main_dep in ("010", "012", "013", "014"):
                if self.rng.random() < 0.32:
                    orders.append("020")
                if self.rng.random() < (0.3 if ag.main_dep in ("013", "014") else 0.1):
                    orders.append("021")
            if orders:
                ag.returned = True
                for o in orders:
                    cur.execute("INSERT OR REPLACE INTO mock_orders VALUES (?,?,?,?)",
                                (ag.vn, now.date().isoformat(), o, "ordered"))
                ag.plan = orders + [ag.main_dep, "030", "031"]
            else:
                ag.plan = ["030", "031"]
        elif dep == ag.main_dep and ag.returned:
            ag.plan = ["030", "031"]
        if not ag.plan:
            cur.execute("UPDATE ovst SET cur_dep_busy='N', ovstost='1' WHERE vn=?", (ag.vn,))
            del self.agents[ag.vn]
            return
        # หลังพบแพทย์และมีคำสั่งตรวจ: HOSxP ยังอยู่ที่ห้องตรวจ (สถานะรอส่งต่อ) ระยะหนึ่ง
        if dep == ag.main_dep and ag.plan and ag.plan[0] in ("020", "021"):
            cur.execute("UPDATE ovst SET cur_dep_busy='N' WHERE vn=?", (ag.vn,))
            ag.busy_until = None
            ag.hold_until = now + timedelta(minutes=self.rng.uniform(1.5, 4))
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

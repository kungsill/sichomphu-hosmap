"""ฐานข้อมูลระบบนำทาง hospital_navigation (แยกจากฐานข้อมูล HOSxP)"""
import json

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from . import config

LongText = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")
Id = sa.String(40)

metadata = sa.MetaData()

# ---------- แผนที่ (ฉบับร่างที่แก้ไขใน Map Builder) ----------
buildings = sa.Table(
    "buildings", metadata,
    sa.Column("id", Id, primary_key=True),
    sa.Column("code", sa.String(20), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("sort", sa.Integer, default=0),
)

floors = sa.Table(
    "floors", metadata,
    sa.Column("id", Id, primary_key=True),
    sa.Column("building_id", Id, sa.ForeignKey("buildings.id"), nullable=False),
    sa.Column("level", sa.Integer, nullable=False, default=1),
    sa.Column("name", sa.String(100), nullable=False),
    sa.Column("width", sa.Float, nullable=False, default=60),   # เมตร
    sa.Column("height", sa.Float, nullable=False, default=40),  # เมตร
    sa.Column("plan_image", sa.String(300)),                    # รูปแปลน PNG/SVG
    sa.Column("plan_opacity", sa.Float, default=0.5),
)

rooms = sa.Table(
    "rooms", metadata,
    sa.Column("id", Id, primary_key=True),
    sa.Column("floor_id", Id, sa.ForeignKey("floors.id"), nullable=False),
    sa.Column("code", sa.String(20), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("short_name", sa.String(60)),
    # service = ห้องมีผนัง, counter = เคาน์เตอร์บริการแบบเปิด, waiting = พื้นที่นั่งรอ, corridor = ทางเดิน, other
    sa.Column("kind", sa.String(20), nullable=False, default="service"),
    sa.Column("polygon", sa.Text, nullable=False),  # JSON [[x,y],...] หน่วยเมตร
    sa.Column("door_node_id", Id),
    sa.Column("color", sa.String(20)),
    sa.Column("capacity", sa.Integer, default=20),
    sa.Column("seats", sa.Boolean, default=False),   # วาดเก้าอี้นั่งรอ
    sa.Column("desk", sa.String(10)),                 # ตำแหน่งโต๊ะ/เคาน์เตอร์ n/s/e/w
    sa.Column("decor", sa.String(20)),                # ของตกแต่ง: pharmacy (ชั้นวางยา), cashier (ตู้เอกสาร)
)

map_nodes = sa.Table(
    "map_nodes", metadata,
    sa.Column("id", Id, primary_key=True),
    sa.Column("floor_id", Id, sa.ForeignKey("floors.id"), nullable=False),
    # door, corridor, junction, elevator, stairs, ramp, entrance
    sa.Column("kind", sa.String(20), nullable=False, default="corridor"),
    sa.Column("x", sa.Float, nullable=False),
    sa.Column("y", sa.Float, nullable=False),
    sa.Column("name", sa.String(100)),
    # จุดลิฟต์/บันไดที่ link_group เดียวกันบนคนละชั้นจะเชื่อมกันอัตโนมัติ
    sa.Column("link_group", sa.String(40)),
)

map_edges = sa.Table(
    "map_edges", metadata,
    sa.Column("id", Id, primary_key=True),
    sa.Column("node_a", Id, sa.ForeignKey("map_nodes.id"), nullable=False),
    sa.Column("node_b", Id, sa.ForeignKey("map_nodes.id"), nullable=False),
    sa.Column("kind", sa.String(20), nullable=False, default="walk"),  # walk, stairs, ramp
    sa.Column("accessible", sa.Boolean, nullable=False, default=True),  # รถเข็นผ่านได้
)

hosxp_room_mapping = sa.Table(
    "hosxp_room_mapping", metadata,
    sa.Column("id", Id, primary_key=True),
    sa.Column("depcode", sa.String(20), nullable=False, index=True),  # รหัสหน่วยบริการใน HOSxP
    sa.Column("dep_name", sa.String(200)),
    sa.Column("room_id", Id),            # ห้องที่ให้บริการ
    sa.Column("wait_room_id", Id),       # พื้นที่นั่งรอของหน่วยบริการ
    sa.Column("room_hint", sa.String(40)),  # ใช้แยกห้องย่อย ถ้า HOSxP บันทึกไว้
    # ใช้เฉพาะผู้ป่วยที่แผนกหลัก (ovst.main_dep) ตรงกับรายการนี้ เช่น "047" — รหัสเดียวกันแต่อยู่คนละโซน
    sa.Column("for_main_dep", sa.String(100)),
    sa.Column("is_default", sa.Boolean, default=True),
    # ขั้นตอน: register, screening, doctor, lab, xray, finance, pharmacy, other
    sa.Column("stage", sa.String(20), default="other"),
    sa.Column("priority", sa.Integer, default=50),  # ลำดับเมื่อมีงานค้างหลายห้อง (น้อย = ไปก่อน)
    sa.Column("queue_prefix", sa.String(4)),
    sa.Column("servers", sa.Integer, default=1),      # จำนวนช่องบริการ
    sa.Column("avg_service_min", sa.Float, default=5),
)

map_versions = sa.Table(
    "map_versions", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("published_at", sa.DateTime, nullable=False),
    sa.Column("note", sa.String(200)),
    sa.Column("data", LongText, nullable=False),
)

# ---------- ผู้ป่วย ----------
patient_visits = sa.Table(
    "patient_visits", metadata,
    sa.Column("vn", sa.String(20), primary_key=True),
    sa.Column("hn", sa.String(20), nullable=False, index=True),
    sa.Column("vstdate", sa.Date, nullable=False, index=True),
    sa.Column("vsttime", sa.String(8)),
    sa.Column("oqueue", sa.Integer),
    sa.Column("queue_no", sa.String(20), index=True),  # เลขคิวที่พิมพ์บนใบคิว (เช่น neoQ: G113)
    sa.Column("main_dep", sa.String(20)),
    sa.Column("age", sa.Integer),
    sa.Column("sex", sa.String(2)),
    sa.Column("vitals", sa.Text),  # JSON น้ำหนัก ความดัน อุณหภูมิ (ถ้าเปิด SHOW_VITALS)
    sa.Column("created_at", sa.DateTime, nullable=False),
)

patient_status = sa.Table(
    "patient_status", metadata,
    sa.Column("vn", sa.String(20), primary_key=True),
    sa.Column("cur_dep", sa.String(20)),
    sa.Column("busy", sa.Boolean, default=False),
    sa.Column("cur_dep_time", sa.DateTime),     # เวลาที่ถูกส่งมาหน่วยปัจจุบัน
    sa.Column("busy_since", sa.DateTime),
    sa.Column("prev_dep", sa.String(20)),
    sa.Column("room_hint", sa.String(40)),
    # state: waiting, in_service, service_done, finished, cancelled
    sa.Column("state", sa.String(20), nullable=False),
    sa.Column("dest_dep", sa.String(20)),
    sa.Column("pending", sa.Text),              # JSON [{depcode,status}]
    sa.Column("stages_done", sa.Text),          # JSON ["register","screening",...]
    sa.Column("route", sa.Text),                # JSON เส้นทางล่าสุด [[floor_id,x,y],...]
    sa.Column("route_id", sa.Integer, default=0),
    sa.Column("finished_at", sa.DateTime),
    sa.Column("missing_polls", sa.Integer, default=0),
    sa.Column("updated_at", sa.DateTime, nullable=False),
)

patient_events = sa.Table(
    "patient_events", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("vn", sa.String(20), nullable=False, index=True),
    # registered, sent, in_service, service_done, left, order_added, order_done, finished, cancelled, resync
    sa.Column("event_type", sa.String(20), nullable=False),
    sa.Column("depcode", sa.String(20)),
    sa.Column("detail", sa.String(300)),
    sa.Column("event_time", sa.DateTime, nullable=False),
)

navigation_tokens = sa.Table(
    "navigation_tokens", metadata,
    sa.Column("token", sa.String(64), primary_key=True),
    sa.Column("vn", sa.String(20), nullable=False, index=True),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("expires_at", sa.DateTime, nullable=False),
    sa.Column("revoked", sa.Boolean, default=False),
)

sync_state = sa.Table(
    "sync_state", metadata,
    sa.Column("key", sa.String(40), primary_key=True),
    sa.Column("value", sa.Text),
)

MAP_TABLES = (buildings, floors, rooms, map_nodes, map_edges, hosxp_room_mapping)
PATIENT_TABLES = (patient_visits, patient_status, patient_events, navigation_tokens)

_engine_kwargs = {"pool_pre_ping": True, "future": True}
if config.NAV_DB_URL.startswith("sqlite"):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
else:
    _engine_kwargs["pool_recycle"] = 3600

engine = sa.create_engine(config.NAV_DB_URL, **_engine_kwargs)

if engine.dialect.name == "sqlite":
    @sa.event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


def init_db() -> None:
    metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """อัปเกรดฐานข้อมูลเดิม: เพิ่มคอลัมน์ใหม่ที่ยังไม่มี (ไม่ลบหรือแก้ข้อมูลเดิม)"""
    insp = sa.inspect(engine)
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(sa.text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}"))


def rows(result) -> list[dict]:
    return [dict(r._mapping) for r in result]


def jload(value, default=None):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def jdump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

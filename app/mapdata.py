"""แผนที่โรงพยาบาล: อ่าน/บันทึกฉบับร่าง เผยแพร่ และคำนวณเส้นทางด้วย Dijkstra บนกราฟจุดนำทาง"""
import heapq
import math
import threading
from datetime import datetime

import sqlalchemy as sa

from . import db
from .db import jdump, jload, rows

ROOM_FIELDS = ("id", "floor_id", "code", "name", "short_name", "kind", "polygon", "door_node_id",
               "color", "capacity", "seats", "desk")


# ---------------------------------------------------------------- draft document

def load_draft(conn) -> dict:
    doc = {
        "buildings": rows(conn.execute(sa.select(db.buildings).order_by(db.buildings.c.sort))),
        "floors": rows(conn.execute(sa.select(db.floors).order_by(db.floors.c.level))),
        "rooms": rows(conn.execute(sa.select(db.rooms))),
        "nodes": rows(conn.execute(sa.select(db.map_nodes))),
        "edges": rows(conn.execute(sa.select(db.map_edges))),
        "mapping": rows(conn.execute(sa.select(db.hosxp_room_mapping).order_by(db.hosxp_room_mapping.c.depcode))),
    }
    for r in doc["rooms"]:
        r["polygon"] = jload(r["polygon"], [])
    return doc


def save_draft(conn, doc: dict) -> None:
    """แทนที่แผนที่ฉบับร่างทั้งชุด (id เป็นข้อความที่ฝั่ง Map Builder สร้าง จึงคงที่ข้ามการบันทึก)"""
    errors = validate(doc)
    if errors:
        raise ValueError("; ".join(errors[:10]))
    for table in (db.hosxp_room_mapping, db.map_edges, db.rooms, db.map_nodes, db.floors, db.buildings):
        conn.execute(table.delete())

    def pick(item, table):
        cols = table.c.keys()
        return {k: item.get(k) for k in cols if k in item}

    for b in doc.get("buildings", []):
        conn.execute(db.buildings.insert().values(**pick(b, db.buildings)))
    for f in doc.get("floors", []):
        conn.execute(db.floors.insert().values(**pick(f, db.floors)))
    for n in doc.get("nodes", []):
        conn.execute(db.map_nodes.insert().values(**pick(n, db.map_nodes)))
    for r in doc.get("rooms", []):
        values = pick(r, db.rooms)
        values["polygon"] = jdump(r.get("polygon") or [])
        conn.execute(db.rooms.insert().values(**values))
    for e in doc.get("edges", []):
        conn.execute(db.map_edges.insert().values(**pick(e, db.map_edges)))
    for m in doc.get("mapping", []):
        conn.execute(db.hosxp_room_mapping.insert().values(**pick(m, db.hosxp_room_mapping)))


def validate(doc: dict) -> list[str]:
    errors = []
    building_ids = {b["id"] for b in doc.get("buildings", [])}
    floor_ids = {f["id"] for f in doc.get("floors", [])}
    node_ids = {n["id"] for n in doc.get("nodes", [])}
    room_ids = {r["id"] for r in doc.get("rooms", [])}
    for f in doc.get("floors", []):
        if f.get("building_id") not in building_ids:
            errors.append(f"ชั้น {f.get('name')} ไม่มีอาคาร")
    for n in doc.get("nodes", []):
        if n.get("floor_id") not in floor_ids:
            errors.append(f"จุด {n.get('id')} ไม่มีชั้น")
    for r in doc.get("rooms", []):
        if r.get("floor_id") not in floor_ids:
            errors.append(f"ห้อง {r.get('name')} ไม่มีชั้น")
        if len(r.get("polygon") or []) < 3:
            errors.append(f"ห้อง {r.get('name')} ขอบเขตไม่ครบ")
        if r.get("door_node_id") and r["door_node_id"] not in node_ids:
            r["door_node_id"] = None
    doc["edges"] = [e for e in doc.get("edges", []) if e.get("node_a") in node_ids and e.get("node_b") in node_ids]
    for m in doc.get("mapping", []):
        if not m.get("depcode"):
            errors.append("มีรายการจับคู่ HOSxP ที่ไม่มีรหัสหน่วยบริการ")
        for key in ("room_id", "wait_room_id"):
            if m.get(key) and m[key] not in room_ids:
                m[key] = None
    return errors


def publish(conn, note: str = "") -> int:
    doc = load_draft(conn)
    errors = validate(doc)
    if errors:
        raise ValueError("; ".join(errors[:10]))
    res = conn.execute(db.map_versions.insert().values(
        published_at=datetime.now().replace(microsecond=0), note=note[:200], data=jdump(doc)))
    version = res.inserted_primary_key[0]
    _cache.clear()
    return version


# ---------------------------------------------------------------- published map + routing

_cache: dict = {}
_cache_lock = threading.Lock()


def published(conn=None) -> "HospitalMap | None":
    """แผนที่ฉบับเผยแพร่ล่าสุด (cache ไว้จนกว่าจะเผยแพร่ใหม่)"""
    with _cache_lock:
        own = conn is None
        if own:
            conn = db.engine.connect()
        try:
            latest = conn.execute(sa.select(db.map_versions.c.id).order_by(db.map_versions.c.id.desc()).limit(1)).scalar()
            if latest is None:
                return None
            if _cache.get("version") != latest:
                data = conn.execute(sa.select(db.map_versions.c.data).where(db.map_versions.c.id == latest)).scalar()
                doc = jload(data, {})
                doc["version"] = latest
                _cache["version"] = latest
                _cache["map"] = HospitalMap(doc)
            return _cache["map"]
        finally:
            if own:
                conn.close()


def centroid(poly):
    if not poly:
        return (0.0, 0.0)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


class HospitalMap:
    VERTICAL = {
        "elevator": {"base": 15.0, "per_floor": 4.0, "accessible": True, "label": "ใช้ลิฟต์"},
        "ramp": {"base": 6.0, "per_floor": 18.0, "accessible": True, "label": "ใช้ทางลาด"},
        "stairs": {"base": 3.0, "per_floor": 9.0, "accessible": False, "label": "ใช้บันได"},
    }

    PORTALS = ("entrance", "exit", "portal", "gate")

    def __init__(self, doc: dict):
        self.doc = doc
        self.version = doc.get("version")
        self.floors = {f["id"]: f for f in doc.get("floors", [])}
        self.buildings = {b["id"]: b for b in doc.get("buildings", [])}
        self.rooms = {r["id"]: r for r in doc.get("rooms", [])}
        self.nodes = {n["id"]: n for n in doc.get("nodes", [])}
        self.mapping_by_dep: dict[str, list[dict]] = {}
        for m in doc.get("mapping", []):
            self.mapping_by_dep.setdefault(str(m["depcode"]), []).append(m)
        self.adj: dict[str, list[tuple]] = {nid: [] for nid in self.nodes}
        for e in doc.get("edges", []):
            a, b = self.nodes.get(e["node_a"]), self.nodes.get(e["node_b"])
            if not a or not b:
                continue
            dist = math.dist((a["x"], a["y"]), (b["x"], b["y"]))
            if e.get("kind") == "stairs":
                dist *= 1.6
            acc = bool(e.get("accessible", True)) and e.get("kind") != "stairs"
            self.adj[a["id"]].append((b["id"], dist, acc, e.get("kind") or "walk"))
            self.adj[b["id"]].append((a["id"], dist, acc, e.get("kind") or "walk"))
        groups: dict[str, list[dict]] = {}
        for n in self.nodes.values():
            if n.get("link_group") and (n.get("kind") in self.VERTICAL or n.get("kind") in self.PORTALS):
                groups.setdefault(n["link_group"], []).append(n)
        for members in groups.values():
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    if a["floor_id"] == b["floor_id"]:
                        continue
                    if a["kind"] in self.PORTALS and b["kind"] in self.PORTALS:
                        # ประตูโซน ↔ จุดหน้าตึกบนแผนที่ภาพรวม (เดินออก/เข้าอาคาร)
                        self.adj[a["id"]].append((b["id"], 3.0, True, "portal"))
                        self.adj[b["id"]].append((a["id"], 3.0, True, "portal"))
                        continue
                    if a["kind"] not in self.VERTICAL or b["kind"] not in self.VERTICAL:
                        continue
                    spec = self.VERTICAL[a["kind"]]
                    levels = abs(self.level(a["floor_id"]) - self.level(b["floor_id"]))
                    cost = spec["base"] + spec["per_floor"] * levels
                    self.adj[a["id"]].append((b["id"], cost, spec["accessible"], a["kind"]))
                    self.adj[b["id"]].append((a["id"], cost, spec["accessible"], a["kind"]))

    # -- helpers
    def level(self, floor_id) -> int:
        f = self.floors.get(floor_id)
        return int(f["level"]) if f else 0

    def floor_label(self, floor_id) -> str:
        f = self.floors.get(floor_id)
        if not f:
            return ""
        b = self.buildings.get(f["building_id"])
        return f"{b['name']} {f['name']}" if b else f["name"]

    def room_name(self, room_id) -> str:
        r = self.rooms.get(room_id)
        return r["name"] if r else ""

    def room_center(self, room_id):
        r = self.rooms[room_id]
        return centroid(r["polygon"])

    def room_door(self, room_id) -> str | None:
        r = self.rooms.get(room_id)
        if not r:
            return None
        if r.get("door_node_id") in self.nodes:
            return r["door_node_id"]
        cx, cy = centroid(r["polygon"])
        best, best_d = None, 1e18
        for n in self.nodes.values():
            if n["floor_id"] != r["floor_id"]:
                continue
            d = math.dist((cx, cy), (n["x"], n["y"]))
            if d < best_d:
                best, best_d = n["id"], d
        return best

    def building_of(self, room_or_node_id) -> str | None:
        item = self.rooms.get(room_or_node_id) or self.nodes.get(room_or_node_id)
        f = self.floors.get(item["floor_id"]) if item else None
        return f["building_id"] if f else None

    def _gate(self, kinds, building=None, near=None) -> str | None:
        cands = [n for n in self.nodes.values() if n.get("kind") in kinds
                 and (building is None or self.floors.get(n["floor_id"], {}).get("building_id") == building)]
        if not cands:
            return None
        if near and near in self.rooms:
            cx, cy = self.room_center(near)
            same = self.rooms[near]["floor_id"]
            cands.sort(key=lambda n: (n["floor_id"] != same, math.dist((cx, cy), (n["x"], n["y"]))))
        else:
            cands.sort(key=lambda n: (self.level(n["floor_id"]), n["id"]))
        return cands[0]["id"]

    def entrance(self, near_room=None) -> str | None:
        """ทางเข้าของโซน/อาคารเดียวกับห้องที่ระบุ"""
        b = self.building_of(near_room) if near_room else None
        return self._gate(("entrance",), b, near_room) or self._gate(("entrance",))

    def exit_node(self, near_room=None) -> str | None:
        """ทางออก: ถ้ามีแผนที่ภาพรวมและโซนนี้เชื่อมไว้ → ประตูใหญ่โรงพยาบาล ไม่งั้นทางออกของโซน"""
        b = self.building_of(near_room) if near_room else None
        gate = self._gate(("gate",))
        if gate and b:
            linked = any(n.get("link_group") and n.get("kind") in self.PORTALS
                         and self.floors.get(n["floor_id"], {}).get("building_id") == b for n in self.nodes.values())
            if linked:
                return gate
        return (self._gate(("exit",), b, near_room) or self._gate(("entrance",), b, near_room)
                or self._gate(("exit", "entrance")))

    # -- HOSxP mapping
    @staticmethod
    def _zones(m) -> list[str]:
        return [z.strip() for z in str(m.get("for_main_dep") or "").split(",") if z.strip()]

    def _rows(self, depcode, main_dep=None) -> list[dict]:
        """แถวจับคู่ของหน่วยบริการ โดยเลือกแถวเฉพาะโซนก่อน (ตามแผนกหลักของผู้ป่วย) แล้วจึงแถวทั่วไป"""
        items = self.mapping_by_dep.get(str(depcode)) if depcode is not None else None
        if not items:
            return []
        if main_dep is not None:
            specific = [m for m in items if str(main_dep) in self._zones(m)]
            if specific:
                return specific
            return [m for m in items if not self._zones(m)]
        return [m for m in items if not self._zones(m)] or items

    def zone_key(self, depcode, main_dep=None) -> str | None:
        """คีย์จุดบริการ (รหัส + โซน) ใช้แยกคิวของรหัสเดียวกันที่อยู่คนละโซน"""
        rows = self._rows(depcode, main_dep)
        if not rows:
            return None
        z = rows[0].get("for_main_dep") or ""
        return f"{depcode}@{z}" if z else str(depcode)

    def resolve_dep(self, depcode, room_hint=None, main_dep=None) -> dict | None:
        """หาห้องของหน่วยบริการ ถ้าแผนกเดียวมีหลายห้องจะใช้ room_hint ถ้าไม่มีจะไม่เดา แต่พาไปพื้นที่รอของแผนก"""
        items = self._rows(depcode, main_dep)
        if not items:
            return None
        if room_hint:
            for m in items:
                if m.get("room_hint") and str(m["room_hint"]) == str(room_hint):
                    return {**m, "exact": True}
        if len(items) == 1:
            return {**items[0], "exact": True}
        default = next((m for m in items if m.get("is_default")), items[0])
        # ไม่รู้ห้องย่อย: ให้ไปพื้นที่รอของแผนกแทนการเดาห้อง
        return {**default, "room_id": default.get("wait_room_id") or default.get("room_id"), "exact": False}

    def dep_info(self, depcode, main_dep=None) -> dict:
        items = self._rows(depcode, main_dep)
        return items[0] if items else {}

    # -- routing
    def shortest(self, start: str, goal: str, accessible: bool = False):
        if start not in self.adj or goal not in self.adj:
            return None
        dist = {start: 0.0}
        prev: dict[str, tuple] = {}
        heap = [(0.0, start)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == goal:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, w, acc, kind in self.adj[u]:
                if accessible and not acc:
                    continue
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = (u, kind)
                    heapq.heappush(heap, (nd, v))
        if goal not in dist:
            return None
        nodes = [goal]
        while nodes[-1] != start:
            nodes.append(prev[nodes[-1]][0])
        nodes.reverse()
        # คู่ (จุด, ชนิดเส้นทางที่ออกจากจุดนี้ไปจุดถัดไป)
        path = [(n, prev[nodes[i + 1]][1] if i + 1 < len(nodes) else None) for i, n in enumerate(nodes)]
        return path, dist[goal]

    def route(self, from_room=None, to_room=None, accessible=False, from_node=None, to_node=None) -> dict | None:
        """เส้นทางจากห้อง (หรือจุด) ไปห้องปลายทาง (หรือจุด) คืนพิกัดตามชั้น + คำแนะนำการเดิน"""
        if from_room not in self.rooms:
            from_room = None
        if to_node is None and to_room not in self.rooms:
            return None
        start = from_node or (self.room_door(from_room) if from_room else self.entrance(to_room))
        goal = to_node or self.room_door(to_room)
        if not start or not goal:
            return None
        found = self.shortest(start, goal, accessible)
        if not found:
            return {"ok": False, "reason": "ไม่พบเส้นทางที่เหมาะสม" + (" สำหรับรถเข็น" if accessible else "")}
        path, total = found
        steps_th, steps_data = self._instructions(path, from_room, to_room)
        points = []
        # ห้องแบบช่องบริการ: เริ่ม/สิ้นสุดที่หน้าช่อง ไม่เดินทะลุเคาน์เตอร์เข้าไปกลางห้อง
        if from_room and from_room in self.rooms and self.rooms[from_room].get("kind") != "window":
            cx, cy = self.room_center(from_room)
            points.append([self.rooms[from_room]["floor_id"], round(cx, 2), round(cy, 2)])
        for nid, _ in path:
            n = self.nodes[nid]
            points.append([n["floor_id"], n["x"], n["y"]])
        if to_node is None and self.rooms[to_room].get("kind") != "window":
            tx, ty = self.room_center(to_room)
            points.append([self.rooms[to_room]["floor_id"], round(tx, 2), round(ty, 2)])
        return {
            "ok": True,
            "from_room": from_room,
            "to_room": to_room,
            "distance": round(total),
            "minutes": max(1, round(total / 50)),  # ประมาณ 50 ม./นาที (เดินช้า)
            "points": points,
            "floors": list(dict.fromkeys(p[0] for p in points)),
            "steps": steps_th,
            "steps_data": steps_data,  # ขั้นตอนแบบมีโครงสร้าง ให้หน้าเว็บแปลเป็นภาษาอื่นได้
        }

    def zone_name(self, floor_id) -> str:
        f = self.floors.get(floor_id) or {}
        b = self.buildings.get(f.get("building_id")) or {}
        return b.get("name") or f.get("name") or ""

    def _instructions(self, path, from_room, to_room) -> tuple[list[str], list[dict]]:
        data: list[dict] = []
        if from_room in self.rooms:
            data.append({"t": "leave", "name": self.rooms[from_room]["name"]})
        elif path and self.nodes[path[0][0]].get("name"):
            data.append({"t": "start", "name": self.nodes[path[0][0]]["name"]})
        run = 0.0
        for i in range(1, len(path)):
            a = self.nodes[path[i - 1][0]]
            b = self.nodes[path[i][0]]
            kind = path[i - 1][1]
            if a["floor_id"] != b["floor_id"]:
                if run >= 3:
                    data.append({"t": "walk", "m": round(run)})
                run = 0.0
                if kind == "portal":
                    if (self.floors.get(b["floor_id"]) or {}).get("style") == "campus":
                        data.append({"t": "exit", "name": self.zone_name(a["floor_id"])})
                    else:
                        data.append({"t": "enter", "name": self.zone_name(b["floor_id"])})
                else:
                    data.append({"t": "vertical", "via": kind, "floor": self.floors[b["floor_id"]]["name"]})
                continue
            run += math.dist((a["x"], a["y"]), (b["x"], b["y"]))
            if i + 1 < len(path):
                c = self.nodes[path[i + 1][0]]
                if c["floor_id"] != b["floor_id"]:
                    continue
                v1 = (b["x"] - a["x"], b["y"] - a["y"])
                v2 = (c["x"] - b["x"], c["y"] - b["y"])
                n1, n2 = math.hypot(*v1), math.hypot(*v2)
                if n1 < 0.01 or n2 < 0.01:
                    continue
                cross = (v1[0] * v2[1] - v1[1] * v2[0]) / (n1 * n2)
                dot = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
                if dot < 0.7 and run >= 2:  # เลี้ยวมากกว่า ~45 องศา (ไม่บอกช่วงสั้นกว่า 2 ม.)
                    data.append({"t": "walk", "m": max(1, round(run)), "turn": "right" if cross > 0 else "left",
                                 "at": b.get("name")})
                    run = 0.0
        if run >= 3:
            data.append({"t": "walk", "m": round(run)})
        if to_room in self.rooms:
            data.append({"t": "arrive", "name": self.rooms[to_room]["name"]})
        else:
            data.append({"t": "arrive", "name": self.nodes[path[-1][0]].get("name") or "ปลายทาง"})
        return [self._step_th(d) for d in data], data

    def _step_th(self, d: dict) -> str:
        t = d["t"]
        if t == "leave":
            return f"ออกจาก{d['name']}"
        if t == "start":
            return f"เริ่มที่{d['name']}"
        if t == "walk":
            if d.get("turn"):
                side = "ขวา" if d["turn"] == "right" else "ซ้าย"
                return f"เดินตรงไปประมาณ {d['m']} เมตร แล้วเลี้ยว{side}" + (f" ที่{d['at']}" if d.get("at") else "")
            return f"เดินตรงไปประมาณ {d['m']} เมตร"
        if t == "exit":
            return f"ออกจาก{d['name']} ไปทางเดินนอกอาคาร"
        if t == "enter":
            return f"เดินไปเข้า{d['name']}"
        if t == "vertical":
            return f"{self.VERTICAL.get(d['via'], {}).get('label', 'ขึ้น/ลง')}ไป{d['floor']}"
        return f"ถึง{d['name']}"

    def public_doc(self) -> dict:
        """ข้อมูลแผนที่สำหรับฝั่งแสดงผล (ไม่รวมการตั้งค่า HOSxP)"""
        return {
            "version": self.version,
            "buildings": self.doc.get("buildings", []),
            "floors": self.doc.get("floors", []),
            "rooms": self.doc.get("rooms", []),
            "nodes": self.doc.get("nodes", []),
            "edges": self.doc.get("edges", []),
        }

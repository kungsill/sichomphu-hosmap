"""แผนที่ภาพรวมโรงพยาบาล (campus) + ตึกเพิ่มเติม (ระยะ 2)

- campus: ใช้ภาพผังโรงพยาบาล (static/img/campus.jpg 1518×1036 px) เป็นพื้น ≈0.2 ม./px
  ตึกเป็นกล่อง 3 มิติ คลิกแล้วเข้าไปดูโซนข้างใน และมีทางเดินนอกอาคารเชื่อมประตูของแต่ละโซน
- ประตูของโซนกับจุดหน้าตึกบนแผนที่ภาพรวมเชื่อมกันด้วย link_group เดียวกัน (Z_*) → คำนวณเส้นทางข้ามตึกได้
- ตึกใหม่ (ไตเทียม, ห้องคลอด/ผ่าตัด, หอผู้ป่วยใน ชาย/หญิง, จิตเวช) เป็น "ผังเบื้องต้น" ยังไม่มีผังจริง
  ปรับใน Map Builder เมื่อได้ผังจริง
"""
from .seed import rect

CAMPUS_B, CAMPUS_F = "bld_campus", "flr_campus"
K = 0.2  # เมตรต่อพิกเซลของภาพผัง

# ประตูโซนเดิม (จาก seed.py) → กลุ่มเชื่อมกับแผนที่ภาพรวม
ZONE_LINKS = {
    "ent": "Z_OPD",
    "k_ent": "Z_CLINIC", "k_exit": "Z_CLINIC",
    "a_ent": "Z_ARI",
    "d_ent": "Z_DENT",
    "t_ent": "Z_TTM",
}


class Zone:
    """ตัวช่วยสร้างโซน: พิกัดเป็นเมตร (หรือพิกเซล × scale)"""

    def __init__(self, prefix, bid, fid, name, code, w, h, sort, scale=1.0, style=None, plan=None):
        self.p, self.f, self.s = prefix, fid, scale
        self.doc = {
            "buildings": [{"id": bid, "code": code, "name": name, "sort": sort}],
            "floors": [{"id": fid, "building_id": bid, "level": 1, "name": "ชั้น 1" if style != "campus" else "ภาพรวม",
                        "width": round(w * scale, 1), "height": round(h * scale, 1), "plan_image": plan,
                        "plan_opacity": 1.0 if plan else 0.5, "style": style}],
            "rooms": [], "nodes": [], "edges": [], "mapping": [],
        }

    def m(self, v):
        return round(v * self.s, 1)

    def node(self, nid, x, y, kind="corridor", name=None, link=None):
        nid = f"{self.p}_{nid}"
        self.doc["nodes"].append({"id": nid, "floor_id": self.f, "kind": kind, "x": self.m(x), "y": self.m(y),
                                  "name": name, "link_group": link})
        return nid

    def edge(self, a, b, kind="walk"):
        self.doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": kind, "accessible": True})

    def chain(self, ids):
        for a, b in zip(ids, ids[1:]):
            self.edge(a, b)

    def room(self, rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None,
             color=None, link_floor=None):
        x1, y1, x2, y2 = box
        rid = f"{self.p}_{rid}"
        self.doc["rooms"].append({"id": rid, "floor_id": self.f, "code": code, "name": name, "short_name": short,
                                  "kind": kind, "polygon": rect(self.m(x1), self.m(y1), self.m(x2), self.m(y2)),
                                  "door_node_id": door, "capacity": capacity, "seats": seats, "desk": desk,
                                  "color": color, "decor": decor, "link_floor": link_floor})
        return rid

    def map(self, dep, name, room_id, wait, stage, servers=1, avg=5, priority=50, hint=None, default=True, zone=None):
        self.doc["mapping"].append({"id": f"m_{dep}_{hint or room_id}", "depcode": dep, "dep_name": name,
                                    "room_id": room_id, "wait_room_id": wait, "room_hint": hint, "is_default": default,
                                    "stage": stage, "for_main_dep": zone, "priority": priority, "queue_prefix": None,
                                    "servers": servers, "avg_service_min": avg})


# ---------------------------------------------------------------------------- แผนที่ภาพรวม
def campus_document() -> dict:
    z = Zone("c", CAMPUS_B, CAMPUS_F, "ภาพรวมโรงพยาบาล", "CAMPUS", 1518, 1036, 0, scale=K, style="campus",
             plan="/static/img/campus.jpg")

    def bld(rid, name, short, box, color, link=None, door=None, cap=0):
        return z.room(rid, rid.upper(), name, short, "building", box, door, capacity=cap, color=color, link_floor=link)

    # ---- ถนน / ทางเดินนอกอาคาร (พิกัดพิกเซลของภาพผัง)
    gate = z.node("gate", 928, 900, "gate", "ประตูทางเข้าโรงพยาบาล")
    z.chain([gate, z.node("r830", 928, 830, "junction"), z.node("r690", 928, 690, "junction")])
    row = {x: z.node(f"y690_{x}", x, 690, "junction") for x in (785, 814, 890, 1010, 1093, 1130)}
    z.chain([row[785], row[814], row[890], "c_r690", row[1010], row[1093], row[1130]])
    west_col = [row[785], z.node("x785_450", 785, 450), z.node("x785_380", 785, 380, "junction")]
    z.chain(west_col)
    east_col = [row[1130], z.node("x1130_450", 1130, 450), z.node("x1130_380", 1130, 380, "junction")]
    z.chain(east_col)
    diag = ["c_r830", z.node("q845", 845, 770), z.node("q760", 760, 700, "junction"), z.node("q660", 660, 610),
            z.node("q580", 580, 545, "junction"), z.node("q540", 540, 470), z.node("q500", 500, 420)]
    z.chain(diag)
    z.edge("c_q760", row[785])
    wroad = ["c_q580", z.node("w545", 545, 545, "junction"), z.node("w490", 490, 545), z.node("w420", 420, 545),
             z.node("w375", 375, 545), z.node("w333", 333, 545), z.node("w240", 240, 545)]
    z.chain(wroad)
    scol = ["c_w545", z.node("s700", 545, 700), z.node("s770", 545, 770), z.node("s850", 545, 850)]
    z.chain(scol)

    # ---- ตึกที่มีแผนที่ภายใน (ประตูหน้าตึก = portal เชื่อมกับประตูโซน)
    def door(nid, x, y, link, to, name):
        d = z.node(nid, x, y, "portal", name, link)
        z.edge(d, to)
        return d

    d = door("d_opd", 1010, 662, "Z_OPD", row[1010], "หน้าตึก OPD")
    bld("opd", "ตึก OPD (ห้องยา · การเงิน · LAB)", "OPD", (953, 520, 1068, 655), "#4a90d9", "flr_opd_1", d)
    d = door("d_lr", 890, 662, "Z_LR", row[890], "หน้าตึก ER · ห้องคลอด")
    bld("er", "ER · ห้องคลอด · ผ่าตัดเล็ก", "ER · ห้องคลอด", (833, 518, 950, 655), "#e05a9a", "flr_lr_1", d)
    d = door("d_ari", 814, 662, "Z_ARI", row[814], "หน้าตึก ARI")
    bld("ari", "ARI", "ARI", (796, 520, 832, 655), "#c9d3ea", "flr_ari_1", d)
    d = door("d_clinic", 1093, 662, "Z_CLINIC", row[1093], "หน้าคลินิกพิเศษ")
    bld("clinic", "คลินิกพิเศษ", "คลินิกพิเศษ", (1070, 522, 1116, 655), "#b9a7e8", "flr_clinic_1", d)
    d = door("d_ipdm", 798, 450, "Z_IPDM", "c_x785_450", "หน้าตึกผู้ป่วยใน (ชาย)")
    bld("ipdm", "ตึกผู้ป่วยใน (ชาย)", "ผู้ป่วยใน ชาย", (798, 387, 898, 505), "#5cc26c", "flr_ipdm_1", d)
    d = door("d_ipdf", 1070, 450, "Z_IPDF", "c_x1130_450", "หน้าตึกผู้ป่วยใน (หญิง)")
    bld("ipdf", "ตึกผู้ป่วยใน (หญิง)", "ผู้ป่วยใน หญิง", (953, 385, 1070, 512), "#f07ab8", "flr_ipdf_1", d)
    d = door("d_dent", 684, 778, "Z_DENT", z.node("dd", 700, 760), "หน้าตึกทันตกรรม")
    z.edge("c_dd", "c_q760")
    bld("dent", "ตึกทันตกรรม", "ทันตกรรม", (608, 780, 760, 855), "#5cc26c", "flr_dental_1", d)
    d = door("d_ttm", 333, 512, "Z_TTM", "c_w333", "หน้าตึกแผนไทย")
    bld("ttm", "แพทย์แผนไทย", "แผนไทย", (256, 467, 410, 510), "#5cc26c", "flr_thaimed_1", d)
    d = door("d_dial", 487, 422, "Z_DIAL", "c_q540", "หน้าศูนย์ไตเทียม")
    bld("dial", "ศูนย์ไตเทียม", "ไตเทียม", (258, 397, 485, 448), "#f2d14b", "flr_dialysis_1", d)
    d = door("d_psy", 338, 842, "Z_PSY", "c_s850", "หน้าตึกจิตเวช")
    bld("psy", "ตึกจิตเวช", "จิตเวช", (220, 820, 337, 862), "#a78bdb", "flr_psych_1", d)

    # ---- ตึกอื่น (ยังไม่มีแผนที่ภายใน)
    bld("ct", "ห้อง CT Scan", "CT Scan", (857, 477, 915, 520), "#f2d14b")
    bld("genprac", "ตึกเวชปฏิบัติ", "ตึกเวชปฏิบัติ", (235, 590, 515, 692), "#f07ab8")
    bld("old", "อาคารตึกเวชเก่า", "ตึกเวชเก่า", (195, 720, 517, 820), "#4a90d9")
    bld("hall", "หอประชุม", "หอประชุม", (650, 395, 775, 490), "#4a90d9")
    bld("pool", "สระพักน้ำบำบัด", "สระน้ำบำบัด", (597, 283, 770, 395), "#f07ab8")
    bld("canteen", "โรงอาหาร", "โรงอาหาร", (742, 738, 818, 812), "#f2d14b")
    bld("guard", "ป้อมหน้าโรงพยาบาล", "ป้อมยาม", (785, 835, 858, 870), "#f07ab8")
    bld("parkb", "โรงจอดรถ (B)", "ที่จอดรถ B", (838, 705, 1110, 755), "#b0bec5")
    bld("park1", "โรงจอดรถ", "ที่จอดรถ", (1188, 500, 1365, 540), "#4a90d9")
    bld("park2", "โรงจอดรถจักรยานยนต์", "ที่จอดรถ จยย.", (1190, 592, 1380, 630), "#4a90d9")
    return z.doc


# ---------------------------------------------------------------------------- ตึกใหม่ (ผังเบื้องต้น)
def dialysis_document() -> dict:
    z = Zone("dl", "bld_dialysis", "flr_dialysis_1", "ศูนย์ไตเทียม", "DIAL", 40, 26, 8)
    ent = z.node("ent", 0, 13, "entrance", "ทางเข้าศูนย์ไตเทียม", "Z_DIAL")
    sp = {x: z.node(f"s{x}", x, 13, "junction" if x in (6, 18, 27) else "corridor") for x in (6, 18, 24, 27, 34)}
    z.chain([ent] + [sp[x] for x in sorted(sp)])
    d = z.node("d_w", 7, 15, "door"); z.edge(d, sp[6])
    wait = z.room("wait", "DL-W", "ห้องรอศูนย์ไตเทียม", "ห้องรอ", "waiting", (2, 15, 12, 25), d, 30, seats=True)
    d = z.node("d_rec", 7, 11, "door"); z.edge(d, sp[6])
    z.room("rec", "DL-REC", "จุดลงทะเบียนไตเทียม", "ลงทะเบียน", "counter", (2, 1, 12, 11), d, 4, desk="n")
    d = z.node("d_ns", 18, 15, "door"); z.edge(d, sp[18])
    z.room("ns", "DL-NS", "เคาน์เตอร์พยาบาล", "พยาบาล", "counter", (14, 15, 22, 20), d, 4, desk="s")
    d = z.node("d_hall", 24, 11, "door", "ทางเข้าห้องฟอกไต"); z.edge(d, sp[24])
    hall = z.room("hall", "DL-HD", "ห้องฟอกไต (ไตเทียม)", "ห้องฟอกไต", "service", (14, 1, 38, 11), d, 20, decor="beds")
    d = z.node("d_ckd", 27, 15, "door", "หน้าห้องตรวจ CKD"); z.edge(d, sp[27])
    ckd = z.room("ckd", "DL-CKD", "ห้องตรวจคลินิกชะลอไตเสื่อม", "ห้องตรวจ CKD", "service", (24, 15, 31, 25), d, 3, desk="n")
    d = z.node("d_store", 35, 15, "door"); z.edge(d, sp[34])
    z.room("store", "DL-ST", "ห้องเก็บอุปกรณ์", "ห้องเก็บของ", "service", (32, 15, 38, 25), d, 2)
    z.map("031", "คลินิกไตเทียม", hall, wait, "other", servers=12, avg=240, priority=40)
    z.map("184", "คลินิกชะลอไตเสื่อม", ckd, wait, "doctor", servers=1, avg=10)
    return z.doc


def labor_document() -> dict:
    z = Zone("lr", "bld_lr", "flr_lr_1", "ห้องคลอด · ห้องผ่าตัด", "LR", 36, 24, 9)
    ent = z.node("ent", 18, 24, "entrance", "ทางเข้าห้องคลอด · ห้องผ่าตัด", "Z_LR")
    sp = {x: z.node(f"s{x}", x, 12, "junction" if x == 18 else "corridor") for x in (2, 9, 18, 27, 34)}
    z.chain([sp[x] for x in sorted(sp)])
    z.chain([ent, z.node("s18_18", 18, 18), sp[18]])
    d = z.node("d_w", 9, 14, "door"); z.edge(d, sp[9])
    wait = z.room("wait", "LR-W", "ห้องรอญาติ", "ห้องรอญาติ", "waiting", (2, 14, 14, 22), d, 20, seats=True)
    d = z.node("d_ns", 27, 14, "door"); z.edge(d, sp[27])
    z.room("ns", "LR-NS", "เคาน์เตอร์พยาบาล", "พยาบาล", "counter", (22, 14, 34, 22), d, 4, desk="s")
    d = z.node("d_lr", 9, 10, "door", "หน้าห้องคลอด"); z.edge(d, sp[9])
    lr = z.room("lr", "LR-LR", "ห้องคลอด", "ห้องคลอด", "service", (2, 1, 16, 10), d, 6, decor="beds")
    d = z.node("d_or", 27, 10, "door", "หน้าห้องผ่าตัด"); z.edge(d, sp[27])
    orr = z.room("or", "LR-OR", "ห้องผ่าตัด", "ห้องผ่าตัด", "service", (20, 1, 34, 10), d, 3)
    z.map("109", "ห้องคลอด", lr, wait, "other", servers=3, avg=60, priority=10)
    z.map("111", "ห้องผ่าตัด", orr, wait, "other", servers=1, avg=60, priority=10)
    return z.doc


def ward_document(sex: str) -> dict:
    male = sex == "m"
    z = Zone("wm" if male else "wf", f"bld_ipd{sex}", f"flr_ipd{sex}_1",
             f"ตึกผู้ป่วยใน ({'ชาย' if male else 'หญิง'})", f"IPD{sex.upper()}", 44, 22, 10 if male else 11)
    ent = z.node("ent", 0, 11, "entrance", f"ทางเข้าตึกผู้ป่วยใน ({'ชาย' if male else 'หญิง'})", f"Z_IPD{sex.upper()}")
    sp = {x: z.node(f"s{x}", x, 11, "junction" if x in (6, 30) else "corridor") for x in (6, 16, 30, 40)}
    z.chain([ent] + [sp[x] for x in sorted(sp)])
    d = z.node("d_ns", 7, 13, "door"); z.edge(d, sp[6])
    z.room("ns", "IPD-NS", "เคาน์เตอร์พยาบาล", "พยาบาล", "counter", (2, 13, 12, 20), d, 4, desk="s")
    d = z.node("d_w", 7, 9, "door"); z.edge(d, sp[6])
    z.room("wait", "IPD-W", "ห้องรอญาติ", "ห้องรอญาติ", "waiting", (2, 1, 12, 9), d, 16, seats=True)
    d = z.node("d_a", 30, 9, "door", "ทางเข้าหอผู้ป่วย A"); z.edge(d, sp[30])
    ward_a = z.room("ward_a", "IPD-A", "หอผู้ป่วย A", "หอผู้ป่วย A", "service", (14, 1, 42, 9), d, 20, decor="beds")
    d = z.node("d_b", 30, 13, "door", "ทางเข้าหอผู้ป่วย B"); z.edge(d, sp[30])
    z.room("ward_b", "IPD-B", "หอผู้ป่วย B", "หอผู้ป่วย B", "service", (14, 13, 42, 21), d, 20, decor="beds")
    dep = "038" if male else "037"
    z.map(dep, f"ผู้ป่วยใน ({'ชาย' if male else 'หญิง'})", ward_a, ward_a, "other", servers=20, avg=600, priority=5)
    return z.doc


def psych_document() -> dict:
    z = Zone("ps", "bld_psych", "flr_psych_1", "ตึกจิตเวช", "PSY", 30, 20, 12)
    ent = z.node("ent", 15, 20, "entrance", "ทางเข้าตึกจิตเวช", "Z_PSY")
    sp = {x: z.node(f"s{x}", x, 10, "junction" if x == 15 else "corridor") for x in (2, 5.5, 8, 13.5, 15, 22, 28)}
    z.chain([sp[x] for x in sorted(sp)])
    z.chain([ent, z.node("s15_15", 15, 15), sp[15]])
    d = z.node("d_w", 8, 12, "door"); z.edge(d, sp[8])
    wait = z.room("wait", "PS-W", "ห้องรอพบแพทย์ จิตเวช", "รอพบแพทย์", "waiting", (2, 12, 13, 19), d, 20, seats=True)
    d = z.node("d_scr", 22, 12, "door"); z.edge(d, sp[22])
    z.room("scr", "PS-SCR", "จุดคัดกรอง จิตเวช", "คัดกรอง", "counter", (17, 12, 28, 16), d, 3, desk="s")
    ex = []
    for i, (x1, x2, dx) in enumerate(((2, 9, 5.5), (10, 17, 13.5)), start=1):
        d = z.node(f"d_ex{i}", dx, 8, "door", f"หน้าห้องตรวจ {i} (จิตเวช)"); z.edge(d, sp[dx])
        ex.append(z.room(f"ex{i}", f"PS-EX{i}", f"ห้องตรวจจิตเวช {i}", f"ห้องตรวจ {i}", "service", (x1, 1, x2, 8), d, 3, desk="n"))
    d = z.node("d_cs", 23, 8, "door", "หน้าห้องให้คำปรึกษา"); z.edge(d, sp[22])
    z.room("cs", "PS-CS", "ห้องให้คำปรึกษา", "ให้คำปรึกษา", "service", (18, 1, 28, 8), d, 3, desk="n")
    for i, r in enumerate(ex, start=1):
        z.map("185", "คลินิกจิตเวชและยาเสพติด", r, wait, "doctor", servers=2, avg=15, hint=str(i), default=i == 1)
    return z.doc


NEW_ZONES = (campus_document, dialysis_document, labor_document, lambda: ward_document("m"),
             lambda: ward_document("f"), psych_document)


def merge_into(doc: dict) -> dict:
    """เพิ่มแผนที่ภาพรวม + ตึกใหม่ลงในเอกสารแผนที่ (แทนที่ของเดิมถ้ามีอยู่แล้ว) และเชื่อมประตูโซนเดิม"""
    for make in NEW_ZONES:
        z = make()
        fids = {f["id"] for f in z["floors"]}
        old_nodes = {n["id"] for n in doc["nodes"] if n["floor_id"] in fids}
        doc["buildings"] = [b for b in doc["buildings"] if b["id"] not in {x["id"] for x in z["buildings"]}] + z["buildings"]
        doc["floors"] = [f for f in doc["floors"] if f["id"] not in fids] + z["floors"]
        doc["rooms"] = [r for r in doc["rooms"] if r["floor_id"] not in fids] + z["rooms"]
        doc["nodes"] = [n for n in doc["nodes"] if n["floor_id"] not in fids] + z["nodes"]
        doc["edges"] = [e for e in doc["edges"] if e["node_a"] not in old_nodes and e["node_b"] not in old_nodes] + z["edges"]
        codes = {m["depcode"] for m in z["mapping"]}
        doc["mapping"] = [m for m in doc["mapping"] if m["depcode"] not in codes] + z["mapping"]
    for n in doc["nodes"]:
        if n["id"] in ZONE_LINKS:
            n["link_group"] = ZONE_LINKS[n["id"]]
    # ให้แผนที่ภาพรวมอยู่ลำดับแรก
    doc["buildings"].sort(key=lambda b: (b.get("sort") or 0))
    return doc

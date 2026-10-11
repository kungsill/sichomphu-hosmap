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
# ความสูงพื้นที่แผนที่ภาพรวม (พิกเซล): ภาพผังสูง 1036 วางชิดบน ส่วนที่เกินคือพื้นที่นอกภาพ (ถนนทางใต้ ลานจอดรถอำเภอ)
CAMPUS_H = 1560

# ประตูโซนเดิม (จาก seed.py) → กลุ่มเชื่อมกับแผนที่ภาพรวม
ZONE_LINKS = {
    "ent": "Z_OPD",
    "k_ent": "Z_CLINIC", "k_exit": "Z_CLINIC",
    "a_ent": "Z_ARI",
    "d_ent": "Z_DENT",
    "t_ent": "Z_TTM",
    # กายภาพบำบัดอยู่ในตึกเดียวกับทันตกรรม · ส่งเสริมสุขภาพอยู่ในตึกเวชปฏิบัติ
    "p_ent_w": "Z_DENT", "p_ent_s": "Z_DENT",
    "h_ent1": "Z_PROMO", "h_ent2": "Z_PROMO",
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

    def edge(self, a, b, kind="walk"):  # kind: walk / ramp / stairs / road (ถนนหลัก วาดกว้าง)
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
    z = Zone("c", CAMPUS_B, CAMPUS_F, "ภาพรวมโรงพยาบาล", "CAMPUS", 1518, CAMPUS_H, 0, scale=K, style="campus",
             plan=None)  # ภาพผังเดิม: /static/img/campus.jpg (ใส่กลับได้ใน Map Builder)

    def bld(rid, name, short, box, color, link=None, door=None, cap=0):
        return z.room(rid, rid.upper(), name, short, "building", box, door, capacity=cap, color=color, link_floor=link)

    # ---- ถนน / ทางเดินนอกอาคาร (พิกัดพิกเซลของภาพผัง ตามแนวถนนที่โรงพยาบาลกำหนด)
    # kind: road = ถนนนอกรั้ว (วาดกว้าง ไม่ใช้นำทาง) · walk = ถนนในโรงพยาบาล · path = ทางเดินเท้า (วาดเป็นทางเท้า)
    # ถนนหลักหน้าโรงพยาบาล (ไป สีชมพู ↔ ไป ชุมแพ) + ถนนทางใต้ไปลานจอดรถอำเภอ
    gate = z.node("gate", 915, 888, "gate", "ประตูทางเข้าโรงพยาบาล")
    main_j = z.node("main_j", 920, 930, "junction", "ปากทางเข้าโรงพยาบาล")
    main_wj = z.node("main_wj", 568, 930, "junction", "ปากทางเข้าฝั่งตะวันตก")
    south_j = z.node("south_j", 926, 1382, "junction", "ทางเข้าลานจอดรถอำเภอ")
    z.chain([z.node("main_w", 0, 930, "corridor", "ถนนหลัก (ไป สีชมพู)"), main_wj, main_j,
             z.node("main_e", 1518, 930, "corridor", "ถนนหลัก (ไป ชุมแพ)")])
    z.chain([main_j, z.node("south_m", 924, 1150), south_j, z.node("south_e", 928, CAMPUS_H, "corridor", "ถนนทางใต้")])
    for e in z.doc["edges"][-6:]:
        e["kind"] = "road"
    z.edge(gate, main_j)

    # ถนนทแยงสายยาว: จากแนวกำแพงด้านบน ลงมาสามแยกหน้าตึก ER แล้วต่อถึงประตูโรงพยาบาล
    ax = lambda y: round(300 + 0.668 * (y + 5))  # noqa: E731  แนวกึ่งกลางถนน
    ja = z.node("ja", 771, 700, "junction", "สามแยกหน้าตึก ER")
    a178 = z.node("a178", ax(178), 178, "junction")
    a322 = z.node("a322", ax(322), 322, "junction")
    z.chain([z.node("a_top", 300, 0, "corridor", "ถนนด้านบน"), a178, a322, z.node("a465", ax(465), 465),
             z.node("a560", ax(560), 560), ja])
    z.chain([ja, z.node("e780", 832, 780), z.node("e845", 882, 845), gate])

    # ถนนหน้าตึก OPD → ถนนฝั่งตะวันออก (ขึ้นเหนือถึงบ้านพัก) + แยกเข้าด้านหลังตึกผู้ป่วยในหญิง
    row = {x: z.node(f"y690_{x}", x, 690, "junction") for x in (814, 890, 1010, 1093, 1128)}
    z.chain([ja, row[814], row[890], row[1010], row[1093], row[1128]])
    x388 = z.node("x1130_388", 1128, 388, "junction")
    z.chain([row[1128], z.node("x1130_450", 1128, 450), x388, z.node("x1130_215", 1128, 215)])
    z.edge(x388, z.node("x1075_388", 1075, 388))

    # ถนนฝั่งตะวันตก: แยกจากถนนทแยง ลงมาถึงทางเข้าฝั่งตะวันตก
    wj = z.node("wj", 541, 578, "junction")
    s748 = z.node("s748", 560, 748, "junction")
    z.chain([a322, z.node("wr420", 510, 420), z.node("wr490", 523, 490), wj, z.node("s640", 550, 640), s748,
             z.node("s850", 566, 846, "junction"), main_wj])
    # ถนนเชื่อมถนนฝั่งตะวันตก → สามแยกหน้าตึก ER (ผ่านหน้าตึกทันตกรรม)
    c690 = z.node("c690", 690, 722, "junction")
    z.chain([s748, c690, ja])
    # ถนนเข้าตึกจิตเวช
    z.edge("c_s850", z.node("psy_r", 345, 846))
    # ถนนลานจอดรถ (หน้าแผนไทย / ตึกเวชปฏิบัติ)
    z.chain([wj, z.node("p578", 490, 578), z.node("p548", 432, 548), z.node("w375", 375, 541, "junction"),
             z.node("w333", 333, 540, "junction"), z.node("w240", 235, 540)])
    # ถนนในเขตบ้านพัก (บน · ซ้าย · ล่าง)
    h178, h328 = z.node("h178", 48, 178, "junction"), z.node("h328", 48, 328, "junction")
    z.chain([a178, z.node("h178m", 230, 178), h178, h328, z.node("h328m", 280, 328), a322])

    # ทางเดินเท้า (ไม่ใช่ถนน): ข้าง ARI ขึ้นไปตึกผู้ป่วยในชาย · หน้าตึกทันตกรรม
    for a_, b_ in ((row[814], z.node("x785_600", 790, 600)), ("c_x785_600", z.node("x785_450", 790, 450))):
        z.edge(a_, b_, "path")

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
    d = door("d_dent", 684, 778, "Z_DENT", c690, "หน้าตึกทันตกรรม")
    bld("dent", "ตึกทันตกรรม · กายภาพบำบัด", "ทันตกรรม · กายภาพ", (608, 780, 760, 855), "#5cc26c", "flr_dental_1", d)
    d = door("d_ttm", 333, 512, "Z_TTM", "c_w333", "หน้าตึกแผนไทย")
    bld("ttm", "แพทย์แผนไทย", "แผนไทย", (256, 467, 410, 510), "#5cc26c", "flr_thaimed_1", d)
    d = door("d_dial", 487, 422, "Z_DIAL", "c_wr420", "หน้าศูนย์ไตเทียม")
    bld("dial", "ศูนย์ไตเทียม", "ไตเทียม", (258, 397, 485, 448), "#f2d14b", "flr_dialysis_1", d)
    d = door("d_psy", 338, 842, "Z_PSY", "c_psy_r", "หน้าตึกจิตเวช")
    bld("psy", "ตึกจิตเวช", "จิตเวช", (220, 820, 337, 862), "#a78bdb", "flr_psych_1", d)

    d = door("d_promo", 375, 592, "Z_PROMO", "c_w375", "หน้าตึกเวชปฏิบัติ (ส่งเสริมสุขภาพ)")
    bld("genprac", "ตึกเวชปฏิบัติ · ส่งเสริมสุขภาพ", "เวชปฏิบัติ · ส่งเสริม", (235, 590, 515, 692), "#f07ab8", "flr_promo_1", d)

    # ---- ตึกอื่น (ยังไม่มีแผนที่ภายใน)
    bld("ct", "ห้อง CT Scan", "CT Scan", (857, 477, 915, 520), "#f2d14b")

    bld("old", "อาคารตึกเวชเก่า", "ตึกเวชเก่า", (195, 720, 517, 820), "#4a90d9")
    bld("hall", "หอประชุม", "หอประชุม", (650, 395, 775, 490), "#4a90d9")

    # ---- อาคารอื่นตามผังเดิม (ไม่ใช่จุดบริการผู้ป่วย) · quiet = ไม่แสดงป้ายชื่อ กันป้ายรก (ชี้เมาส์ยังเห็นชื่อ)
    PINK, BLUE, YEL, GRN, PUR, ORG, WHT = "#f07ab8", "#4a90d9", "#f2d14b", "#5cc26c", "#a78bdb", "#f5a35c", "#e3e8ea"
    others = [
        ("store", "อาคารเก็บวัสดุ", (92, 108, 210, 160), BLUE, False), ("store2", "โรงเก็บของ", (42, 102, 80, 160), BLUE, True),
        ("h1", "บ้านพัก", (82, 198, 160, 242), PINK, True), ("h2", "บ้านพัก", (177, 198, 253, 242), PINK, True),
        ("h3", "บ้านพัก", (270, 198, 345, 242), PINK, True), ("h4", "บ้านพัก", (80, 250, 163, 298), PINK, True),
        ("h5", "บ้านพัก", (190, 250, 275, 298), PINK, True), ("h6", "บ้านพัก", (292, 250, 375, 298), PINK, True),
        ("h7", "บ้านพัก", (77, 350, 162, 392), PINK, True), ("h8", "บ้านพัก", (178, 362, 228, 395), PINK, True),
        ("h9", "บ้านพัก", (242, 350, 322, 392), PINK, True), ("h10", "บ้านพัก", (343, 350, 423, 392), PINK, True),
        ("flat", "แฟลตบ้านพัก", (40, 405, 225, 480), PUR, False), ("flat6", "แฟลต 6 ชั้น", (40, 555, 170, 640), YEL, False),
        ("pchr", "ห้องพักพชร", (547, 456, 588, 504), PINK, True), ("maint", "อาคารซ่อมบำรุง", (562, 528, 628, 598), YEL, True),
        ("power", "โรงปั่นไฟ", (580, 606, 645, 650), BLUE, True), ("water", "ประปา", (588, 654, 636, 700), WHT, True),
        ("wc", "ห้องน้ำ", (752, 582, 790, 640), PINK, True),
        ("supply", "อาคารพัสดุ", (795, 210, 890, 290), BLUE, False), ("sew", "ตัดเย็บ", (905, 185, 965, 225), YEL, True),
        ("wc2", "ห้องน้ำ", (975, 185, 1035, 225), BLUE, True), ("fitness", "ฟิตเนส", (995, 105, 1110, 192), PINK, False),
        ("laundry", "โรงซัก", (860, 300, 920, 350), BLUE, True), ("b_a", "ทันตกรรมเก่า / ห้องพัก", (930, 270, 985, 360), PINK, True),
        ("b_b", "คลังยา / พัสดุ", (990, 270, 1040, 360), GRN, True), ("b_c", "IT / งานไฟฟ้า", (1045, 270, 1100, 360), ORG, True),
        ("o2", "ถังออกซิเจน", (1068, 410, 1106, 452), WHT, True),
        ("staff_e", "บ้านพัก (ตึกยาว)", (1155, 178, 1215, 350), BLUE, False),
        ("flat_e", "แฟลตบ้านพัก", (1380, 300, 1468, 460), GRN, False),
        ("e1", "บ้านพัก", (1155, 372, 1230, 420), PINK, True), ("e2", "บ้านพัก", (1262, 372, 1335, 420), PINK, True),
        ("e3", "บ้านพัก", (1165, 430, 1215, 470), PINK, True), ("e4", "บ้านพัก", (1222, 430, 1272, 470), PINK, True),
        ("e5", "บ้านพัก", (1278, 430, 1328, 470), PINK, True), ("e6", "บ้านพัก", (1332, 430, 1382, 470), PINK, True),
        ("e7", "บ้านพัก", (1398, 472, 1455, 528), PINK, True),
        ("director", "บ้านพักผู้อำนวยการ", (1190, 645, 1278, 695), PINK, False),
    ]
    for rid, name, box, color, quiet in others:
        bld(rid, name, name, box, color)
        if quiet:
            z.doc["rooms"][-1]["decor"] = "quiet"
    # ที่ว่าการอำเภอสีชมพู (ถัดจากสนามฟุตบอลกลาง ฝั่งถนนหลัก)
    bld("amphoe", "ที่ว่าการอำเภอสีชมพู", "ที่ว่าการอำเภอ", (130, 1050, 410, 1215), "#4a90d9")
    # สนามกีฬา (วาดแบบสนามบนพื้น)
    bld("court", "สนามกีฬา", "สนามกีฬา", (1228, 228, 1330, 338), "#b0bec5")
    z.doc["rooms"][-1]["decor"] = "field"

    # ---- ของตกแต่ง (วาดเป็นรูป 3 มิติ ไม่ใช่ตึก)
    for rid, name, box, decor in (("buddha", "พระพุทธรูป", (936, 815, 976, 858), "buddha"),
                                  ("flag", "เสาธง", (985, 772, 1041, 828), "flag")):
        bld(rid, name, name, box, "#f2d14b")
        z.doc["rooms"][-1]["decor"] = decor
    # ลานจอดรถ / สนามฟุตบอล (วาดบนพื้น มีรถจอด · เส้นสนาม)
    for rid, name, box, decor in (("park_dial", "ลานจอดรถ (ไตเทียม · แผนไทย)", (405, 455, 497, 528), "parking"),
                                  ("park_amphoe", "ลานจอดรถ อำเภอสีชมพู", (428, 980, 890, 1556), "parking"),
                                  ("field", "สนามฟุตบอลกลาง", (110, 1262, 430, 1492), "field"),
                                  ("carport", "โรงจอดรถ", (846, 716, 1104, 758), "carport")):
        bld(rid, name, name, box, "#b0bec5")
        z.doc["rooms"][-1]["decor"] = decor
    bld("sign", "ป้ายโรงพยาบาลสีชมพู", "โรงพยาบาลสีชมพู", (785, 835, 858, 870), "#f07ab8")
    z.doc["rooms"][-1]["decor"] = "sign"  # วาดเป็นป้ายชื่อ ไม่ใช่ตึก
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

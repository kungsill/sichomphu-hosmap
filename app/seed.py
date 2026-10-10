"""แผนที่ตัวอย่าง (จำลอง) สำหรับเริ่มต้นใช้งาน — ไม่ใช่แผนผังจริงของโรงพยาบาล
ให้แก้ไข/วาดใหม่ผ่าน Map Builder หลังสำรวจอาคารจริง"""
import sqlalchemy as sa

from . import config, db, mapdata


def rect(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def demo_document() -> dict:
    B = "bld_opd"
    F1, F2 = "flr_opd_1", "flr_opd_2"
    doc = {
        "buildings": [{"id": B, "code": "OPD", "name": "อาคารผู้ป่วยนอก", "sort": 1}],
        "floors": [
            {"id": F1, "building_id": B, "level": 1, "name": "ชั้น 1", "width": 64, "height": 44, "plan_image": None, "plan_opacity": 0.5},
            {"id": F2, "building_id": B, "level": 2, "name": "ชั้น 2", "width": 64, "height": 44, "plan_image": None, "plan_opacity": 0.5},
        ],
        "rooms": [], "nodes": [], "edges": [], "mapping": [],
    }
    nodes, edges, rooms = doc["nodes"], doc["edges"], doc["rooms"]

    def node(nid, floor, x, y, kind="corridor", name=None, link=None):
        nodes.append({"id": nid, "floor_id": floor, "kind": kind, "x": x, "y": y, "name": name, "link_group": link})
        return nid

    def edge(a, b, kind="walk"):
        edges.append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": kind, "accessible": kind != "stairs"})

    def room(rid, floor, code, name, short, kind, poly, door, capacity=20, seats=False, desk=None, color=None):
        rooms.append({"id": rid, "floor_id": floor, "code": code, "name": name, "short_name": short, "kind": kind,
                      "polygon": poly, "door_node_id": door, "capacity": capacity, "seats": seats, "desk": desk,
                      "color": color})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    # ------------------------------------------------------------------ ชั้น 1
    exam_x = [31.4, 38.2, 45.0, 51.8, 58.6]
    spine = {}
    for x in sorted({4, 8, 9, 21, 22, 34, 46, 57, 60} | set(exam_x)):
        spine[x] = node(f"n1_c{str(x).replace('.', '_')}", F1, x, 21.5, "junction" if x in (9, 22, 34, 45.0, 46, 57) else "corridor")
    chain([spine[x] for x in sorted(spine)])

    # เวชระเบียน / คัดกรอง
    node("n1_reg_w", F1, 9, 19, "door", "ทางเข้าจุดรอเวชระเบียน"); edge(spine[9], "n1_reg_w")
    node("n1_reg_c", F1, 9, 11, "door"); edge("n1_reg_w", "n1_reg_c")
    node("n1_scr_w", F1, 22, 19, "door", "ทางเข้าจุดรอคัดกรอง"); edge(spine[22], "n1_scr_w")
    node("n1_scr_c", F1, 22, 10, "door"); edge("n1_scr_w", "n1_scr_c")
    room("r_reg", F1, "REG", "เวชระเบียน", "เวชระเบียน", "counter", rect(2, 2, 16, 10), "n1_reg_c", 6, desk="n")
    room("r_reg_wait", F1, "REG-W", "จุดรอเวชระเบียน", "รอเวชระเบียน", "waiting", rect(2, 10, 16, 19), "n1_reg_w", 30, seats=True)
    room("r_scr", F1, "SCR", "จุดคัดกรอง", "คัดกรอง", "counter", rect(17, 2, 27, 9), "n1_scr_c", 4, desk="n")
    room("r_scr_wait", F1, "SCR-W", "จุดรอคัดกรอง", "รอคัดกรอง", "waiting", rect(17, 9, 27, 19), "n1_scr_w", 24, seats=True)

    # ห้องตรวจแพทย์ 1–5 + พื้นที่นั่งรอหน้าห้องตรวจ
    node("n1_exw", F1, 45, 19, "door", "ทางเข้าจุดรอหน้าห้องตรวจ"); edge(spine[45.0], "n1_exw")
    aisle = []
    for i, x in enumerate(exam_x, start=1):
        a = node(f"n1_ea{i}", F1, x, 11.6, "corridor")
        aisle.append(a)
        d = node(f"n1_ex{i}", F1, x, 10, "door", f"หน้าห้องตรวจ {i}")
        edge(a, d)
        room(f"r_exam{i}", F1, f"EX{i}", f"ห้องตรวจ {i}", f"ห้องตรวจ {i}", "service",
             rect(28 + (i - 1) * 6.8, 2, 28 + i * 6.8, 10), d, 4, desk="n")
    chain(aisle)
    edge("n1_ea3", "n1_exw")
    room("r_exam_wait", F1, "EX-W", "จุดรอหน้าห้องตรวจ", "รอพบแพทย์", "waiting", rect(28, 10, 62, 19), "n1_exw", 70, seats=True)

    # LAB / X-ray
    node("n1_lab_w", F1, 8, 24, "door", "ทางเข้าจุดรอ LAB"); edge(spine[8], "n1_lab_w")
    node("n1_lab", F1, 8, 31, "door", "หน้าห้อง LAB"); edge("n1_lab_w", "n1_lab")
    room("r_lab_wait", F1, "LAB-W", "จุดรอห้องปฏิบัติการ", "รอ LAB", "waiting", rect(2, 24, 14, 31), "n1_lab_w", 20, seats=True)
    room("r_lab", F1, "LAB", "ห้องปฏิบัติการ (LAB)", "LAB", "service", rect(2, 31, 14, 42), "n1_lab", 6, desk="s")
    node("n1_xr_w", F1, 21, 24, "door", "ทางเข้าจุดรอ X-ray"); edge(spine[21], "n1_xr_w")
    node("n1_xr", F1, 21, 31, "door", "หน้าห้อง X-ray"); edge("n1_xr_w", "n1_xr")
    room("r_xray_wait", F1, "XR-W", "จุดรอรังสีวิทยา", "รอ X-ray", "waiting", rect(15, 24, 27, 31), "n1_xr_w", 16, seats=True)
    room("r_xray", F1, "XRAY", "รังสีวิทยา (X-ray)", "X-ray", "service", rect(15, 31, 27, 42), "n1_xr", 3, desk="s")

    # โถงทางเข้า ลิฟต์ บันได
    node("n1_ent", F1, 34, 42, "entrance", "ประตูทางเข้าหลัก")
    node("n1_lobby_s", F1, 34, 35, "junction", "โถงทางเข้า")
    node("n1_lobby_n", F1, 34, 27.5, "junction", "หน้าลิฟต์")
    node("n1_lift", F1, 30, 27.5, "elevator", "ลิฟต์", "LIFT_A")
    node("n1_stair", F1, 38.5, 27.5, "stairs", "บันได", "STAIR_A")
    chain(["n1_ent", "n1_lobby_s", "n1_lobby_n", spine[34]])
    edge("n1_lobby_n", "n1_lift")
    edge("n1_lobby_n", "n1_stair")
    room("r_lobby", F1, "LOBBY", "โถงทางเข้า", "โถง", "corridor", rect(28, 24, 40, 42), "n1_lobby_s", 40)
    room("r_corr1", F1, "CORR1", "ทางเดินหลัก", "ทางเดิน", "corridor", rect(2, 19, 62, 24), spine[34], 60)

    # การเงิน / ห้องยา
    node("n1_fin_w", F1, 46, 24, "door", "ทางเข้าจุดรอการเงิน"); edge(spine[46], "n1_fin_w")
    node("n1_fin", F1, 46, 33.5, "door"); edge("n1_fin_w", "n1_fin")
    room("r_fin_wait", F1, "FIN-W", "จุดรอการเงิน", "รอการเงิน", "waiting", rect(41, 24, 51, 34), "n1_fin_w", 24, seats=True)
    room("r_fin", F1, "FIN", "การเงิน", "การเงิน", "counter", rect(41, 34, 51, 42), "n1_fin", 4, desk="s")
    node("n1_ph_w", F1, 57, 24, "door", "ทางเข้าจุดรอรับยา"); edge(spine[57], "n1_ph_w")
    node("n1_ph", F1, 57, 33.5, "door"); edge("n1_ph_w", "n1_ph")
    room("r_ph_wait", F1, "PH-W", "จุดรอรับยา", "รอรับยา", "waiting", rect(52, 24, 62, 34), "n1_ph_w", 30, seats=True)
    room("r_ph", F1, "PHARM", "ห้องยา", "ห้องยา", "counter", rect(52, 34, 62, 42), "n1_ph", 6, desk="s")

    # ------------------------------------------------------------------ ชั้น 2
    s2 = {x: node(f"n2_c{x}", F2, x, 21.5, "junction" if x in (11, 34, 51) else "corridor") for x in (4, 11, 22, 34, 45, 51, 60)}
    chain([s2[x] for x in sorted(s2)])
    node("n2_lobby_n", F2, 34, 27.5, "junction", "หน้าลิฟต์ ชั้น 2"); edge(s2[34], "n2_lobby_n")
    node("n2_lift", F2, 30, 27.5, "elevator", "ลิฟต์", "LIFT_A"); edge("n2_lobby_n", "n2_lift")
    node("n2_stair", F2, 38.5, 27.5, "stairs", "บันได", "STAIR_A"); edge("n2_lobby_n", "n2_stair")
    room("r2_lobby", F2, "LOBBY2", "โถงลิฟต์ ชั้น 2", "โถงลิฟต์", "corridor", rect(28, 24, 40, 34), "n2_lobby_n", 20)
    room("r2_corr", F2, "CORR2", "ทางเดิน ชั้น 2", "ทางเดิน", "corridor", rect(2, 19, 62, 24), s2[34], 40)
    node("n2_pt", F2, 11, 19, "door", "หน้าห้องกายภาพบำบัด"); edge(s2[11], "n2_pt")
    room("r2_pt", F2, "PT", "กายภาพบำบัด", "กายภาพ", "service", rect(2, 2, 20, 19), "n2_pt", 10, desk="n")
    node("n2_den_w", F2, 51, 19, "door", "ทางเข้าจุดรอทันตกรรม"); edge(s2[51], "n2_den_w")
    node("n2_den", F2, 51, 12, "door", "หน้าห้องทันตกรรม"); edge("n2_den_w", "n2_den")
    room("r2_den_wait", F2, "DEN-W", "จุดรอทันตกรรม", "รอทันตกรรม", "waiting", rect(40, 12, 62, 19), "n2_den_w", 20, seats=True)
    room("r2_den", F2, "DENT", "ทันตกรรม", "ทันตกรรม", "service", rect(40, 2, 62, 12), "n2_den", 4, desk="n")

    # ------------------------------------------------------------------ จับคู่รหัส HOSxP (รหัสสมมติ ต้องแทนด้วยรหัสจริง)
    def mp(dep, name, room_id, wait, stage, prefix=None, servers=1, avg=5, priority=50, hint=None, default=True):
        doc["mapping"].append({"id": f"m_{dep}_{hint or 0}", "depcode": dep, "dep_name": name, "room_id": room_id,
                               "wait_room_id": wait, "room_hint": hint, "is_default": default, "stage": stage,
                               "priority": priority, "queue_prefix": prefix, "servers": servers, "avg_service_min": avg})

    mp("001", "เวชระเบียน", "r_reg", "r_reg_wait", "register", servers=3, avg=3)
    mp("002", "คัดกรอง", "r_scr", "r_scr_wait", "screening", servers=3, avg=3)
    mp("010", "อายุรกรรม", "r_exam1", "r_exam_wait", "doctor", "A", servers=2, avg=7, hint="1")
    mp("010", "อายุรกรรม", "r_exam2", "r_exam_wait", "doctor", "A", servers=2, avg=7, hint="2", default=False)
    mp("012", "กุมารเวชกรรม", "r_exam3", "r_exam_wait", "doctor", "K", avg=6)
    mp("013", "ศัลยกรรม", "r_exam4", "r_exam_wait", "doctor", "S", avg=8)
    mp("014", "ศัลยกรรมกระดูกและข้อ", "r_exam5", "r_exam_wait", "doctor", "O", avg=8)
    mp("020", "ห้องปฏิบัติการ (LAB)", "r_lab", "r_lab_wait", "lab", servers=2, avg=4, priority=10)
    mp("021", "รังสีวิทยา (X-ray)", "r_xray", "r_xray_wait", "xray", avg=5, priority=20)
    mp("030", "การเงิน", "r_fin", "r_fin_wait", "finance", servers=2, avg=3, priority=60)
    mp("031", "ห้องยา", "r_ph", "r_ph_wait", "pharmacy", servers=3, avg=4, priority=70)
    mp("040", "ทันตกรรม", "r2_den", "r2_den_wait", "doctor", "D", avg=12)
    mp("041", "กายภาพบำบัด", "r2_pt", "r2_pt", "other", "P", servers=2, avg=15, priority=30)
    return doc


def sichomphu_opd_document() -> dict:
    """โซน OPD โรงพยาบาลสีชมพู — วาดจากผังร่างที่ได้รับ (ภาพ 927×799 px)
    แปลงพิกัดภาพเป็นเมตรประมาณ 0.08 ม./px (ผังร่างไม่ได้วัดจริง ปรับขนาดได้ใน Map Builder)"""
    K, OX, OY = 0.08, 75, 48

    def m(v, o):
        return round((v - o) * K, 1)

    def R(x1, y1, x2, y2):
        return rect(m(x1, OX), m(y1, OY), m(x2, OX), m(y2, OY))

    B, F = "bld_opd", "flr_opd_1"
    doc = {
        "buildings": [{"id": B, "code": "OPD", "name": "โซน OPD", "sort": 1}],
        "floors": [{"id": F, "building_id": B, "level": 1, "name": "ชั้น 1", "width": m(805, OX), "height": m(750, OY),
                    "plan_image": None, "plan_opacity": 0.5}],
        "rooms": [], "nodes": [], "edges": [], "mapping": [],
    }

    def node(nid, x, y, kind="corridor", name=None, link=None):
        doc["nodes"].append({"id": nid, "floor_id": F, "kind": kind, "x": m(x, OX), "y": m(y, OY), "name": name, "link_group": link})
        return nid

    def edge(a, b):
        doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": "walk", "accessible": True})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    def room(rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None):
        doc["rooms"].append({"id": rid, "floor_id": F, "code": code, "name": name, "short_name": short, "kind": kind,
                             "polygon": R(*box), "door_node_id": door, "capacity": capacity, "seats": seats, "desk": desk,
                             "color": None, "decor": decor})

    # ---------------- ทางเดินหลัก (พิกัดเป็น px ของภาพร่าง)
    A = {x: node(f"a{x}", x, 222, "junction" if x in (220, 260, 646) else "corridor")
         for x in (95, 115, 170, 220, 260, 300, 420, 442, 555, 646, 785)}
    chain([A[x] for x in sorted(A)])
    L = [A[220], node("l390", 220, 390), node("l512", 220, 512, "junction")]  # ทางเดินซ้าย
    chain(L)
    M = [A[260], node("m311", 260, 311), node("m368", 260, 368), node("m425", 260, 425), node("m474", 260, 474, "junction")]
    chain(M)
    RR = [A[646], node("r332", 646, 332), node("r370", 646, 370), node("r474", 646, 474, "junction"), node("r512", 646, 512, "junction")]
    chain(RR)
    B1 = [M[-1]] + [node(f"b{x}", x, 474) for x in (398, 447, 463, 541)] + [RR[3]]   # ใต้ห้องรอพบแพทย์
    chain(B1)
    B2 = [L[-1], node("c246", 246, 512, "junction"), node("c271", 271, 512), node("c288", 288, 512)]
    B2 += [node(f"c{x}", x, 512) for x in (327, 365, 404, 442, 481, 520, 559, 597, 628)] + [RR[4]]
    chain(B2)
    edge(M[-1], "c271")

    # ทางเข้า-ออก: ฝั่ง ER / จุดคัดกรอง (ทางเดินระหว่าง ER กับจุดคัดกรอง ออกทางทิศตะวันตก)
    edge(node("ent", 75, 222, "entrance", "ทางเข้า-ออก (ฝั่ง ER / จุดคัดกรอง)"), A[95])

    # ---------------- โซนบน: ER / หัตถการ / X-ray
    d_er = node("d_er", 300, 202, "door", "หน้า ER"); edge(A[300], d_er)
    room("r_er", "ER", "ห้องฉุกเฉิน (ER)", "ER", "service", (154, 68, 410, 202), d_er, 15)
    d_erw = node("d_erw", 420, 157, "door", "หน้าจุดรอ ER"); edge(A[420], d_erw)
    room("r_er_wait", "ER-W", "จุดรอพบแพทย์ ER", "รอ ER", "waiting", (410, 68, 431, 157), d_erw, 8, seats=True)
    d_proc = node("d_proc", 453, 110, "door", "หน้าห้องหัตถการ")
    chain([A[442], node("p442", 442, 110), d_proc])
    room("r_proc", "PROC", "ห้องหัตถการ", "หัตถการ", "service", (453, 68, 657, 135), d_proc, 6)
    d_xr = node("d_xr", 555, 202, "door", "หน้าห้อง X-ray"); edge(A[555], d_xr)
    room("r_xray", "XRAY", "ห้องเอกซ์เรย์ (X-RAY)", "X-RAY", "service", (453, 135, 657, 202), d_xr, 4, desk="n")

    # ---------------- โซนซ้าย: รอ / คัดกรอง / เปิดบัตรคิว / ซักประวัติ
    d_lw = node("d_lw", 115, 242, "door"); edge(A[115], d_lw)
    room("r_left_wait", "W-L", "จุดรอคัดกรอง", "รอคัดกรอง", "waiting", (95, 242, 136, 339), d_lw, 12, seats=True)
    d_scr = node("d_scr", 170, 242, "door", "หน้าจุดคัดกรอง"); edge(A[170], d_scr)
    room("r_screen", "SCR", "จุดคัดกรอง", "คัดกรอง", "counter", (154, 242, 185, 339), d_scr, 4, desk="e")
    d_q = node("d_q", 208, 390, "door", "หน้าจุดเปิดบัตรคิว"); edge("l390", d_q)
    room("r_queue", "QUE", "เปิดบัตรคิว", "บัตรคิว", "counter", (178, 362, 208, 418), d_q, 4, desk="w")
    for i, (y1, y2, ny) in enumerate(((283, 340, "m311"), (340, 397, "m368"), (397, 454, "m425")), start=1):
        d = node(f"d_hx{i}", 251, (y1 + y2) / 2, "door", f"หน้าซักประวัติ {i}"); edge(ny, d)
        room(f"r_hx{i}", f"HX{i}", f"ซักประวัติ {i}", f"ซักประวัติ {i}", "service", (232, y1, 251, y2), d, 2, desk="w")

    # ---------------- ห้องรอพบแพทย์ (กลาง)
    d_bw1 = node("d_bw1", 269, 425, "door", "ทางเข้าห้องรอพบแพทย์"); edge("m425", d_bw1)
    d_bw2 = node("d_bw2", 447, 465, "door"); edge("b447", d_bw2)
    edge(d_bw1, d_bw2)
    room("r_main_wait", "W-OPD", "ห้องรอพบแพทย์", "รอพบแพทย์", "waiting", (269, 276, 625, 465), d_bw2, 120, seats=True)
    for i, (x1, x2, nx) in enumerate(((366, 431, "b398"), (431, 495, "b463"), (495, 588, "b541")), start=4):
        d = node(f"d_post{i}", (x1 + x2) / 2, 483, "door"); edge(nx, d)
        room(f"r_post{i}", f"POST{i}", f"หลังตรวจ {i}", f"หลังตรวจ {i}", "counter", (x1, 483, x2, 503), d, 4, desk="s")

    # ---------------- ห้องตรวจ 1–4 + จุดรอหน้าห้อง + LAB
    for i, (x1, x2, dx, sx) in enumerate(((280, 357, 327, 288), (357, 434, 404, 365), (434, 512, 481, 442), (512, 589, 559, 520)), start=1):
        d = node(f"d_ex{i}", dx, 604, "door", f"หน้าห้องตรวจ {i}"); edge(f"c{dx}", d)
        room(f"r_ex{i}", f"EX{i}", f"ห้องตรวจ {i}", f"ห้องตรวจ {i}", "service", (x1, 604, x2, 690), d, 3, desk="s")
        dw = node(f"d_exw{i}", sx, 520, "door"); edge(f"c{sx}", dw)
        room(f"r_exw{i}", f"EXW{i}", f"จุดรอหน้าห้องตรวจ {i}", f"รอห้อง {i}", "waiting", (x1, 520, x1 + 17, 604), dw, 6, seats=True)
    d_w5 = node("d_exw5", 597, 520, "door"); edge("c597", d_w5)
    room("r_labw", "LAB-W", "จุดรอ LAB", "รอ LAB", "waiting", (589, 520, 606, 604), d_w5, 6, seats=True)
    d_lab = node("d_lab", 628, 604, "door", "หน้าห้อง LAB"); edge("c628", d_lab)
    room("r_lab", "LAB", "ห้องปฏิบัติการ (LAB)", "LAB", "service", (589, 604, 785, 690), d_lab, 8, desk="s")

    # ---------------- ห้องบัตร / ห้องตรวจ 9
    d_w9 = node("d_exw9", 271, 605, "door"); edge("c271", d_w9)
    room("r_exw9", "EXW9", "จุดรอหน้าห้องตรวจ 9", "รอห้อง 9", "waiting", (262, 605, 280, 690), d_w9, 6, seats=True)
    d_card = node("d_card", 231, 626, "door", "หน้าห้องบัตร")
    d_ex9 = node("d_ex9", 231, 700, "door", "หน้าห้องตรวจ 9")
    chain(["c246", node("k626", 246, 626), node("k700", 246, 700)])
    edge("k626", d_card); edge("k700", d_ex9)
    room("r_card", "CARD", "ห้องบัตร", "ห้องบัตร", "counter", (154, 605, 231, 647), d_card, 6, desk="w")
    room("r_ex9", "EX9", "ห้องตรวจ 9 (เปิดเสริม)", "ห้องตรวจ 9", "service", (154, 647, 231, 730), d_ex9, 3, desk="w")

    # ---------------- ห้องเก็บเงิน / ห้องยา
    d_fin = node("d_fin", 667, 332, "door", "หน้าห้องเก็บเงิน"); edge("r332", d_fin)
    room("r_fin", "FIN", "ห้องเก็บเงิน", "เก็บเงิน", "window", (667, 302, 785, 362), d_fin, 6, desk="w", decor="cashier")
    d_ph = node("d_ph", 667, 474, "door", "หน้าห้องยา"); edge("r474", d_ph)
    room("r_ph", "PHARM", "ห้องยา", "ห้องยา", "window", (667, 362, 785, 604), d_ph, 10, desk="w", decor="pharmacy")

    # ---------------- จับคู่รหัส HOSxP (จากตาราง kskdepartment ของ รพ.)
    def mp(dep, name, room_id, wait, stage, prefix=None, servers=1, avg=5, priority=50, hint=None, default=True):
        doc["mapping"].append({"id": f"m_{dep}_{hint or room_id}", "depcode": dep, "dep_name": name, "room_id": room_id,
                               "wait_room_id": wait, "room_hint": hint, "is_default": default, "stage": stage,
                               "priority": priority, "queue_prefix": prefix, "servers": servers, "avg_service_min": avg})

    W = "r_main_wait"
    mp("144", "ซักประวัติ OPD", "r_hx1", W, "screening", "A", servers=3, avg=4, hint="1")
    mp("144", "ซักประวัติ OPD", "r_hx2", W, "screening", "A", servers=3, avg=4, hint="2", default=False)
    mp("144", "ซักประวัติ OPD", "r_hx3", W, "screening", "A", servers=3, avg=4, hint="3", default=False)
    for i in range(1, 5):
        mp("138", "ห้องตรวจอายุรกรรม", f"r_ex{i}", W, "doctor", "M", servers=4, avg=7, hint=str(i), default=i == 1)
    # ห้องตรวจ 9: ห้องตรวจเสริม เปิดเมื่อผู้ป่วยมาก
    mp("138", "ห้องตรวจอายุรกรรม", "r_ex9", W, "doctor", "M", servers=4, avg=7, hint="9", default=False)
    # คลินิกพิเศษ (024, 036, 188) อยู่อีกโซน — จับคู่เมื่อได้ผังโซนคลินิกพิเศษ
    for i in (4, 5, 6):
        mp("145", "หลังตรวจ OPD", f"r_post{i}", W, "doctor", servers=3, avg=3, hint=str(i), default=i == 4)
    mp("019", "LAB", "r_lab", "r_labw", "lab", servers=2, avg=5, priority=10)
    mp("034", "เอกซ์เรย์", "r_xray", W, "xray", avg=6, priority=20)
    mp("110", "ห้องฉุกเฉิน", "r_er", "r_er_wait", "doctor", "E", servers=2, avg=15)
    mp("189", "หลังตรวจ ER", "r_er_wait", "r_er_wait", "doctor", avg=5)
    mp("001", "ห้องเก็บเงิน", "r_fin", W, "finance", servers=2, avg=3, priority=60)
    mp("010", "ห้องยาผู้ป่วยนอก", "r_ph", W, "pharmacy", servers=3, avg=5, priority=70)
    return doc


def sichomphu_clinic_document() -> dict:
    """โซนคลินิกพิเศษ — วาดจากผังร่าง (ภาพ 1132×547 px) ประมาณ 0.08 ม./px
    ทางเข้า: ฝั่งจุดคัดกรอง · ทางออก: ฝั่งรับยากลับบ้าน"""
    K, OX, OY = 0.08, 40, 40

    def m(v, o):
        return round((v - o) * K, 1)

    B, F = "bld_clinic", "flr_clinic_1"
    doc = {
        "buildings": [{"id": B, "code": "CLINIC", "name": "คลินิกพิเศษ", "sort": 2}],
        "floors": [{"id": F, "building_id": B, "level": 1, "name": "ชั้น 1", "width": m(1072, OX), "height": m(507, OY),
                    "plan_image": None, "plan_opacity": 0.5}],
        "rooms": [], "nodes": [], "edges": [],
    }

    def node(nid, x, y, kind="corridor", name=None):
        nid = "k_" + nid
        doc["nodes"].append({"id": nid, "floor_id": F, "kind": kind, "x": m(x, OX), "y": m(y, OY), "name": name, "link_group": None})
        return nid

    def edge(a, b):
        doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": "walk", "accessible": True})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    def room(rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None):
        x1, y1, x2, y2 = box
        doc["rooms"].append({"id": "k_" + rid, "floor_id": F, "code": code, "name": name, "short_name": short, "kind": kind,
                             "polygon": rect(m(x1, OX), m(y1, OY), m(x2, OX), m(y2, OY)), "door_node_id": door,
                             "capacity": capacity, "seats": seats, "desk": desk, "color": None, "decor": decor})

    # ทางเข้า (บน ฝั่งจุดคัดกรอง) / ทางออก (บน ข้างห้องรับยากลับบ้าน)
    ent = node("ent", 400, 40, "entrance", "ทางเข้าคลินิกพิเศษ")
    ext = node("exit", 870, 40, "exit", "ทางออก (รับยากลับบ้าน)")
    top = [node("t400", 400, 95, "junction"), node("t593", 593, 95), node("t870", 870, 95, "junction")]
    chain(top)
    edge(ent, top[0]); edge(top[2], ext)

    # ทางเดินแนวตั้งฝั่งซ้าย (ผ่านจุดคัดกรอง)
    v1 = [top[0], node("v247", 400, 247), node("v300", 400, 300, "junction"), node("v428", 400, 428), node("v450", 400, 450)]
    chain(v1)
    # ทางเดินแนวนอนใต้ห้องตรวจ
    xs = [465, 538, 593, 628, 637, 663, 708, 738, 748, 759, 768, 792, 826, 834, 857, 860]
    h = [v1[2]] + [node(f"h{x}", x, 300, "junction" if x == 860 else "corridor") for x in xs]
    chain(h)
    v2 = [h[-1], node("w419", 860, 419), node("w450", 860, 450)]
    chain(v2)

    # จุดคัดกรอง / ซักประวัติ 1 (ริมทางเดินซ้าย)
    d = node("d_scr", 389, 247, "door", "หน้าจุดคัดกรอง"); edge("k_v247", d)
    room("scr", "C-SCR", "จุดคัดกรอง (คลินิกพิเศษ)", "คัดกรอง", "counter", (373, 223, 389, 271), d, 4, desk="w")
    d = node("d_hx1", 389, 428, "door", "หน้าซักประวัติ 1"); edge("k_v428", d)
    room("hx1", "C-HX1", "ซักประวัติ 1", "ซักประวัติ 1", "counter", (373, 405, 389, 452), d, 2, desk="w")
    # ซักประวัติ 2–4 (แถวบน)
    for i, (x1, x2, dx) in enumerate(((438, 492, 465), (511, 566, 538), (566, 620, 593)), start=2):
        d = node(f"d_hx{i}", dx, 226, "door", f"หน้าซักประวัติ {i}"); edge(f"k_h{dx}", d)
        room(f"hx{i}", f"C-HX{i}", f"ซักประวัติ {i}", f"ซักประวัติ {i}", "counter", (x1, 208, x2, 226), d, 2, desk="n")

    # ห้องตรวจ 1–4 + จุดรอหน้าห้อง + หลังตรวจ 5–8
    exam = ((621, 686, 637), (686, 751, 748), (751, 816, 768), (816, 881, 834))
    for i, (x1, x2, dx) in enumerate(exam, start=1):
        d = node(f"d_ex{i}", dx, 208, "door", f"หน้าห้องตรวจ {i} (คลินิกพิเศษ)"); edge(f"k_h{dx}", d)
        room(f"ex{i}", f"C-EX{i}", f"ห้องตรวจคลินิกพิเศษ {i}", f"ห้องตรวจ {i}", "service", (x1, 135, x2, 208), d, 3, desk="n")
    for i, (x1, x2, dx) in enumerate(((621, 635, 628), (731, 746, 738), (752, 767, 759), (819, 834, 826)), start=1):
        d = node(f"d_sw{i}", dx, 281, "door"); edge(f"k_h{dx}", d)
        room(f"sw{i}", f"C-SW{i}", f"จุดรอหน้าห้องตรวจ {i}", f"รอ {i}", "waiting", (x1, 208, x2, 281), d, 5, seats=True)
    for i, (x1, x2, dx) in zip((5, 6, 7, 8), ((640, 686, 663), (686, 731, 708), (769, 815, 792), (835, 880, 857))):
        d = node(f"d_post{i}", dx, 224, "door"); edge(f"k_h{dx}", d)
        room(f"post{i}", f"C-POST{i}", f"หลังตรวจ {i}", f"หลังตรวจ {i}", "counter", (x1, 209, x2, 224), d, 3, desk="n")
    d = node("d_post9", 832, 419, "door"); edge("k_w419", d)
    room("post9", "C-POST9", "หลังตรวจ 9", "หลังตรวจ 9", "counter", (778, 410, 832, 428), d, 3, desk="w")

    # ห้องรอพบแพทย์ 3 ห้อง
    d = node("d_wl", 359, 300, "door", "ทางเข้าห้องรอ (ซ้าย)"); edge("k_v300", d)
    room("wait_l", "C-WL", "ห้องรอพบแพทย์ (ซ้าย)", "รอพบแพทย์", "waiting", (60, 135, 359, 487), d, 120, seats=True)
    d = node("d_wm", 593, 322, "door", "ทางเข้าห้องรอ (กลาง)"); edge("k_h593", d)
    d2 = node("d_wm2", 430, 450, "door"); edge("k_v450", d2)
    d3 = node("d_wm3", 761, 450, "door"); edge("k_w450", d3)
    edge(d, d2); edge(d, d3)  # เดินผ่านในห้องรอได้
    room("wait_m", "C-WM", "ห้องรอพบแพทย์ (กลาง)", "รอพบแพทย์", "waiting", (430, 322, 761, 492), d, 100, seats=True)
    d = node("d_wr", 887, 300, "door", "ทางเข้าห้องรอ (ขวา)"); edge("k_h860", d)
    room("wait_r", "C-WR", "ห้องรอรับยา", "รอรับยา", "waiting", (887, 135, 1052, 487), d, 80, seats=True)

    # รับยากลับบ้าน (ช่องจ่ายยาหันลงหาห้องรอรับยา) → ทางออก
    d_ph = node("d_ph", 970, 131, "door", "ช่องรับยากลับบ้าน")
    chain([d, node("d_wr2", 970, 135, "door"), d_ph, node("p870", 870, 131), top[2]])
    room("pharm", "C-PH", "รับยาและชำระเงิน", "รับยากลับบ้าน", "window", (887, 56, 1052, 128), d_ph, 8, desk="s", decor="pharmacy")
    return doc


def clinic_mapping() -> list[dict]:
    """จับคู่รหัส HOSxP ของคลินิกพิเศษ (024, 036, 188, 039)"""
    out = []

    def mp(dep, name, room_id, wait, stage, prefix=None, servers=1, avg=5, priority=50, hint=None, default=True):
        out.append({"id": f"m_{dep}_{hint or room_id}", "depcode": dep, "dep_name": name, "room_id": room_id,
                    "wait_room_id": wait, "room_hint": hint, "is_default": default, "stage": stage,
                    "priority": priority, "queue_prefix": prefix, "servers": servers, "avg_service_min": avg})

    for i in range(1, 5):
        mp("024", "คลินิกพิเศษ (ซักประวัติ)", f"k_hx{i}", "k_wait_l", "screening", "S", servers=4, avg=5, hint=str(i), default=i == 1)
    for i in range(1, 5):
        mp("036", "ห้องตรวจคลินิกพิเศษ", f"k_ex{i}", "k_wait_m", "doctor", "S", servers=4, avg=8, hint=str(i), default=i == 1)
    for i in range(5, 10):
        mp("188", "หลังตรวจคลินิกพิเศษ", f"k_post{i}", "k_wait_m", "doctor", servers=5, avg=3, hint=str(i), default=i == 5)
    # ผู้ป่วยคลินิกพิเศษรับยาและชำระเงินที่จุดเดียวกัน แล้วออกทางออกของโซน (ไม่ข้ามไปโซน OPD)
    mp("039", "รับยาและชำระเงิน (คลินิกพิเศษ)", "k_pharm", "k_wait_r", "pharmacy", servers=2, avg=5, priority=70)
    return out


def sichomphu_ari_document() -> dict:
    """โซน ARI (คลินิกโรคทางเดินหายใจ/ไข้หวัด) — วาดจากผังร่าง (ภาพ 1135×758 px) ประมาณ 0.08 ม./px
    ทางเข้า-ออกจุดเดียวทางทิศตะวันตก"""
    K, OX, OY = 0.08, 30, 30

    def m(v, o):
        return round((v - o) * K, 1)

    B, F = "bld_ari", "flr_ari_1"
    doc = {
        "buildings": [{"id": B, "code": "ARI", "name": "ARI", "sort": 3}],
        "floors": [{"id": F, "building_id": B, "level": 1, "name": "ชั้น 1", "width": m(1000, OX), "height": m(710, OY),
                    "plan_image": None, "plan_opacity": 0.5}],
        "rooms": [], "nodes": [], "edges": [],
    }

    def node(nid, x, y, kind="corridor", name=None):
        nid = "a_" + nid
        doc["nodes"].append({"id": nid, "floor_id": F, "kind": kind, "x": m(x, OX), "y": m(y, OY), "name": name, "link_group": None})
        return nid

    def edge(a, b):
        doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": "walk", "accessible": True})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    def room(rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None):
        x1, y1, x2, y2 = box
        doc["rooms"].append({"id": "a_" + rid, "floor_id": F, "code": code, "name": name, "short_name": short, "kind": kind,
                             "polygon": rect(m(x1, OX), m(y1, OY), m(x2, OX), m(y2, OY)), "door_node_id": door,
                             "capacity": capacity, "seats": seats, "desk": desk, "color": None, "decor": decor})

    # ทางเข้า-ออก → ห้องรอพบแพทย์ใหญ่ → ทางเดินฝั่งตะวันออก
    ent = node("ent", 30, 405, "entrance", "ทางเข้า-ออก ARI")
    d_hw = node("d_hw", 260, 405, "door", "ทางเข้าห้องรอพบแพทย์")
    d_he = node("d_he", 683, 405, "door")
    chain([ent, node("e230", 230, 405, "junction"), d_hw, d_he])
    room("wait", "A-W", "ห้องรอพบแพทย์ ARI", "รอพบแพทย์", "waiting", (260, 162, 683, 659), d_hw, 150, seats=True)
    col = [node(f"c{y}", 715, y, "junction" if y in (355, 405, 640) else "corridor") for y in (140, 192, 262, 332, 355, 405, 506, 640, 660)]
    chain(col)
    edge(d_he, "a_c405")

    d = node("d_xr", 725, 125, "door", "หน้าห้อง X-ray"); edge("a_c140", d)
    room("xray", "A-XR", "X-RAY (ARI)", "X-RAY", "service", (604, 46, 846, 125), d, 4, desk="n")
    d = node("d_scr", 752, 192, "door", "หน้าจุดคัดกรอง"); edge("a_c192", d)
    room("scr", "A-SCR", "จุดคัดกรอง ARI", "คัดกรอง", "counter", (752, 176, 855, 209), d, 4, desk="e")
    d = node("d_hx1", 754, 262, "door", "หน้าซักประวัติ 1"); edge("a_c262", d)
    room("hx1", "A-HX1", "ซักประวัติ 1", "ซักประวัติ 1", "counter", (754, 246, 857, 279), d, 3, desk="e")
    d = node("d_doc", 754, 332, "door", "หน้าคอมหมอ"); edge("a_c332", d)
    room("doc", "A-DOC", "คอมหมอ", "คอมหมอ", "counter", (754, 315, 857, 349), d, 3, desk="e")
    d = node("d_ws", 746, 506, "door", "จุดรอหน้าห้องตรวจ"); edge("a_c506", d)
    room("wait_s", "A-WS", "จุดรอหน้าห้องตรวจ ARI", "รอพบแพทย์", "waiting", (746, 398, 858, 614), d, 20, seats=True)

    # ห้องตรวจ 1–3 (ประตูฝั่งตะวันตก) — ทางเดินเลียบหน้าห้อง
    ex = [node(f"x{y}", 860, y, "junction" if y in (355, 640) else "corridor") for y in (355, 406, 498, 590, 640)]
    chain(ex)
    edge("a_c355", ex[0]); edge("a_c640", ex[-1])
    for i, (y1, y2, dy) in zip((1, 2, 3), ((544, 635, 590), (452, 544, 498), (360, 452, 406))):
        d = node(f"d_ex{i}", 863, dy, "door", f"หน้าห้องตรวจ {i} (ARI)"); edge(f"a_x{dy}", d)
        room(f"ex{i}", f"A-EX{i}", f"ห้องตรวจ ARI {i}", f"ห้องตรวจ {i}", "service", (863, y1, 966, y2), d, 3, desk="e")

    d = node("d_ph", 748, 660, "door", "จุดรับยา ARI"); edge("a_c660", d)
    room("pharm", "A-PH", "จุดรับยา ARI", "จุดรับยา", "window", (748, 643, 851, 677), d, 6, desk="w", decor="pharmacy")
    return doc


def ari_mapping() -> list[dict]:
    """จับคู่รหัส HOSxP ของ ARI (047 / 005 / 002) — ห้องยา 010 และ X-ray 034 ใช้รหัสเดียวกับ OPD
    จึงจำกัดเฉพาะผู้ป่วยที่แผนกหลัก (main_dep) = 047"""
    out = []

    def mp(dep, name, room_id, wait, stage, prefix=None, servers=1, avg=5, priority=50, hint=None, default=True, zone=None):
        out.append({"id": f"m_{dep}_{hint or room_id}", "depcode": dep, "dep_name": name, "room_id": room_id,
                    "wait_room_id": wait, "room_hint": hint, "is_default": default, "stage": stage, "for_main_dep": zone,
                    "priority": priority, "queue_prefix": prefix, "servers": servers, "avg_service_min": avg})

    mp("047", "คลินิกไข้หวัดใหญ่ (ARI)", "a_scr", "a_wait", "screening", "R", servers=2, avg=4)
    for i in (1, 2, 3):
        mp("005", "ห้องตรวจไข้หวัดใหญ่", f"a_ex{i}", "a_wait_s", "doctor", "R", servers=3, avg=6, hint=str(i), default=i == 1)
    mp("002", "หลังตรวจไข้หวัดใหญ่", "a_doc", "a_wait", "doctor", avg=3)
    mp("010", "จุดรับยา ARI", "a_pharm", "a_wait", "pharmacy", servers=1, avg=4, priority=70, zone="047")
    mp("034", "X-RAY (ARI)", "a_xray", "a_wait", "xray", avg=6, priority=20, zone="047")
    return out


def sichomphu_dental_document() -> dict:
    """ตึกทันตกรรม — วาดจากผังร่าง (ภาพ 607×770 px) ประมาณ 0.08 ม./px · ทางเข้า-ออกฝั่งตะวันออก"""
    K, OX, OY = 0.08, 60, 15

    def m(v, o):
        return round((v - o) * K, 1)

    B, F = "bld_dental", "flr_dental_1"
    doc = {
        "buildings": [{"id": B, "code": "DENT", "name": "ทันตกรรม", "sort": 4}],
        "floors": [{"id": F, "building_id": B, "level": 1, "name": "ชั้น 1", "width": m(440, OX), "height": m(740, OY),
                    "plan_image": None, "plan_opacity": 0.5}],
        "rooms": [], "nodes": [], "edges": [],
    }

    def node(nid, x, y, kind="corridor", name=None):
        nid = "d_" + nid
        doc["nodes"].append({"id": nid, "floor_id": F, "kind": kind, "x": m(x, OX), "y": m(y, OY), "name": name, "link_group": None})
        return nid

    def edge(a, b):
        doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": "walk", "accessible": True})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    def room(rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None):
        x1, y1, x2, y2 = box
        doc["rooms"].append({"id": "d_" + rid, "floor_id": F, "code": code, "name": name, "short_name": short, "kind": kind,
                             "polygon": rect(m(x1, OX), m(y1, OY), m(x2, OX), m(y2, OY)), "door_node_id": door,
                             "capacity": capacity, "seats": seats, "desk": desk, "color": None, "decor": decor})

    # ทางเข้า-ออก (ตะวันออก) → ทางเดินหลักแนวตั้งระหว่างห้องตรวจกับห้องรอ
    ent = node("ent", 440, 583, "entrance", "ทางเข้า-ออก ทันตกรรม")
    v = {y: node(f"v{y}", 300, y, "junction" if y in (282, 545, 583, 630) else "corridor") for y in (88, 185, 282, 380, 476, 545, 583, 630)}
    chain([v[y] for y in sorted(v)])
    edge(ent, v[583])

    d = node("d_xr", 285, 88, "door", "หน้าห้อง X-ray ทันตกรรม"); edge(v[88], d)
    room("xray", "D-XR", "X-ray ทันตกรรม", "X-ray", "service", (93, 40, 285, 137), d, 3, desk="w")
    for i, (y1, y2) in zip((4, 3, 2, 1), ((137, 234), (234, 331), (331, 428), (428, 524))):
        dy = {4: 185, 3: 282, 2: 380, 1: 476}[i]
        d = node(f"d_ex{i}", 285, dy, "door", f"หน้าห้องตรวจ {i} (ทันตกรรม)"); edge(v[dy], d)
        room(f"ex{i}", f"D-EX{i}", f"ห้องทันตกรรม {i}", f"ห้องตรวจ {i}", "service", (93, y1, 285, y2), d, 2, desk="w", decor="dental")
    d = node("d_wr", 314, 282, "door", "ทางเข้าห้องรอหน้าห้องตรวจ"); edge(v[282], d)
    room("wait_r", "D-WR", "ห้องรอพบแพทย์ (หน้าห้องตรวจ)", "รอพบแพทย์", "waiting", (314, 40, 392, 524), d, 40, seats=True)

    # คัดกรอง / ซักประวัติ / ห้องรอด้านล่าง
    h = [node("h140", 140, 630), node("h236", 236, 630, "junction"), v[630]]
    chain(h)
    d = node("d_scr", 140, 597, "door", "หน้าจุดคัดกรอง"); edge("d_h140", d)
    room("scr", "D-SCR", "จุดคัดกรอง ทันตกรรม", "คัดกรอง", "counter", (93, 567, 187, 597), d, 3, desk="n")
    d = node("d_hx1", 236, 597, "door", "หน้าซักประวัติ 1"); edge("d_h236", d)
    room("hx1", "D-HX1", "ซักประวัติ 1 ทันตกรรม", "ซักประวัติ 1", "counter", (189, 567, 284, 597), d, 3, desk="n")
    d = node("d_wb", 236, 661, "door", "ทางเข้าห้องรอ (ด้านล่าง)"); edge("d_h236", d)
    room("wait_b", "D-WB", "ห้องรอพบแพทย์ (ด้านล่าง)", "รอพบแพทย์", "waiting", (91, 661, 391, 708), d, 30, seats=True)
    return doc


def dental_mapping() -> list[dict]:
    """ทันตกรรม: 190 ซักประวัติทันตกรรม → 028 ทันตกรรม → กลับบ้าน (บางรายไปห้องยา OPD 010)"""
    out = []

    def mp(dep, name, room_id, wait, stage, prefix=None, servers=1, avg=5, priority=50, hint=None, default=True, zone=None):
        out.append({"id": f"m_{dep}_{hint or room_id}", "depcode": dep, "dep_name": name, "room_id": room_id,
                    "wait_room_id": wait, "room_hint": hint, "is_default": default, "stage": stage, "for_main_dep": zone,
                    "priority": priority, "queue_prefix": prefix, "servers": servers, "avg_service_min": avg})

    mp("190", "จุดซักประวัติทันตกรรม", "d_hx1", "d_wait_b", "screening", "D", servers=1, avg=4)
    for i in (1, 2, 3, 4):
        mp("028", "ทันตกรรม", f"d_ex{i}", "d_wait_r", "doctor", "D", servers=4, avg=20, hint=str(i), default=i == 1)
    mp("034", "X-ray ทันตกรรม", "d_xray", "d_wait_r", "xray", avg=5, priority=20, zone="190,028")
    return out


def sichomphu_physio_document() -> dict:
    """ตึกกายภาพบำบัด — วาดจากผังร่าง (ภาพ 655×857 px) ประมาณ 0.08 ม./px
    ทางเข้า-ออก 2 ทาง: ฝั่งตะวันตก และด้านล่าง"""
    K, OX, OY = 0.08, 40, 10

    def m(v, o):
        return round((v - o) * K, 1)

    B, F = "bld_physio", "flr_physio_1"
    doc = {
        "buildings": [{"id": B, "code": "PT", "name": "กายภาพบำบัด", "sort": 5}],
        "floors": [{"id": F, "building_id": B, "level": 1, "name": "ชั้น 1", "width": m(660, OX), "height": m(830, OY),
                    "plan_image": None, "plan_opacity": 0.5}],
        "rooms": [], "nodes": [], "edges": [],
    }

    def node(nid, x, y, kind="corridor", name=None):
        nid = "p_" + nid
        doc["nodes"].append({"id": nid, "floor_id": F, "kind": kind, "x": m(x, OX), "y": m(y, OY), "name": name, "link_group": None})
        return nid

    def edge(a, b):
        doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": "walk", "accessible": True})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    def room(rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None):
        x1, y1, x2, y2 = box
        doc["rooms"].append({"id": "p_" + rid, "floor_id": F, "code": code, "name": name, "short_name": short, "kind": kind,
                             "polygon": rect(m(x1, OX), m(y1, OY), m(x2, OX), m(y2, OY)), "door_node_id": door,
                             "capacity": capacity, "seats": seats, "desk": desk, "color": None, "decor": decor})

    # ทางเข้า-ออก ฝั่งตะวันตก → ทางเดิน x=240 ; ด้านล่าง → เดินอ้อมห้องพักนักกายภาพทางทิศตะวันออก
    ent_w = node("ent_w", 40, 572, "entrance", "ทางเข้า-ออก (ฝั่งตะวันตก)")
    ent_s = node("ent_s", 440, 830, "entrance", "ทางเข้า-ออก (ด้านล่าง)")
    colw = [node("w475", 240, 475, "junction"), node("w572", 240, 572, "junction"), node("w640", 240, 640)]
    chain(colw)
    edge(ent_w, "p_w572")
    row = [colw[0], node("r387", 387, 475, "junction"), node("r546", 546, 475), node("r580", 580, 475), node("r648", 648, 475, "junction")]
    chain(row)
    chain(["p_r648", node("e800", 648, 800, "junction"), node("s800", 440, 800), ent_s])

    # ห้องพักนักกายภาพ (เฉพาะเจ้าหน้าที่) — จุดคัดกรองเป็นช่องบริการที่ผนังฝั่งตะวันตก
    d = node("d_staff", 580, 534, "door", "ห้องพักนักกายภาพ"); edge("p_r580", d)
    room("staff", "PT-STAFF", "ห้องพักนักกายภาพ", "ห้องพักนักกายภาพ", "service", (271, 534, 636, 770), d, 10)
    d = node("d_scr", 272, 640, "door", "หน้าจุดคัดกรอง"); edge("p_w640", d)
    room("scr", "PT-SCR", "จุดคัดกรอง กายภาพ", "คัดกรอง", "counter", (272, 592, 306, 698), d, 3, desk="e")

    # จุดรอ / เตียงกายภาพ / ซักประวัติ
    d = node("d_ws", 387, 488, "door", "จุดรอหน้าเตียงกายภาพ"); edge("p_r387", d)
    room("wait_s", "PT-WS", "จุดรอพบแพทย์ (หน้าเตียงกายภาพ)", "รอพบแพทย์", "waiting", (271, 488, 492, 529), d, 20, seats=True)
    d = node("d_wl", 203, 640, "door", "จุดรอ (ฝั่งตะวันตก)"); edge("p_w640", d)
    room("wait_l", "PT-WL", "จุดรอพบแพทย์ (ฝั่งตะวันตก)", "รอพบแพทย์", "waiting", (149, 605, 203, 770), d, 15, seats=True)
    d = node("d_beds", 387, 434, "door", "ทางเข้าเตียงกายภาพ"); edge("p_r387", d)
    room("beds", "PT-BED", "เตียงกายภาพ", "เตียงกายภาพ", "service", (271, 18, 502, 434), d, 40, decor="beds")
    d = node("d_hx1", 546, 466, "door", "หน้าซักประวัติ 1"); edge("p_r546", d)
    room("hx1", "PT-HX1", "ซักประวัติ 1 กายภาพ", "ซักประวัติ 1", "counter", (522, 359, 570, 466), d, 3, desk="e")
    return doc


def physio_mapping() -> list[dict]:
    """กายภาพบำบัด: ใช้รหัส 046 รหัสเดียวตั้งแต่รอจนเสร็จ (รับผู้ป่วย = ขึ้นเตียงกายภาพ)"""
    return [{"id": "m_046_beds", "depcode": "046", "dep_name": "กายภาพบำบัด", "room_id": "p_beds",
             "wait_room_id": "p_wait_s", "room_hint": None, "is_default": True, "stage": "other", "for_main_dep": None,
             "priority": 30, "queue_prefix": "P", "servers": 4, "avg_service_min": 12}]


def sichomphu_thaimed_document() -> dict:
    """ตึกแพทย์แผนไทย — วาดจากผังร่าง (ภาพ 772×744 px) ประมาณ 0.08 ม./px · ทางเข้า-ออกฝั่งตะวันตก"""
    K, OX, OY = 0.08, 30, 20

    def m(v, o):
        return round((v - o) * K, 1)

    B, F = "bld_thaimed", "flr_thaimed_1"
    doc = {
        "buildings": [{"id": B, "code": "TTM", "name": "แพทย์แผนไทย", "sort": 6}],
        "floors": [{"id": F, "building_id": B, "level": 1, "name": "ชั้น 1", "width": m(740, OX), "height": m(720, OY),
                    "plan_image": None, "plan_opacity": 0.5}],
        "rooms": [], "nodes": [], "edges": [],
    }

    def node(nid, x, y, kind="corridor", name=None):
        nid = "t_" + nid
        doc["nodes"].append({"id": nid, "floor_id": F, "kind": kind, "x": m(x, OX), "y": m(y, OY), "name": name, "link_group": None})
        return nid

    def edge(a, b):
        doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": "walk", "accessible": True})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    def room(rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None):
        x1, y1, x2, y2 = box
        doc["rooms"].append({"id": "t_" + rid, "floor_id": F, "code": code, "name": name, "short_name": short, "kind": kind,
                             "polygon": rect(m(x1, OX), m(y1, OY), m(x2, OX), m(y2, OY)), "door_node_id": door,
                             "capacity": capacity, "seats": seats, "desk": desk, "color": None, "decor": decor})

    # ทางเข้า-ออก (ตะวันตก) → ทางเดินแนวนอน y=548 → ทางเดินแนวตั้งระหว่างห้องตรวจกับเตียงแผนไทย
    ent = node("ent", 30, 548, "entrance", "ทางเข้า-ออก แพทย์แผนไทย")
    row = [ent] + [node(f"r{x}", x, 548, "junction" if x == 454 else "corridor") for x in (180, 258, 310, 366, 454)]
    chain(row)
    col = [node(f"c{y}", 454, y) for y in (244, 354, 400)] + ["t_r454"]
    chain(col)

    for i, (y1, y2, dy) in zip((2, 1), ((189, 299, 244), (299, 409, 354))):
        d = node(f"d_ex{i}", 424, dy, "door", f"หน้าห้องตรวจ {i} (แผนไทย)"); edge(f"t_c{dy}", d)
        room(f"ex{i}", f"T-EX{i}", f"ห้องตรวจแพทย์แผนไทย {i}", f"ห้องตรวจ {i}", "service", (205, y1, 424, y2), d, 3, desk="w")
    d = node("d_scr", 258, 516, "door", "หน้าจุดคัดกรอง"); edge("t_r258", d)
    room("scr", "T-SCR", "จุดคัดกรอง แผนไทย", "คัดกรอง", "counter", (205, 482, 312, 516), d, 3, desk="n")
    d = node("d_hx1", 366, 516, "door", "หน้าซักประวัติ 1"); edge("t_r366", d)
    room("hx1", "T-HX1", "ซักประวัติ 1 แผนไทย", "ซักประวัติ 1", "counter", (313, 482, 420, 516), d, 3, desk="n")
    d = node("d_wait", 310, 587, "door", "ทางเข้าห้องรอ"); edge("t_r310", d)
    room("wait", "T-W", "ห้องรอพบแพทย์ แผนไทย", "รอพบแพทย์", "waiting", (198, 587, 423, 692), d, 30, seats=True)
    d = node("d_beds", 484, 400, "door", "ทางเข้าเตียงแผนไทย"); edge("t_c400", d)
    room("beds", "T-BED", "เตียงแผนไทย", "เตียงแผนไทย", "service", (484, 50, 716, 692), d, 40, decor="beds")
    return doc


def thaimed_mapping() -> list[dict]:
    """แพทย์แผนไทย: ใช้รหัส 035 รหัสเดียว (รับผู้ป่วย = อยู่ที่เตียงแผนไทย เฉลี่ยราว 1 ชั่วโมง)"""
    return [{"id": "m_035_beds", "depcode": "035", "dep_name": "แพทย์แผนไทย", "room_id": "t_beds",
             "wait_room_id": "t_wait", "room_hint": None, "is_default": True, "stage": "other", "for_main_dep": None,
             "priority": 40, "queue_prefix": "T", "servers": 6, "avg_service_min": 60}]


def sichomphu_promotion_document() -> dict:
    """ตึกส่งเสริมสุขภาพ (แม่และเด็ก ฝากครรภ์ วัคซีน) — วาดจากผังร่าง (ภาพ 854×692 px) ประมาณ 0.08 ม./px
    ทางเข้า-ออก 2 ทาง ฝั่งตะวันตก (บน/ล่าง)"""
    K, OX, OY = 0.08, 40, 30

    def m(v, o):
        return round((v - o) * K, 1)

    B, F = "bld_promo", "flr_promo_1"
    doc = {
        "buildings": [{"id": B, "code": "HP", "name": "ส่งเสริมสุขภาพ", "sort": 7}],
        "floors": [{"id": F, "building_id": B, "level": 1, "name": "ชั้น 1", "width": m(800, OX), "height": m(650, OY),
                    "plan_image": None, "plan_opacity": 0.5}],
        "rooms": [], "nodes": [], "edges": [],
    }

    def node(nid, x, y, kind="corridor", name=None):
        nid = "h_" + nid
        doc["nodes"].append({"id": nid, "floor_id": F, "kind": kind, "x": m(x, OX), "y": m(y, OY), "name": name, "link_group": None})
        return nid

    def edge(a, b):
        doc["edges"].append({"id": f"e_{a}_{b}", "node_a": a, "node_b": b, "kind": "walk", "accessible": True})

    def chain(ids):
        for a, b in zip(ids, ids[1:]):
            edge(a, b)

    def room(rid, code, name, short, kind, box, door, capacity=10, seats=False, desk=None, decor=None):
        x1, y1, x2, y2 = box
        doc["rooms"].append({"id": "h_" + rid, "floor_id": F, "code": code, "name": name, "short_name": short, "kind": kind,
                             "polygon": rect(m(x1, OX), m(y1, OY), m(x2, OX), m(y2, OY)), "door_node_id": door,
                             "capacity": capacity, "seats": seats, "desk": desk, "color": None, "decor": decor})

    # ทางเข้า-ออก 2 ทาง → ทางเดินแนวตั้ง x=190
    ent1 = node("ent1", 40, 75, "entrance", "ทางเข้า-ออก (บน)")
    ent2 = node("ent2", 40, 500, "entrance", "ทางเข้า-ออก (ล่าง)")
    colw = [node(f"w{y}", 190, y, "junction" if y in (75, 480) else "corridor") for y in (75, 250, 480, 500)]
    chain(colw)
    edge(ent1, "h_w75"); edge(ent2, "h_w500")
    row = ["h_w480"] + [node(f"r{x}", x, 480, "junction" if x in (445, 556) else "corridor") for x in (272, 445, 462, 556)]
    chain(row)
    col_m = [node(f"m{y}", 445, y, "junction" if y == 130 else "corridor") for y in (130, 192, 300, 397)] + ["h_r445"]
    chain(col_m)
    col_e = [node(f"e{y}", 556, y, "junction" if y == 130 else "corridor") for y in (130, 157, 253, 349, 445)] + ["h_r556"]
    chain(col_e)
    edge("h_m130", "h_e130")

    d = node("d_wb", 217, 250, "door", "ทางเข้าห้องรอพบแพทย์"); edge("h_w250", d)
    d2 = node("d_wb2", 422, 300, "door"); edge("h_m300", d2); edge(d, d2)
    # ประตูหลักฝั่งตะวันออก (หันไปทางห้องตรวจ) — จากทางเข้าเดินผ่านประตูฝั่งตะวันตกเข้ามาได้
    room("wait", "HP-W", "ห้องรอพบแพทย์ ส่งเสริมสุขภาพ", "รอพบแพทย์", "waiting", (217, 109, 422, 403), d2, 80, seats=True)
    d = node("d_scr", 272, 451, "door", "หน้าจุดคัดกรอง"); edge("h_r272", d)
    room("scr", "HP-SCR", "จุดคัดกรอง ส่งเสริมสุขภาพ", "คัดกรอง", "counter", (226, 421, 319, 451), d, 3, desk="n")

    # จุดรอเล็ก + ซักประวัติ 2 (บน) / 1 (ล่าง)
    for i, wy1, wy2, wy, hy1, hy2 in ((2, 148, 237, 192, 148, 241), (1, 353, 442, 397, 351, 445)):
        d = node(f"d_sw{i}", 462, wy, "door", f"จุดรอซักประวัติ {i}"); edge(f"h_m{wy}", d)
        room(f"sw{i}", f"HP-SW{i}", f"จุดรอซักประวัติ {i}", "รอพบแพทย์", "waiting", (462, wy1, 497, wy2), d, 8, seats=True)
        dh = node(f"d_hx{i}", 507, wy, "door", f"หน้าซักประวัติ {i}"); edge(d, dh)
        room(f"hx{i}", f"HP-HX{i}", f"ซักประวัติ {i} ส่งเสริมสุขภาพ", f"ซักประวัติ {i}", "counter", (507, hy1, 537, hy2), dh, 2, desk="e")

    # ห้องตรวจ 1–4 (ประตูฝั่งตะวันตก)
    for i, (y1, y2, dy) in zip((4, 3, 2, 1), ((109, 205, 157), (205, 301, 253), (301, 397, 349), (397, 494, 445))):
        d = node(f"d_ex{i}", 575, dy, "door", f"หน้าห้องตรวจ {i} (ส่งเสริมสุขภาพ)"); edge(f"h_e{dy}", d)
        room(f"ex{i}", f"HP-EX{i}", f"ห้องตรวจส่งเสริมสุขภาพ {i}", f"ห้องตรวจ {i}", "service", (575, y1, 766, y2), d, 3, desk="e")
    d = node("d_dent", 462, 518, "door", "หน้าห้องตรวจฟัน"); edge("h_r462", d)
    room("dent", "HP-DENT", "ห้องตรวจฟัน (แม่และเด็ก)", "ห้องตรวจฟัน", "service", (366, 518, 558, 613), d, 3, desk="n", decor="dental")
    return doc


def promotion_mapping() -> list[dict]:
    """ส่งเสริมสุขภาพ: 033 ใช้ตลอดตั้งแต่รอจนเสร็จ (ไม่ทราบห้องตรวจย่อย → รอที่ห้องรอ)
    วัคซีน 007 / หลังฉีดวัคซีน 011 / หลังตรวจคลินิกวัคซีน 025 — ยังไม่ทราบห้อง ให้รอที่ห้องรอพบแพทย์"""
    out = []

    def mp(dep, name, room_id, wait, stage, prefix=None, servers=1, avg=5, priority=50, hint=None, default=True):
        out.append({"id": f"m_{dep}_{hint or room_id or wait}", "depcode": dep, "dep_name": name, "room_id": room_id,
                    "wait_room_id": wait, "room_hint": hint, "is_default": default, "stage": stage, "for_main_dep": None,
                    "priority": priority, "queue_prefix": prefix, "servers": servers, "avg_service_min": avg})

    for i in (1, 2, 3, 4):
        mp("033", "ส่งเสริมสุขภาพ", f"h_ex{i}", "h_wait", "other", "H", servers=4, avg=10, hint=str(i), default=i == 1)
    mp("007", "คลินิกวัคซีน", None, "h_wait", "other", "V", avg=5)
    mp("011", "หลังฉีดวัคซีน", None, "h_wait", "other", avg=30)
    mp("025", "หลังตรวจคลินิกวัคซีน", None, "h_wait", "other", avg=5)
    return out


def sichomphu_document() -> dict:
    """แผนที่ รพ.สีชมพู ทุกโซน: OPD + คลินิกพิเศษ + ARI + ทันตกรรม + กายภาพบำบัด + แพทย์แผนไทย + ส่งเสริมสุขภาพ"""
    doc = sichomphu_opd_document()
    for zone in (sichomphu_clinic_document(), sichomphu_ari_document(), sichomphu_dental_document(),
                 sichomphu_physio_document(), sichomphu_thaimed_document(),
                 sichomphu_promotion_document()):
        for key in ("buildings", "floors", "rooms", "nodes", "edges"):
            doc[key] += zone[key]
    doc["mapping"] += clinic_mapping() + ari_mapping() + dental_mapping() + physio_mapping() + thaimed_mapping() + promotion_mapping()
    from .seed_campus import merge_into  # แผนที่ภาพรวม + ตึกเพิ่มเติม (ระยะ 2)
    return merge_into(doc)


def ensure_seed() -> None:
    with db.engine.begin() as conn:
        has_map = conn.execute(sa.select(sa.func.count()).select_from(db.buildings)).scalar()
        if not has_map:
            if config.IS_DEMO:
                doc = demo_document()
            else:
                # ใช้แผนที่ล่าสุดที่ส่งออกไว้ใน Git (maps/sichomphu_map.json) ถ้ามี ไม่งั้นใช้แผนที่ในโค้ด
                from .mapio import MAP_FILE, load_file
                doc = load_file(MAP_FILE) if MAP_FILE.exists() else sichomphu_document()
            mapdata.save_draft(conn, doc)
        has_version = conn.execute(sa.select(sa.func.count()).select_from(db.map_versions)).scalar()
        if not has_version:
            mapdata.publish(conn, "แผนที่ตัวอย่างเริ่มต้น")

"""ส่งออก / นำเข้าแผนที่เป็นไฟล์ JSON (ใช้แชร์แผนที่ผ่าน Git)

    python -m app.mapio export              # ส่งออกแผนที่ฉบับเผยแพร่ล่าสุด → maps/sichomphu_map.json
    python -m app.mapio import [ไฟล์]       # นำเข้าเป็นฉบับร่าง แล้วเผยแพร่
    python -m app.mapio import [ไฟล์] --draft-only

ไฟล์นี้ไม่มีข้อมูลผู้ป่วย มีแค่อาคาร ชั้น ห้อง จุดนำทาง และการจับคู่รหัส HOSxP
"""
import json
import sys
from pathlib import Path

from . import config, db, mapdata

MAP_FILE = config.BASE_DIR / "maps" / "sichomphu_map.json"
KEYS = ("buildings", "floors", "rooms", "nodes", "edges", "mapping")


def export_map(path: Path = MAP_FILE) -> dict:
    with db.engine.connect() as conn:
        hmap = mapdata.published(conn)
        doc = hmap.doc if hmap else mapdata.load_draft(conn)
    out = {k: doc.get(k, []) for k in KEYS}
    # เรียงให้คงที่ เพื่อให้ git diff อ่านง่าย
    for k in KEYS:
        out[k] = sorted(out[k], key=lambda x: str(x.get("id")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def load_file(path: Path = MAP_FILE) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: doc.get(k, []) for k in KEYS}


def import_map(path: Path = MAP_FILE, publish: bool = True, note: str = "") -> int | None:
    doc = load_file(path)
    with db.engine.begin() as conn:
        mapdata.save_draft(conn, doc)
        if publish:
            return mapdata.publish(conn, note or f"นำเข้าจาก {Path(path).name}")
    return None


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("export", "import"):
        print(__doc__)
        return 1
    db.init_db()
    path = Path(next((a for a in argv[1:] if not a.startswith("--")), MAP_FILE))
    if argv[0] == "export":
        doc = export_map(path)
        print(f"ส่งออกแล้ว: {path}  ({len(doc['buildings'])} โซน, {len(doc['rooms'])} ห้อง, {len(doc['mapping'])} รหัส HOSxP)")
    else:
        v = import_map(path, publish="--draft-only" not in argv)
        print(f"นำเข้าแล้ว: {path}" + (f" → เผยแพร่ฉบับที่ {v}" if v else " (ฉบับร่าง ยังไม่เผยแพร่)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

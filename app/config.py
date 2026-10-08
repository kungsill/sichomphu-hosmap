"""การตั้งค่าระบบ อ่านจากไฟล์ .env (ถ้ามี) และ Environment Variables"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


HOSPITAL_NAME = os.environ.get("HOSPITAL_NAME", "โรงพยาบาลสีชมพู")

# ฐานข้อมูลระบบนำทาง (แยกจาก HOSxP) — ใช้ SQLite สำหรับทดลอง หรือ MySQL/MariaDB สำหรับใช้งานจริง
# ตัวอย่าง MySQL: mysql+pymysql://nav:password@127.0.0.1:3306/hospital_navigation?charset=utf8mb4
NAV_DB_URL = os.environ.get("NAV_DB_URL", f"sqlite:///{(DATA_DIR / 'hospital_navigation.db').as_posix()}")

# แหล่งข้อมูล HOSxP: "mock" = จำลองผู้ป่วยเพื่อสาธิต, "mysql" = เชื่อม HOSxP V4 จริงแบบอ่านอย่างเดียว
HOSXP_MODE = os.environ.get("HOSXP_MODE", "mock").strip().lower()
# บัญชีที่ใช้ต้องมีสิทธิ์ SELECT เท่านั้น
HOSXP_DB_URL = os.environ.get("HOSXP_DB_URL", "")
HOSXP_QUERY_FILE = Path(os.environ.get("HOSXP_QUERY_FILE", str(BASE_DIR / "hosxp_queries.ini")))

POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "3"))
# จำนวนรอบที่ VN หายไปจากผลลัพธ์ติดต่อกันก่อนถือว่ายกเลิก (กันกรณีอ่านข้อมูลไม่ครบชั่วคราว)
MISSING_POLLS_BEFORE_CANCEL = int(os.environ.get("MISSING_POLLS_BEFORE_CANCEL", "5"))
# ช่วงเวลา (นาที) หลังถูกส่งไปห้องใหม่ ที่ถือว่าผู้ป่วยยังเดินอยู่
WALKING_MINUTES = float(os.environ.get("WALKING_MINUTES", "2"))
# แสดงผู้ป่วยที่จบ Visit แล้วบนแผนที่ต่ออีกกี่นาที (สถานะ "กำลังกลับบ้าน")
SHOW_FINISHED_MINUTES = float(os.environ.get("SHOW_FINISHED_MINUTES", "6"))

# โหมดสาธิต: ความเร็วนาฬิกาจำลอง (นาทีจำลองต่อ 1 นาทีจริง)
DEMO_SPEED = float(os.environ.get("DEMO_SPEED", "12"))
DEMO_START_TIME = os.environ.get("DEMO_START_TIME", "07:30")
DEMO_WARMUP_MINUTES = float(os.environ.get("DEMO_WARMUP_MINUTES", "150"))

# URL ที่ผู้ป่วยใช้เปิดผ่าน QR (ต้องเข้าถึงได้จากมือถือ เช่น Wi-Fi ของโรงพยาบาล)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
TOKEN_VALID_HOURS = float(os.environ.get("TOKEN_VALID_HOURS", "18"))

# รหัสผ่านสำหรับหน้าจอเจ้าหน้าที่และ Map Builder (HTTP Basic) — เว้นว่าง = ไม่ล็อก (ใช้เฉพาะทดลอง)
STAFF_USER = os.environ.get("STAFF_USER", "admin")
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "")

# รหัสผ่าน Map Builder และ API จัดการแผนที่ (แยกจากหน้าจอเจ้าหน้าที่)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

SHOW_VITALS = _bool("SHOW_VITALS", True)

IS_DEMO = HOSXP_MODE == "mock"

"""การเข้าสู่ระบบด้วย Session Cookie (ลงลายมือชื่อ HMAC) สำหรับหน้าจอเจ้าหน้าที่และ Map Builder"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time

from fastapi import HTTPException, Request

from . import config

COOKIE = "hosmap_session"
SESSION_HOURS = float(os.environ.get("SESSION_HOURS", "12"))
ROLE_RANK = {"staff": 1, "admin": 2}


def _secret() -> bytes:
    env = os.environ.get("SESSION_SECRET")
    if env:
        return env.encode()
    path = config.DATA_DIR / "session.key"
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip().encode()


SECRET = _secret()


def _sign(payload: str) -> str:
    return hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()


def make_cookie(user: str, role: str) -> str:
    payload = f"{user}|{role}|{int(time.time() + SESSION_HOURS * 3600)}"
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + _sign(payload)


def read_cookie(value: str | None) -> dict | None:
    if not value or "." not in value:
        return None
    raw, sig = value.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(raw.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    user, role, exp = payload.split("|")
    if int(exp) < time.time():
        return None
    return {"user": user, "role": role}


def required_role(role: str) -> bool:
    """บทบาทนี้ต้องเข้าสู่ระบบหรือไม่ (ถ้าไม่ได้ตั้งรหัสผ่านไว้ = เปิดให้เข้าได้)"""
    if role == "admin":
        return bool(config.ADMIN_PASSWORD or config.STAFF_PASSWORD)
    return bool(config.STAFF_PASSWORD)


def has_role(request: Request, role: str) -> bool:
    if not required_role(role):
        return True
    sess = read_cookie(request.cookies.get(COOKIE))
    return bool(sess) and ROLE_RANK.get(sess["role"], 0) >= ROLE_RANK[role]


def check_password(user: str, password: str) -> str | None:
    """คืนบทบาทที่ตรงกับชื่อผู้ใช้/รหัสผ่าน"""
    def eq(a, b):
        return secrets.compare_digest(a.encode(), b.encode())
    if config.ADMIN_PASSWORD and eq(user, config.ADMIN_USER) and eq(password, config.ADMIN_PASSWORD):
        return "admin"
    if config.STAFF_PASSWORD and eq(user, config.STAFF_USER) and eq(password, config.STAFF_PASSWORD):
        # ถ้าไม่ได้ตั้งรหัสผู้ดูแลแยก รหัสเจ้าหน้าที่ใช้เข้า Map Builder ได้ด้วย
        return "staff" if config.ADMIN_PASSWORD else "admin"
    return None


# ---------------------------------------------------------------- กันเดารหัสผ่าน
_fails: dict[str, list[float]] = {}
_lock = threading.Lock()
MAX_FAILS, WINDOW, LOCK_SECONDS = 5, 300, 60


def locked_for(ip: str) -> int:
    with _lock:
        recent = [t for t in _fails.get(ip, []) if t > time.time() - WINDOW]
        _fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            return max(0, int(recent[-1] + LOCK_SECONDS - time.time()))
        return 0


def record_fail(ip: str) -> None:
    with _lock:
        _fails.setdefault(ip, []).append(time.time())


def clear_fails(ip: str) -> None:
    with _lock:
        _fails.pop(ip, None)


# ---------------------------------------------------------------- FastAPI dependencies
def staff(request: Request):
    if not has_role(request, "staff"):
        raise HTTPException(401, "ต้องเข้าสู่ระบบ")
    return True


def admin(request: Request):
    if not has_role(request, "admin"):
        raise HTTPException(401, "ต้องเข้าสู่ระบบผู้ดูแลแผนที่")
    return True

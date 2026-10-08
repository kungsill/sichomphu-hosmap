"""Smart Hospital Navigation — โรงพยาบาลสีชมพู"""
import asyncio
import hashlib
import html
import io
import json
import logging
from urllib.parse import quote
from contextlib import asynccontextmanager

import qrcode
import qrcode.image.svg
import sqlalchemy as sa
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import auth, config, db, mapdata, seed
from .auth import admin, staff
from .clock import clock
from .hosxp.worker import Worker, get_or_create_token
from .status import SnapshotBuilder, patient_view

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


# ---------------------------------------------------------------- SSE hub
class Hub:
    def __init__(self):
        self.queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        self.queues.add(q)
        return q

    def unsubscribe(self, q):
        self.queues.discard(q)

    def publish(self, item):
        for q in list(self.queues):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(item)


hub = Hub()
state: dict = {"worker": None, "simulator": None, "builder": SnapshotBuilder()}


async def sync_loop():
    builder: SnapshotBuilder = state["builder"]
    while True:
        try:
            if state["simulator"]:
                await asyncio.to_thread(state["simulator"].tick)
            if state["worker"]:
                await asyncio.to_thread(state["worker"].sync_once)
            snap = await asyncio.to_thread(builder.build)
            hub.publish(snap)
        except Exception:
            log.exception("รอบซิงก์ผิดพลาด")
        await asyncio.sleep(config.POLL_SECONDS)


@asynccontextmanager
async def lifespan(_app):
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()
    seed.ensure_seed()
    if config.IS_DEMO:
        from .hosxp.mock import Simulator
        # โหมดสาธิต: เริ่มวันจำลองใหม่ทุกครั้งที่เปิดโปรแกรม
        with db.engine.begin() as conn:
            for t in db.PATIENT_TABLES:
                conn.execute(t.delete())
        sim = Simulator()
        log.info("โหมดสาธิต: กำลังจำลองผู้ป่วยย้อนหลัง %s นาที ...", config.DEMO_WARMUP_MINUTES)
        await asyncio.to_thread(sim.warmup, config.DEMO_WARMUP_MINUTES)
        state["simulator"] = sim
    try:
        state["worker"] = Worker()
    except Exception as exc:
        log.error("เริ่มตัวเชื่อม HOSxP ไม่สำเร็จ: %s", exc)
    state["builder"] = SnapshotBuilder(state["worker"], state["simulator"])
    if state["worker"]:
        await asyncio.to_thread(state["worker"].sync_once)
    await asyncio.to_thread(state["builder"].build)
    task = asyncio.create_task(sync_loop())
    yield
    task.cancel()


app = FastAPI(title="Smart Hospital Navigation", lifespan=lifespan)
@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """ให้เบราว์เซอร์ตรวจไฟล์ JS/CSS ใหม่ทุกครั้ง (ได้ 304 ถ้าไม่เปลี่ยน) — หน้าจอจะได้ไม่ใช้ไฟล์เก่าหลังอัปเดตระบบ"""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR, check_dir=False), name="uploads")

def page(name: str) -> FileResponse:
    return FileResponse(config.STATIC_DIR / name, headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- pages
def to_login(request: Request) -> RedirectResponse:
    nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(nxt)}", status_code=303)


@app.get("/", include_in_schema=False)
def index(request: Request):
    if not auth.has_role(request, "staff"):
        return to_login(request)
    return page("index.html")


@app.get("/builder", include_in_schema=False)
def builder_page(request: Request):
    if not auth.has_role(request, "admin"):
        return to_login(request)
    return page("builder.html")


@app.get("/login", include_in_schema=False)
def login_page():
    return page("login.html")


@app.post("/api/login")
async def api_login(request: Request):
    ip = request.client.host if request.client else "?"
    wait = auth.locked_for(ip)
    if wait:
        raise HTTPException(429, f"ลองผิดหลายครั้ง กรุณารอ {wait} วินาที")
    body = await request.json()
    role = auth.check_password(str(body.get("username") or "").strip(), str(body.get("password") or ""))
    if not role:
        auth.record_fail(ip)
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    auth.clear_fails(ip)
    nxt = str(body.get("next") or "/")
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    if nxt.startswith("/builder") and role != "admin":
        raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์จัดการแผนที่")
    res = JSONResponse({"ok": True, "role": role, "next": nxt})
    res.set_cookie(auth.COOKIE, auth.make_cookie(body["username"], role), max_age=int(auth.SESSION_HOURS * 3600),
                   httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return res


@app.get("/logout", include_in_schema=False)
def logout():
    res = RedirectResponse("/login", status_code=303)
    res.delete_cookie(auth.COOKIE)
    return res


@app.get("/api/me")
def api_me(request: Request):
    sess = auth.read_cookie(request.cookies.get(auth.COOKIE))
    return {"user": sess["user"] if sess else None, "role": sess["role"] if sess else None,
            "staff_locked": auth.required_role("staff"), "admin_locked": auth.required_role("admin")}


@app.get("/t/{token}", include_in_schema=False)
def patient_page(token: str):
    return page("patient.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(config.STATIC_DIR / "img" / "logo.png")


# ---------------------------------------------------------------- public API
@app.get("/api/config")
def api_config():
    return {"hospital": config.HOSPITAL_NAME, "demo": config.IS_DEMO, "poll_seconds": config.POLL_SECONDS}


@app.get("/api/map")
def api_map():
    hmap = mapdata.published()
    if not hmap:
        raise HTTPException(404, "ยังไม่มีแผนที่ที่เผยแพร่")
    return hmap.public_doc()


@app.get("/api/health")
def api_health():
    w = state["worker"]
    return {"time": clock.now().isoformat(), "hosxp": w.health if w else None,
            "map_version": state["builder"].latest.get("map_version")}


def _token_vn(token: str) -> str:
    with db.engine.connect() as conn:
        row = conn.execute(sa.select(db.navigation_tokens).where(db.navigation_tokens.c.token == token)).mappings().first()
    if not row or row["revoked"] or row["expires_at"] < clock.now():
        raise HTTPException(404, "ใบนำทางไม่ถูกต้องหรือหมดอายุ")
    return row["vn"]


@app.get("/api/t/{token}")
def api_patient(token: str, accessible: bool = False):
    vn = _token_vn(token)
    view = patient_view(state["builder"], vn, accessible)
    if not view:
        raise HTTPException(404, "ไม่พบข้อมูลการรับบริการ")
    view.pop("vn", None)
    return view


def _sse(data) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.get("/api/t/{token}/stream")
async def api_patient_stream(token: str, request: Request, accessible: bool = False):
    vn = _token_vn(token)

    async def gen():
        q = hub.subscribe()
        last = None
        try:
            while not await request.is_disconnected():
                view = await asyncio.to_thread(patient_view, state["builder"], vn, accessible)
                if view:
                    view.pop("vn", None)
                    payload = _sse(view)
                    if payload != last:
                        last = payload
                        yield payload
                try:
                    await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- staff API
@app.get("/api/live")
def api_live(_=Depends(staff)):
    return state["builder"].latest


@app.get("/api/stream")
async def api_stream(request: Request, _=Depends(staff)):
    async def gen():
        q = hub.subscribe()
        try:
            yield _sse(state["builder"].latest)
            while not await request.is_disconnected():
                try:
                    snap = await asyncio.wait_for(q.get(), timeout=20)
                    yield _sse(snap)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/visits/{vn}")
def api_visit(vn: str, _=Depends(staff)):
    view = patient_view(state["builder"], vn)
    if not view:
        raise HTTPException(404, "ไม่พบ VN")
    return view


@app.get("/api/route")
def api_route(to: str, from_: str | None = None, accessible: bool = False, _=Depends(staff)):
    hmap = mapdata.published()
    route = hmap.route(from_, to, accessible) if hmap else None
    if not route:
        raise HTTPException(404, "ไม่พบห้อง")
    return route


@app.post("/api/demo/rush")
async def api_rush(request: Request, _=Depends(staff)):
    sim = state["simulator"]
    if not sim:
        raise HTTPException(400, "ใช้ได้เฉพาะโหมดสาธิต")
    body = await request.json()
    sim.rush = bool(body.get("on"))
    return {"rush": sim.rush}


@app.get("/slip/{vn}", response_class=HTMLResponse, include_in_schema=False)
def slip(vn: str, request: Request):
    if not auth.has_role(request, "staff"):
        return to_login(request)
    """ใบนำทางพร้อม QR Code (พิมพ์จากเครื่องพิมพ์ใบคิว 80 มม.)"""
    with db.engine.begin() as conn:
        visit = conn.execute(sa.select(db.patient_visits).where(db.patient_visits.c.vn == vn)).mappings().first()
        if not visit:
            raise HTTPException(404, "ไม่พบ VN")
        token = get_or_create_token(conn, vn)
    base = config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    url = f"{base}/t/{token}"
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    svg = svg[svg.find("<svg"):]
    snap_p = state["builder"].by_vn.get(vn) or {}
    queue = snap_p.get("q") or str(visit["oqueue"] or "")
    hn = str(visit["hn"] or "")
    hn_masked = ("*" * max(0, len(hn) - 4)) + hn[-4:]
    tpl = (config.STATIC_DIR / "slip.html").read_text(encoding="utf-8")
    values = {
        "HOSPITAL": config.HOSPITAL_NAME, "QUEUE": queue, "HN": hn_masked,
        "DATE": f"{visit['vstdate'].strftime('%d/%m/')}{visit['vstdate'].year + 543} {str(visit['vsttime'] or '')[:5]}",
        "DEST": snap_p.get("dest_name") or "", "QR": svg, "URL": url,
    }
    for k, v in values.items():
        tpl = tpl.replace("{{" + k + "}}", v if k == "QR" else html.escape(str(v)))
    return HTMLResponse(tpl)


# ---------------------------------------------------------------- Map Builder API
@app.get("/api/admin/map")
def admin_map(_=Depends(admin)):
    with db.engine.connect() as conn:
        doc = mapdata.load_draft(conn)
        versions = db.rows(conn.execute(sa.select(db.map_versions.c.id, db.map_versions.c.published_at, db.map_versions.c.note)
                                        .order_by(db.map_versions.c.id.desc()).limit(20)))
    return {"draft": doc, "versions": versions}


@app.put("/api/admin/map")
async def admin_save(request: Request, _=Depends(admin)):
    doc = await request.json()
    try:
        with db.engine.begin() as conn:
            mapdata.save_draft(conn, doc)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/admin/publish")
async def admin_publish(request: Request, _=Depends(admin)):
    body = await request.json()
    try:
        with db.engine.begin() as conn:
            if body.get("doc"):
                mapdata.save_draft(conn, body["doc"])
            version = mapdata.publish(conn, body.get("note") or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "version": version}


@app.post("/api/admin/route-test")
async def admin_route_test(request: Request, _=Depends(admin)):
    body = await request.json()
    doc = body.get("doc")
    if not doc:
        with db.engine.connect() as conn:
            doc = mapdata.load_draft(conn)
    hmap = mapdata.HospitalMap(doc)
    route = hmap.route(body.get("from") or None, body.get("to"), bool(body.get("accessible")))
    if not route:
        raise HTTPException(400, "เลือกห้องปลายทางไม่ถูกต้อง")
    return route


@app.post("/api/admin/plan-image")
async def admin_upload(file: UploadFile = File(...), _=Depends(admin)):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "svg", "webp"):
        raise HTTPException(400, "รองรับไฟล์ PNG, JPG, SVG, WEBP")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 15MB")
    name = f"plan_{hashlib.sha1(data).hexdigest()[:16]}.{ext}"
    (config.UPLOAD_DIR / name).write_bytes(data)
    return {"path": f"/uploads/{name}"}


@app.get("/api/admin/hosxp-departments")
def admin_departments(_=Depends(admin)):
    """รายชื่อหน่วยบริการจาก HOSxP (kskdepartment) เพื่อช่วยจับคู่ห้อง"""
    w = state["worker"]
    if not w:
        return []
    try:
        with w.source.engine.connect() as conn:
            res = conn.execute(sa.text("SELECT depcode, department FROM kskdepartment ORDER BY depcode"))
            return [{"depcode": str(r[0]), "name": r[1]} for r in res]
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=502)

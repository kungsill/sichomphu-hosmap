# ติดตั้งใช้งานจริง (Production) — Smart Hospital Navigation รพ.สีชมพู

เอกสารนี้สำหรับฝ่าย IT ที่จะนำระบบขึ้นเครื่อง Server ของโรงพยาบาล ให้ผู้ป่วยเปิดจากมือถือได้ทั้งใน Wi-Fi และเน็ตมือถือ

```
มือถือผู้ป่วย / จอทีวี / เครื่องเจ้าหน้าที่
            │  HTTPS (443)   https://nav.scphos.go.th
            ▼
   Caddy หรือ nginx  (ออกใบรับรอง HTTPS, ส่งต่อ, ปิด buffering ของ SSE)
            │  http://127.0.0.1:8090
            ▼
   Smart Hospital Navigation (FastAPI, รันเป็น Windows Service / systemd)
        │                                   │
        ▼ อ่านอย่างเดียว                     ▼ อ่าน/เขียน
   HOSxP (MySQL: ovst, opd_dep_queue, neoq_track_ovst)   ฐานข้อมูลระบบนำทาง hospital_navigation (MySQL/MariaDB)
```

## 1. เตรียมเครื่อง

| รายการ | ขั้นต่ำ |
|---|---|
| OS | Windows Server 2016+ หรือ Ubuntu 22.04+ |
| CPU / RAM / Disk | 2 core / 4 GB / 20 GB |
| ซอฟต์แวร์ | Python 3.11+, Git, MySQL/MariaDB (สำหรับฐานข้อมูลระบบนำทาง) |
| เครือข่าย | เข้าถึง HOSxP MySQL ได้ (พอร์ต 3306) และเปิดพอร์ต 443 ให้ผู้ป่วย |

## 2. ติดตั้งโปรแกรม

```
git clone https://github.com/kungsill/sichomphu-hosmap.git C:\hosmap
cd C:\hosmap
copy .env.example .env
```

แก้ `.env`:

```
HOSXP_MODE=mysql
HOSXP_DB_URL=mysql+pymysql://<user_อ่านอย่างเดียว>:<รหัส>@<IP HOSxP>:3306/<ชื่อฐาน>?charset=utf8mb4
NAV_DB_URL=mysql+pymysql://nav:<รหัส>@127.0.0.1:3306/hospital_navigation?charset=utf8mb4
PUBLIC_BASE_URL=https://nav.scphos.go.th
STAFF_PASSWORD=<รหัสหน้าเจ้าหน้าที่>
ADMIN_PASSWORD=<รหัส Map Builder>
SESSION_SECRET=<สุ่มยาว ๆ เช่น จาก python -c "import secrets;print(secrets.token_hex(32))">
```

สร้างฐานข้อมูลระบบนำทางและบัญชี: ดู `deploy/mysql_setup.sql` (รันด้วยบัญชีผู้ดูแล MySQL)
ระบบจะสร้างตารางเองตอนเปิดครั้งแรก และโหลดแผนที่จาก `maps/sichomphu_map.json`

ทดสอบ: `run.bat` แล้วเปิด http://127.0.0.1:8090/api/health ต้องได้ `"ok": true`

## 3. รันเป็น Service (เปิดเองเมื่อเครื่องรีสตาร์ต)

**Windows:** ดาวน์โหลด NSSM (https://nssm.cc) แล้วรัน `deploy\install_service.bat` ด้วยสิทธิ์ Administrator
**Linux:** คัดลอก `deploy/hosmap.service` ไป `/etc/systemd/system/` แล้ว `systemctl enable --now hosmap`

## 4. HTTPS + ชื่อโดเมน

1. ขอให้ผู้ดูแล DNS ของ `scphos.go.th` เพิ่มระเบียน `nav` ชี้มาที่ IP สาธารณะของเครื่องนี้ (หรือ NAT พอร์ต 443 จาก Firewall)
2. เลือกอย่างใดอย่างหนึ่ง
   - **Caddy (ง่ายสุด ออกใบรับรองให้อัตโนมัติ):** ใช้ `deploy/Caddyfile`
   - **nginx:** ใช้ `deploy/nginx.conf` + ใบรับรองของหน่วยงาน
3. ตั้ง `PUBLIC_BASE_URL=https://nav.scphos.go.th` แล้วรีสตาร์ต service — QR บนป้าย/ใบนำทางจะชี้ที่อยู่นี้

> ต้องปิด buffering ของ `/api/stream`, `/api/t/*/stream`, `/api/tv/*/stream` (SSE) — ไฟล์ตัวอย่างตั้งไว้แล้ว
> หน้าเจ้าหน้าที่ (`/`, `/builder`) มีรหัสผ่านอยู่แล้ว แต่ถ้าไม่ต้องการให้เปิดจากภายนอกเลย จำกัด IP ใน nginx/Caddy ได้ (มีตัวอย่าง)

## 5. ปุ่ม "ดูแผนที่" ในหน้าสถานะคิวของ neoQ

ส่ง `deploy/neoq_button.html` ให้ผู้ดูแล neoQ — เพิ่มปุ่มในหน้า `patient_status.aspx` ลิงก์ไป
`https://nav.scphos.go.th/q?vn=<VN เดียวกับในลิงก์ของหน้า>` ผู้ป่วยจะกรอกแค่ HN 4 ตัวท้าย

## 6. จอทีวีหน้าห้องรอ

เปิดเบราว์เซอร์แบบเต็มจอ (kiosk) ที่ `https://nav.scphos.go.th/tv?f=<รหัสโซน>` — เปิด `/tv` เพื่อเลือกโซน
ต้องการเสียงเรียกคิวเพิ่ม `&voice=1` (ค่าเริ่มต้นปิด เพราะ neoQ มีเสียงเรียกอยู่แล้ว)
ตัวอย่าง Chrome kiosk: `chrome.exe --kiosk --autoplay-policy=no-user-gesture-required "https://nav.scphos.go.th/tv?f=flr_opd_1"`

## 7. สำรองข้อมูล

`deploy/backup.bat` (Windows Task Scheduler ทุกคืน) หรือ `deploy/backup.sh` (cron) — สำรอง
1. แผนที่ฉบับเผยแพร่ → `maps/sichomphu_map.json` (ไม่มีข้อมูลผู้ป่วย)
2. ฐานข้อมูลระบบนำทาง (มีประวัติการรับบริการ = ข้อมูลผู้ป่วย เก็บในที่ปลอดภัย) เก็บย้อนหลัง 30 วัน

## 8. อัปเดตเวอร์ชัน

```
cd C:\hosmap
git pull
.venv\Scripts\python -m pip install -r requirements.txt
nssm restart hosmap            (Linux: systemctl restart hosmap)
.venv\Scripts\python -m app.mapio import    ← เฉพาะเมื่อมีการแก้แผนที่ใน Git
```

## 9. ตรวจสุขภาพระบบ

- `GET /api/health` → `hosxp.ok`, `last_sync`, `fail_count` (ต่อเข้าระบบเฝ้าระวังได้)
- จุดสีบนหน้าจอเจ้าหน้าที่: เขียว = ปกติ, แดง = ขาดการเชื่อมต่อ (ชี้เมาส์ดูสาเหตุ)
- ถ้า HOSxP ล่ม ระบบเก็บสถานะเดิมไว้และกลับมาซิงก์เองเมื่อเชื่อมต่อได้

## 10. ความปลอดภัย / PDPA

- บัญชี HOSxP สิทธิ์ `SELECT` เท่านั้น (ระบบสั่ง `READ ONLY` ซ้ำอีกชั้น)
- หน้าผู้ป่วยเปิดด้วย token สุ่ม หรือเลขคิว/VN + HN 4 ตัวท้าย (มีกันเดา) ไม่แสดงชื่อ เลขบัตร หรือสัญญาณชีพ
- จอทีวีแสดงเฉพาะเลขคิว
- `.env` และ `data/` ห้ามขึ้น Git / ห้ามแชร์ในกลุ่มแชท

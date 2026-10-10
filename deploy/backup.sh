#!/usr/bin/env sh
# สำรองแผนที่ + ฐานข้อมูลระบบนำทาง (cron: 0 2 * * * /opt/hosmap/deploy/backup.sh) เก็บย้อนหลัง 30 วัน
cd "$(dirname "$0")/.." || exit 1
D=$(date +%Y%m%d)
mkdir -p backups
.venv/bin/python -m app.mapio export "backups/map_$D.json"
[ -f data/hospital_navigation.db ] && cp data/hospital_navigation.db "backups/nav_$D.db"
# MySQL (ถ้าใช้): mysqldump -u nav -pCHANGE_ME hospital_navigation > "backups/nav_$D.sql"
find backups -type f -mtime +30 -delete
echo "สำรองแล้ว: backups/*_$D.*"

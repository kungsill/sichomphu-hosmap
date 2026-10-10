-- =====================================================================
--  ฐานข้อมูลระบบนำทาง (แยกจาก HOSxP) — รันด้วยบัญชีผู้ดูแล MySQL/MariaDB
--  เปลี่ยน 'CHANGE_ME' เป็นรหัสผ่านจริง แล้วใส่ใน NAV_DB_URL ของไฟล์ .env
-- =====================================================================
CREATE DATABASE IF NOT EXISTS hospital_navigation CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'nav'@'localhost' IDENTIFIED BY 'CHANGE_ME';
GRANT ALL PRIVILEGES ON hospital_navigation.* TO 'nav'@'localhost';

-- ---------------------------------------------------------------------
--  (ทำบนเครื่อง HOSxP) บัญชีอ่านอย่างเดียวสำหรับระบบนำทาง
--  เปลี่ยน <HOSXP_DB> เป็นชื่อฐาน HOSxP จริง และ 'IP_SERVER_NAV' เป็น IP เครื่องระบบนำทาง
-- ---------------------------------------------------------------------
-- CREATE USER 'nav_ro'@'IP_SERVER_NAV' IDENTIFIED BY 'CHANGE_ME';
-- GRANT SELECT ON <HOSXP_DB>.ovst              TO 'nav_ro'@'IP_SERVER_NAV';
-- GRANT SELECT ON <HOSXP_DB>.patient           TO 'nav_ro'@'IP_SERVER_NAV';
-- GRANT SELECT ON <HOSXP_DB>.opdscreen         TO 'nav_ro'@'IP_SERVER_NAV';
-- GRANT SELECT ON <HOSXP_DB>.opd_dep_queue     TO 'nav_ro'@'IP_SERVER_NAV';
-- GRANT SELECT ON <HOSXP_DB>.neoq_track_ovst   TO 'nav_ro'@'IP_SERVER_NAV';
-- GRANT SELECT ON <HOSXP_DB>.kskdepartment     TO 'nav_ro'@'IP_SERVER_NAV';
FLUSH PRIVILEGES;

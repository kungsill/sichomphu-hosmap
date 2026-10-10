# ติดตั้งระบบนำทางให้รันอัตโนมัติเมื่อเปิดเครื่อง (ต้องใช้สิทธิ์ Administrator)
#  - มี NSSM ใน PATH → ติดตั้งเป็น Windows Service ชื่อ "hosmap"
#  - ไม่มี NSSM     → ใช้ Task Scheduler ของ Windows (ไม่ต้องดาวน์โหลดอะไร) งานชื่อ "HospitalNavigation"
#    เริ่มตอนเปิดเครื่อง (ก่อนมีคนล็อกอิน) ด้วยบัญชี SYSTEM และเปิดใหม่เองถ้าหยุดทำงาน
#  - เพิ่มกฎ Windows Firewall ให้เครื่องอื่นใน LAN เข้า port 8090 ได้ (เฉพาะเครือข่าย Domain/Private)
$ErrorActionPreference = "Stop"
$App = (Resolve-Path "$PSScriptRoot\..").Path
$Port = 8090
$Runner = Join-Path $App "deploy\run_server.bat"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host "กรุณาคลิกขวาที่ install_service.bat แล้วเลือก Run as administrator" -ForegroundColor Red; exit 1 }
if (-not (Test-Path "$App\.venv\Scripts\python.exe")) { Write-Host "ไม่พบ .venv — ติดตั้งตาม README ก่อน (python -m venv .venv แล้ว pip install -r requirements.txt)" -ForegroundColor Red; exit 1 }
if (-not (Test-Path "$App\.env")) { Write-Host "ไม่พบไฟล์ .env — คัดลอกจาก .env.example แล้วใส่ค่าการเชื่อม HOSxP ก่อน" -ForegroundColor Red; exit 1 }

# 1) ปิดเซิร์ฟเวอร์ที่เปิดค้างไว้ (เช่น รันจาก VS Code) เพื่อไม่ให้ port ชนกัน — ปิดเฉพาะ python เท่านั้น
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -like "python*") { Write-Host "ปิดเซิร์ฟเวอร์เดิม (PID $($p.Id))"; Stop-Process -Id $p.Id -Force }
}

# 2) ติดตั้ง
$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if ($nssm) {
    & nssm stop hosmap 2>$null | Out-Null
    & nssm remove hosmap confirm 2>$null | Out-Null
    & nssm install hosmap "$env:ComSpec" "/c `"$Runner`""
    & nssm set hosmap AppDirectory $App
    & nssm set hosmap DisplayName "Hospital Navigation (โรงพยาบาลสีชมพู)"
    & nssm set hosmap Start SERVICE_AUTO_START
    & nssm set hosmap AppExit Default Restart
    & nssm start hosmap
    $mode = "Windows Service (NSSM) ชื่อ hosmap"
} else {
    $name = "HospitalNavigation"
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    $action = New-ScheduledTaskAction -Execute "$env:ComSpec" -Argument "/c `"$Runner`"" -WorkingDirectory $App
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description "ระบบนำทางผู้ป่วย โรงพยาบาลสีชมพู (http://localhost:$Port)" | Out-Null
    Start-ScheduledTask -TaskName $name
    $mode = "Task Scheduler งานชื่อ $name (เริ่มเองเมื่อเปิดเครื่อง)"
}

# 3) Firewall: ให้เครื่องอื่นในโรงพยาบาลเข้าได้ (ไม่เปิดให้เครือข่ายสาธารณะ)
if (-not (Get-NetFirewallRule -DisplayName "Hospital Navigation $Port" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "Hospital Navigation $Port" -Direction Inbound -Protocol TCP -LocalPort $Port `
        -Action Allow -Profile Domain,Private | Out-Null
}

# 4) ตรวจว่าเปิดได้จริง
Write-Host "รอระบบเริ่มทำงาน..."
$ok = $false
for ($i = 0; $i -lt 30 -and -not $ok; $i++) {
    Start-Sleep -Seconds 2
    try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3; $ok = $true } catch { }
}
if ($ok) {
    Write-Host "ติดตั้งสำเร็จ: $mode" -ForegroundColor Green
    Write-Host ("HOSxP: " + $(if ($h.hosxp.ok) { "เชื่อมต่อได้ ($($h.hosxp.visits) visit วันนี้)" } else { "ยังเชื่อมไม่ได้ — ดู data\service.log" }))
    $ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | ForEach-Object { $_.IPAddress }
    $ips | ForEach-Object { Write-Host "เปิดจากเครื่องอื่น: http://$($_):$Port/" }
} else {
    Write-Host "ระบบยังไม่ตอบ — ดูรายละเอียดใน $App\data\service.log" -ForegroundColor Yellow
}

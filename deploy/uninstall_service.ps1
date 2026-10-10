# ถอนการติดตั้ง (ต้องใช้สิทธิ์ Administrator) — ไม่ลบข้อมูลใน data\
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host "กรุณาเรียกใช้ด้วยสิทธิ์ Administrator" -ForegroundColor Red; exit 1 }
if (Get-Command nssm -ErrorAction SilentlyContinue) { & nssm stop hosmap 2>$null | Out-Null; & nssm remove hosmap confirm 2>$null | Out-Null }
$t = Get-ScheduledTask -TaskName "HospitalNavigation" -ErrorAction SilentlyContinue
if ($t) { Stop-ScheduledTask -TaskName "HospitalNavigation" -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName "HospitalNavigation" -Confirm:$false }
Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -like "python*") { Stop-Process -Id $p.Id -Force }
}
Remove-NetFirewallRule -DisplayName "Hospital Navigation 8090" -ErrorAction SilentlyContinue
Write-Host "ถอนการติดตั้งแล้ว (ข้อมูลใน data\ ยังอยู่)" -ForegroundColor Green

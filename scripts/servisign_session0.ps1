# servisign_session0.ps1 -- run ELEVATED (servisign_utils.start_servisign_session0 launches it via RunAs).
# Starts the TCGServiSign MAIN executable ("TCGServiSign.exe 0") as SYSTEM in session 0 through a
# one-shot scheduled task, so its winscard.dll loads in the local (non-RDP) context and can see the
# smart-card reader attached to THIS machine even while the user works over Remote Desktop.
#
# Why not the Monitor: TCGServiSignMonitor.exe exits immediately when there is no desktop (session 0).
# Why a scheduled task: it is the supported way to launch a process as SYSTEM without a service wrapper.
# ASCII only: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI and fails to parse non-ASCII.
#
# Exit codes: 0 = 56420 is listening and owned by a session-0 process; 1 = failed (see log).
param([string]$LogPath = "$env:TEMP\servisign_session0.log")

$exe = "C:\Program Files (x86)\TCG\TCGServiSign\TCGServiSign.exe"
$dir = "C:\Program Files (x86)\TCG\TCGServiSign"
$task = "TCGServiSign_Session0"
function L($m) { ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $m) | Out-File $LogPath -Append -Encoding utf8 }

try {
  L "start (elevated=$(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)))"
  if (-not (Test-Path $exe)) { L "exe not found: $exe"; exit 1 }

  # Stop whatever copy is running in a user session (a SYSTEM/session-0 copy, if any, is left alone
  # only if it already owns the port; otherwise it is restarted too so we end in a known state).
  Get-Process -Name "TCGServiSign*" -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2

  Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
  $action    = New-ScheduledTaskAction -Execute $exe -Argument "0" -WorkingDirectory $dir
  $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
  $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName $task
  L "task $task registered and started"

  $ok = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $l = Get-NetTCPConnection -LocalPort 56420 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($l) {
      $p = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue
      if ($p -and $p.SessionId -eq 0) { $ok = $true; L ("56420 listening, pid=" + $p.Id + " session=0 after " + ($i*0.5) + "s"); break }
    }
  }
  if (-not $ok) { L "56420 not owned by a session-0 process within 20s"; exit 1 }
  exit 0
} catch {
  L ("EXCEPTION: " + $_.Exception.Message)
  exit 1
}

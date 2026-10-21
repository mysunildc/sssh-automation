# servisign_session0_watchdog.ps1 -- run as SYSTEM by the scheduled task "TCGServiSign_Session0_Watchdog"
# (registered by install_servisign_watchdog.ps1). Keeps the TCGServiSign main program in session 0 so
# the smart-card reader attached to THIS machine stays usable while the user works over Remote Desktop.
#
# Why: ensure_servisign() in main.py only fixes things when main.py runs. In between, the vendor
# Monitor restarts the main program in the user session on every logon / RDP reconnect
# (2026-10-21: all ServiSign mains restarted 1s after reconnect), and a main program started inside
# an RDP session has its winscard redirected to the RDP client -> host reader invisible.
#
# OK state: 56420 is listening and the owner is TCGServiSign.exe in session 0 -> do nothing.
# Otherwise: run servisign_session0.ps1 (stops the user-session copies, starts the main as SYSTEM).
# ASCII only: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI and fails to parse non-ASCII.
param([string]$LogPath = "$env:ProgramData\TCGServiSign_Session0\watchdog.log")

$launcher = Join-Path $PSScriptRoot "servisign_session0.ps1"
$exe = "C:\Program Files (x86)\TCG\TCGServiSign\TCGServiSign.exe"

New-Item -ItemType Directory -Force (Split-Path $LogPath) | Out-Null
function L($m) { ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $m) | Out-File $LogPath -Append -Encoding utf8 }

# Keep the log small: rotate at 1 MB, keep one old file.
if ((Test-Path $LogPath) -and (Get-Item $LogPath).Length -gt 1MB) { Move-Item $LogPath "$LogPath.1" -Force }

if (-not (Test-Path $exe)) { L "exe not found: $exe"; exit 1 }

$owner = $null
$l = Get-NetTCPConnection -LocalPort 56420 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($l) { $owner = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue }
if ($owner -and $owner.SessionId -eq 0 -and $owner.ProcessName -eq "TCGServiSign") { exit 0 }

$why = if ($owner) { "56420 owned by $($owner.ProcessName) pid=$($owner.Id) session=$($owner.SessionId)" } else { "56420 not listening" }
L "$why -> switching TCGServiSign to session 0"
& powershell -NoProfile -ExecutionPolicy Bypass -File $launcher -LogPath $LogPath
L "launcher exit=$LASTEXITCODE"
exit $LASTEXITCODE

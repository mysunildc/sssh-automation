# install_servisign_watchdog.ps1 -- run ELEVATED once per machine (re-run after moving the repo).
# Registers "TCGServiSign_Session0_Watchdog": SYSTEM runs servisign_session0_watchdog.ps1
#   - at startup (before anyone logs on, so session 0 grabs 56420 first),
#   - 15s after every logon / RDP connect / reconnect (the vendor Monitor restarts the main
#     program in the user session at those moments),
#   - every 2 minutes as a safety net (the main program sometimes dies on its own).
# -Uninstall removes the watchdog task.
# ASCII only: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI and fails to parse non-ASCII.
param([switch]$Uninstall)

$task = "TCGServiSign_Session0_Watchdog"
$ErrorActionPreference = "Stop"

# A non-elevated Register/Unregister of a SYSTEM task fails without stopping the script, so check first.
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { "must run elevated (Run as administrator)"; exit 1 }

function TaskExists { [bool](Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) }

if ($Uninstall) {
  if (TaskExists) { Unregister-ScheduledTask -TaskName $task -Confirm:$false }
  if (TaskExists) { "failed to remove $task"; exit 1 }
  "removed $task"
  exit 0
}

$watchdog = Join-Path $PSScriptRoot "servisign_session0_watchdog.ps1"
if (-not (Test-Path $watchdog)) { "not found: $watchdog"; exit 1 }
$esc = [Security.SecurityElement]::Escape($watchdog)

# LocalSessionManager/Operational: 21 = logon (incl. new RDP session), 25 = reconnect (console or RDP).
$q = @'
&lt;QueryList&gt;&lt;Query Id="0"&gt;&lt;Select Path="Microsoft-Windows-TerminalServices-LocalSessionManager/Operational"&gt;*[System[(EventID=21 or EventID=25)]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;
'@

$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Keep TCGServiSign main program in session 0 so the host smart-card reader works over RDP (sssh-automation).</Description></RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled><Delay>PT20S</Delay></BootTrigger>
    <EventTrigger><Enabled>true</Enabled><Delay>PT15S</Delay><Subscription>$($q.Trim())</Subscription></EventTrigger>
    <TimeTrigger>
      <Repetition><Interval>PT2M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary><Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Hidden>false</Hidden>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$esc"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

try {
  Register-ScheduledTask -TaskName $task -Xml $xml -Force | Out-Null
  Start-ScheduledTask -TaskName $task
} catch {
  "failed to register $task : $($_.Exception.Message)"
  exit 1
}
if (-not (TaskExists)) { "failed to register $task"; exit 1 }
"registered and started $task -> $watchdog"
exit 0

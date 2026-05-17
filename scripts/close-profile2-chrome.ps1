# close-profile2-chrome.ps1
# 關閉所有「Profile 2」的 chrome.exe，讓 Selenium 能重新接管該 profile。
# 不影響其他 Chrome profile 的視窗。
$procs = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object { $_.CommandLine -like "*Profile 2*" }
if ($procs) {
    Write-Host ("找到 {0} 個 Profile 2 chrome.exe，正在關閉..." -f $procs.Count)
    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Write-Host "已關閉。"
} else {
    Write-Host "沒有 Profile 2 chrome.exe 在運行。"
}

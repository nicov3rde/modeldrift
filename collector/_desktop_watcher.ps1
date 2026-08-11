# Watches for the collector's own Chrome windows (identified by the
# --remote-debugging-port flag Playwright/browser_use always sets, which a
# normal user-launched Chrome never has) and relocates each one to the
# "ModelDrift" virtual desktop the instant its window handle exists.
# Run detached; stop with: Get-Process powershell | Where CommandLine -match
# '_desktop_watcher' | Stop-Process, or just close the Modeldrift desktop.

Import-Module VirtualDesktop

$targetDesktop = Get-Desktop -Index "ModelDrift"
if (-not $targetDesktop) {
    Write-Output "ModelDrift desktop not found - exiting"
    exit 1
}

$movedPids = New-Object System.Collections.Generic.HashSet[int]

while ($true) {
    $procs = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match '--remote-debugging-port=' -and $_.CommandLine -notmatch '--type=' }
    foreach ($p in $procs) {
        if (-not $movedPids.Contains($p.ProcessId)) {
            try {
                $proc = Get-Process -Id $p.ProcessId -ErrorAction Stop
                if ($proc.MainWindowHandle -ne 0) {
                    Move-Window -Desktop $targetDesktop -Hwnd $proc.MainWindowHandle -ErrorAction Stop | Out-Null
                    [void]$movedPids.Add($p.ProcessId)
                    Write-Output "$(Get-Date -Format 'HH:mm:ss') moved PID $($p.ProcessId) to ModelDrift desktop"
                }
            } catch {
                # window not ready yet, or process already exited - retry next poll
            }
        }
    }
    Start-Sleep -Milliseconds 500
}

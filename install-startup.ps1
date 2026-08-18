# Register Super Jarvis to start at Windows logon. No admin required. Runs on battery.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$script = Join-Path $PSScriptRoot "serve.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "SuperJarvis" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
& $script
Get-ScheduledTask -TaskName "SuperJarvis" | Format-List TaskName, State
Write-Host "Installed SuperJarvis logon task (battery ok). HUD: http://127.0.0.1:8787"

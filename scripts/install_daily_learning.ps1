# Installs the NEXUS daily autonomous learning task for the current Windows user.
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TaskName = "NEXUS Daily Autonomous Learning"
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$DotVenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $PythonPath = $VenvPython
} elseif (Test-Path $DotVenvPython) {
    $PythonPath = $DotVenvPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw "Python was not found. Create the NEXUS virtual environment first."
    }
    $PythonPath = $PythonCommand.Source
}

if (-not (Test-Path (Join-Path $ProjectRoot "learning\daily_worker.py"))) {
    throw "learning\daily_worker.py was not found. Pull the latest NEXUS changes first."
}

$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "-m learning.daily_worker" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "5:00PM"
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Runs NEXUS autonomous learning daily at 5:00 PM (Windows local time), only while the current user is logged in." -Force | Out-Null

Write-Host ""
Write-Host "NEXUS daily learning task installed." -ForegroundColor Green
Write-Host "Schedule: Every day at 5:00 PM (Windows local time)."
Write-Host "Runs only while you are logged into Windows."
Write-Host "Python: $PythonPath"
Write-Host "Project: $ProjectRoot"
Write-Host ""
Write-Host "Log file: $ProjectRoot\logs\daily_learning.log"
Write-Host ('To test it now, run: "{0}" -m learning.daily_worker --force' -f $PythonPath)

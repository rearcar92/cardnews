param(
    [string]$TaskName = "Morning Insight Cards",
    [string]$At = "08:00"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runner = Join-Path $ProjectRoot "scripts\run_morning_cardnews.ps1"
$Powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

$Action = New-ScheduledTaskAction `
    -Execute $Powershell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Generate a personal morning news card HTML every weekday at $At." `
    -Force | Out-Null

Write-Output "Registered scheduled task: $TaskName at $At on weekdays"

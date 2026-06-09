param(
    [switch]$Open,
    [switch]$Force,
    [switch]$Email
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PythonScript = Join-Path $ProjectRoot "src\morning_news.py"
$LogDir = Join-Path $ProjectRoot "logs"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$PythonExe = "python"

if (Test-Path $BundledPython) {
    $PythonExe = $BundledPython
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$Arguments = @($PythonScript)
if ($Force) {
    $Arguments += "--force"
}
if ($Email) {
    $Arguments += "--email"
}

$OutputPath = & $PythonExe @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Morning Insight Cards generation failed. Check logs\morning-news.log"
}

if ($Open -and $OutputPath -and (Test-Path $OutputPath)) {
    Start-Process $OutputPath
}

Write-Output $OutputPath

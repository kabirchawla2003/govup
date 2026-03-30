$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { Join-Path $RootDir ".venv" }
$PythonExe = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$IncludeDev = if ($env:INCLUDE_DEV) { $env:INCLUDE_DEV } else { "1" }

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonExe -m venv $VenvDir
}
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $RootDir "requirements.txt")

if ($IncludeDev -eq "1") {
    & $VenvPython -m pip install -r (Join-Path $RootDir "requirements-dev.txt")
}

$EnvPath = Join-Path $RootDir ".env"
if (-not (Test-Path -LiteralPath $EnvPath)) {
    Copy-Item (Join-Path $RootDir ".env.example") $EnvPath
}

$DataDir = Join-Path $RootDir "data"
if (-not (Test-Path -LiteralPath $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
}

Write-Host "Installation complete."
Write-Host ""
Write-Host "Virtual environment: $VenvDir"
Write-Host ""
Write-Host "Activate:"
Write-Host "  $VenvDir\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Run the API:"
Write-Host "  uvicorn src.main:app --reload"
Write-Host ""
Write-Host "OpenClaw is optional and must be installed separately if you need browser-backed live scraping."

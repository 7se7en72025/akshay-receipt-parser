param([switch]$Setup)
$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspaceRoot
$workspacePython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $workspacePython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python environment creation failed." }
    $Setup = $true
}
if ($Setup) {
    & $workspacePython -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
    Push-Location -LiteralPath (Join-Path $workspaceRoot "frontend")
    try {
        bun install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
        bun run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath (Join-Path $workspaceRoot "frontend\dist\index.html"))) {
    throw "Run this script with -Setup to build the frontend first."
}
Write-Host "Akshay invoice workspace: http://127.0.0.1:8001"
Write-Host "Keep this process running. Press Ctrl+C to stop."
& $workspacePython -m uvicorn backend.main:app --host 127.0.0.1 --port 8001

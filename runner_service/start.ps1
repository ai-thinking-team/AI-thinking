$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found. Install Docker Desktop, enable Linux containers, and reopen PowerShell.'
}

docker info | Out-Null
docker build -t ai-thinking-code-runner:local runner_service
$pythonPath = Join-Path $repoRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) {
    $pythonPath = 'python'
}
& $pythonPath -m runner_service.server

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found. Install Docker Desktop, enable Linux containers, and reopen PowerShell.'
}

try {
    docker info | Out-Null
} catch {
    docker desktop start 2>$null | Out-Null
    $dockerReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            docker info | Out-Null
            $dockerReady = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $dockerReady) {
        throw 'Docker Desktop is not running. Start Docker Desktop once and retry the Coding page.'
    }
}
docker build -t ai-thinking-code-runner:local runner_service
$pythonPath = Join-Path $repoRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) {
    $pythonPath = 'python'
}
& $pythonPath -m runner_service.server

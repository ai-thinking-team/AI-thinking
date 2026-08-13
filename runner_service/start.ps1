$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found. Install Docker Desktop, enable Linux containers, and reopen PowerShell.'
}

docker info | Out-Null
docker build -t ai-thinking-code-runner:local runner_service
python -m runner_service.server

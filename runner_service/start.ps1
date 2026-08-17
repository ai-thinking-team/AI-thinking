param(
    [switch]$SkipBuild,
    [int]$Port = 8765,
    [int]$DockerReadyTimeoutSeconds = 60,
    [int]$ContainerTimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Resolve-DockerPath {
    $command = Get-Command docker -CommandType Application -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
        $candidates += Join-Path $env:ProgramFiles 'DockerDesktop\resources\bin\docker.exe'
    }
    if (${env:ProgramW6432}) {
        $candidates += Join-Path ${env:ProgramW6432} 'Docker\Docker\resources\bin\docker.exe'
        $candidates += Join-Path ${env:ProgramW6432} 'DockerDesktop\resources\bin\docker.exe'
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

$dockerPath = Resolve-DockerPath
if (-not $dockerPath) {
    throw 'Docker CLI was not found. Install Docker Desktop with the WSL 2 Linux-container backend, then reopen PowerShell.'
}
$dockerDirectory = Split-Path -Parent $dockerPath
if (($env:Path -split ';') -notcontains $dockerDirectory) {
    $env:Path = "$dockerDirectory;$env:Path"
}
Write-Host "Using Docker CLI: $dockerPath"

function Test-DockerReady {
    $process = Start-Process -FilePath $dockerPath -ArgumentList @('info') -WindowStyle Hidden -PassThru
    try {
        if (-not $process.WaitForExit(5000)) {
            $process.Kill()
            $process.WaitForExit()
            return $false
        }
        return $process.ExitCode -eq 0
    } finally {
        $process.Dispose()
    }
}

if (-not (Test-DockerReady)) {
    $desktopStart = Start-Process -FilePath $dockerPath -ArgumentList @('desktop', 'start') -WindowStyle Hidden -PassThru
    if (-not $desktopStart.WaitForExit(15000)) {
        $desktopStart.Kill()
        $desktopStart.WaitForExit()
    }
    $desktopStart.Dispose()
    $dockerReady = $false
    for ($attempt = 0; $attempt -lt $DockerReadyTimeoutSeconds; $attempt++) {
        if (Test-DockerReady) {
            $dockerReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $dockerReady) {
        throw "Docker Desktop did not become ready within $DockerReadyTimeoutSeconds seconds. Start Docker Desktop and confirm that 'docker info' works, then retry."
    }
}
$env:RUNNER_PORT = $Port
$env:RUNNER_IMAGE = 'ai-thinking-code-runner:local'
$env:DOCKER_BIN = $dockerPath
$env:RUNNER_CONTAINER_TIMEOUT_SECONDS = [string]$ContainerTimeoutSeconds
if ($SkipBuild) {
    Write-Host 'Skipping runner image build.'
} else {
    & $dockerPath build -t ai-thinking-code-runner:local runner_service
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker image build failed. Review the Docker output above and retry after fixing the reported issue.'
    }
}
$pythonPath = Join-Path $repoRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) {
    $pythonPath = 'python'
}
& $pythonPath -m runner_service.server

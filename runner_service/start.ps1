$ErrorActionPreference = 'Stop'

docker build -t ai-thinking-code-runner:local runner_service
python -m runner_service.server

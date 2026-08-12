# Local Coding Runner

This service is separate from Django. Django sends only Python source code and curated test-case IDs over HTTP.

## Start

1. On Windows Home, run PowerShell as Administrator and execute `powershell -ExecutionPolicy Bypass -File runner_service/enable_wsl_features.ps1`, then restart Windows.
2. Install and start Docker Desktop with the WSL 2 Linux-container backend.
3. From the repository root, run `powershell -ExecutionPolicy Bypass -File runner_service/start.ps1`.
4. Set `CODE_RUNNER_URL=http://127.0.0.1:8765` in `.env` and restart Django.

The executor container is removed after every request and runs with no network, a read-only root filesystem, a non-root user, all Linux capabilities dropped, a 128 MB memory limit, one CPU, a PID limit, and layered execution timeouts.

The runner service allows 15 seconds for Docker container startup and teardown by default, while learner execution inside the container remains limited to 2 seconds. Override the outer limit with `RUNNER_CONTAINER_TIMEOUT_SECONDS`; keep Django's `CODE_RUNNER_TIMEOUT_SECONDS` greater than that value (the supplied default is 20 seconds).

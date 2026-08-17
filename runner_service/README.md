# Local Coding Runner

This service is separate from Django. Django sends only Python source code and curated test-case IDs over HTTP.

## Start the local demo

1. On Windows Home, run PowerShell as Administrator and execute `powershell -ExecutionPolicy Bypass -File runner_service/enable_wsl_features.ps1`, then restart Windows.
2. Install and start Docker Desktop with the WSL 2 Linux-container backend.
3. In the project PowerShell, build and start the runner:

   ```powershell
   cd path\to\AI-thinking
   powershell -ExecutionPolicy Bypass -File .\runner_service\start.ps1
   ```

   Keep this terminal open. For a restart without rebuilding the image, use
   `powershell -ExecutionPolicy Bypass -File .\runner_service\start.ps1 -SkipBuild`.
4. Development settings already use `CODE_RUNNER_URL=http://127.0.0.1:8765` by default. If you
   override it in `.env`, use that same URL and restart Django.
5. From a second PowerShell, verify the complete local setup:

   ```powershell
   .\venv\Scripts\python.exe manage.py check_local_demo
   ```

   The command checks Django, all 210 Coding catalog entries and `http://127.0.0.1:8765/health`
   without sending learner code to the runner.

`start.ps1` finds Docker Desktop in the standard Windows installation locations and waits up to
60 seconds for the daemon. If it still reports that Docker CLI or Docker Desktop is unavailable,
install Docker Desktop with the WSL 2 Linux-container backend and confirm `docker info` works in a
new PowerShell. Container creation allows 30 seconds and execution transport allows 10 seconds;
learner code itself remains limited to 2 seconds. If the Django page reports `RUNNER_ERROR`, inspect the
runner terminal: the HTTP response includes Docker's diagnostic message (for example, an image-not-found
or Docker-Desktop-not-running error).

The auto-start feature can still launch the runner on the first code submission in local development
and allows up to 75 seconds for Docker startup/build. The explicit two-terminal workflow above is
easier to diagnose and reproduce. The runner is always separate from Django and learner code never
runs inside the Django process.

The executor container is removed after every request and runs with no network, a read-only root filesystem, a non-root user, all Linux capabilities dropped, a 128 MB memory limit, one CPU, a PID limit, and layered execution timeouts.

The runner service separates container creation (30 seconds), execution transport (10 seconds),
and cleanup (5 seconds) by default. Override them with `-ContainerCreateTimeoutSeconds`,
`-ContainerStartTimeoutSeconds`, and `-ContainerCleanupTimeoutSeconds`. These are infrastructure
guards; only the harness's 2-second result is reported as a learner-code `TIMEOUT`.

Evaluation statuses distinguish `OUTPUT_MISMATCH` for a failed public expected/actual check from
`LOGIC_ERROR` for a missing required function or a hidden boundary failure. Hidden failures never
return expected or actual values. Syntax, runtime, timeout, unavailable-runner, and passing results
remain `SYNTAX_ERROR`, `RUNTIME_ERROR`, `TIMEOUT`, `RUNNER_ERROR`, `NOT_EXECUTED`, and `PASSED`
respectively. `RUNNER_ERROR` means the infrastructure failed before a student result was
received; it is never presented as a learner-code timeout.

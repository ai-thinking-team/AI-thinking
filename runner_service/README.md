# Local Coding Runner (lightweight, no Docker)

This service is separate from Django. Django sends only Python source code and curated
test-case IDs over HTTP to `POST /execute`, and gets back a `{status, message, tests}`
verdict (`PASSED`, `FAILED`, `SYNTAX_ERROR`, `RUNTIME_ERROR`, `TIMEOUT`, or `NOT_EXECUTED`).

**This version has no sandboxing beyond a subprocess + a 2-second timeout.** It is meant
for one person testing their own learning flow locally — do not point it at code from
real, untrusted students. For that, build a container-based runner instead (network
disabled, read-only root filesystem, dropped capabilities, resource limits).

## Start

```sh
venv/bin/python runner_service/local_server.py
```

This listens on `http://127.0.0.1:8765` by default (override with `RUNNER_HOST`/`RUNNER_PORT`
env vars). Then set in `.env`:

```
CODE_RUNNER_URL=http://127.0.0.1:8765
```

Restart `manage.py runserver` (or any process that reads `.env` at startup) so Django
picks up the new setting. Without `CODE_RUNNER_URL` set, `coding_quiz` falls back to
`NOT_EXECUTED` for every submission — safe, but the "correct answer" branches
(Verification, direct-to-Teach-Back, passing a Revision) can never be reached.

## Files

- `harness.py` — the test catalog (`double_numbers`, `word_lengths`) and the logic that
  runs a learner's function against expected values, with a per-call timeout.
- `worker.py` — executes the learner's submitted source in a fresh subprocess so a crash
  or infinite loop in their code can't take down the runner itself.
- `local_server.py` — a plain `http.server` wrapper around `harness.execute()`. Single-
  threaded on purpose (the timeout uses `SIGALRM`, which only works on the main thread).

## Stop

`Ctrl-C` if running in the foreground, or find and kill the process (e.g.
`pkill -f runner_service/local_server.py`) if it was started in the background.

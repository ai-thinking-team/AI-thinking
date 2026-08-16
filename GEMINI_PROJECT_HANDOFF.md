# Gemini Project Handoff

This document describes the repository as audited on 2026-08-12. It is a handoff, not a
replacement for reading the source. The repository is a Django project in the
`AI-thinking-review` directory. The current Git branch is
`feature/coding-first-vertical-slice`, based on commit `b963e58` (`Complete isolated Coding MVP
workflow`). The worktree already contained substantial uncommitted user changes before this
document was created. Preserve them.

## 1. Project Goal

The project is a Python/Django learning application for a gPBL 2026 project. Its purpose is to
design a learning experience in which students continue to think, judge, and grow independently
in an era where AI use is normal. AI is intended to be a controlled coach inside a learning method,
not a general answer generator.

The current repository contains a working, browser-session-based Coding vertical slice for
beginner Python loop/value transformations. Mathematics, Languages, and Other Subjects currently
exist as scaffolds only.

## 2. Product / Learning Philosophy

The specifications in `OVERALL_LEARNING_WORKFLOW.md` and `CODING_WORKFLOW.md` share these
principles:

- The learner thinks and attempts first, including an answer/solution, reasoning, and confidence.
- AI support is progressively unlocked and should diagnose thinking rather than merely grade an
  answer.
- A guiding question comes before a direct hint; one focused issue is handled at a time.
- Hints require another learner action and are recorded as evidence.
- A correct answer, confidence, or number of AI messages is not proof of mastery.
- The learner must explain the concept in a Teach-Back and apply it to a different Transfer Check
  without AI or hints.
- A misconception is a hypothesis until learner evidence confirms it.
- Mastery is controlled by application code, not by the model.
- Learner code must execute outside the Django process.
- Learning history should remain append-only so that the learner path can be reconstructed.

The shared specification also describes a four-area workflow beginning with subject/topic choice and
a diagnostic quiz, then response evaluation, diagnosis, guided revision, Teach-Back, transfer, and
progress update. The current implementation only realizes most of that method for Coding; the other
areas do not yet have the shared workflow.

## 3. Current Repository Structure

Important project files and responsibilities:

```text
AI-thinking-review/
├── manage.py                         Django command entry point
├── README.md                         Setup, scope, Coding runner, catalog, AI provider notes
├── OVERALL_LEARNING_WORKFLOW.md      Shared four-subject product specification
├── CODING_WORKFLOW.md                Detailed Coding behavior and agent rules
├── CODING_CATALOG.md                 Catalog authoring/validation/sync instructions
├── PRODUCTION.md                     Deployment and security checklist
├── requirements.txt                  Pinned Django/runner/AI/deployment dependencies
├── config/
│   ├── settings.py                   Environment, DB, security, runner, AI configuration
│   ├── settings_test.py              In-memory SQLite test settings
│   ├── environment.py                Environment variable parsing/required-value helpers
│   ├── urls.py                       Root URL routing
│   ├── asgi.py / wsgi.py              Deployment entry points
│   └── tests.py                      Environment parsing tests
├── apps/
│   ├── core/                         Landing page and subject links
│   ├── learning_core/                Shared learning models, state machine, mastery service
│   ├── coding_quiz/                  Implemented Coding vertical slice
│   ├── ai_engine/                    Provider boundary, schemas, validation, orchestration
│   ├── code_runner/                  Django-side isolated-runner gateway
│   ├── progress/                     Browser-scoped evidence dashboard
│   ├── math_quiz/                    Mathematics scaffold
│   ├── lang_quiz/                    Languages scaffold
│   └── other_quiz/                   Other Subjects scaffold
├── runner_service/                   Separate stdlib HTTP service and Docker sandbox
├── templates/                        Shared base/navbar/form components
├── static/css/base.css               Shared demo styling
├── fixtures/                         Empty JSON fixture placeholders (`[]`)
└── tests/integration/test_routes.py  Basic route smoke tests
```

The repository also has ignored/local artifacts such as `venv/` and `db.sqlite3`. They are not the
architecture and should not be edited or committed. `db.sqlite3` is ignored by `.gitignore`.

## 4. Current Architecture

The actual Coding request/data flow is:

```text
Browser request
  -> config.urls
  -> apps.coding_quiz.urls
  -> apps.coding_quiz.views.exercise
  -> Django session key + LearningSession lookup/create
  -> server-side action dispatch in _handle_action
  -> apps.coding_quiz.services
       -> forms/validators
       -> learning_core state transition
       -> code_runner gateway for Python execution, when submitted
       -> ai_engine orchestrator for structured AI, if configured
       -> curated fallback when AI is absent/invalid
       -> append-only learning evidence models
       -> mastery decision after Transfer Check
  -> template response / redirect
```

The application uses Django models and a browser session rather than authenticated learner
accounts. `LearningSession.browser_session_key` is the database-side identity for a browser. There
is no user-to-session foreign key. This is intentional for the demo, but it is not a multi-user
account implementation.

`apps.learning_core` is the shared domain layer. It owns the generic subject/topic/concept/activity
hierarchy, attempts, hints, coach evidence, misconceptions, Teach-Back, transfer, and mastery.
`apps.coding_quiz` supplies Coding-specific content and workflow services on top of it. The
Coding-specific `CodingExercise` is a one-to-one extension of `LearningActivity`.

The AI boundary is deliberately narrow:

- `apps.ai_engine.client.AIProvider` is the provider protocol.
- `get_ai_provider()` selects `settings.AI_PROVIDER_CLASS` or an unavailable provider.
- `generate_ai_response()` normalizes unexpected provider failures into
  `AIServiceUnavailable`.
- `apps.ai_engine.providers.deepseek.DeepSeekProvider` is the preferred OpenAI-compatible HTTP
  adapter when DeepSeek is configured; `GeminiProvider` remains available.
- `apps.ai_engine.orchestrator` validates every provider result and falls back to curated data.
- `apps.ai_engine.schemas` defines exact structured response shapes and rejects unauthorized
  workflow/mastery fields.

The code runner boundary is also narrow:

- `apps.code_runner.runner.CodeExecutionGateway` is the protocol.
- `UnavailableCodeExecutionGateway` returns `NOT_EXECUTED` and never executes source locally.
- `HttpCodeExecutionGateway` posts JSON to `<CODE_RUNNER_URL>/execute`.
- `runner_service/server.py` receives the request and starts one Docker container per request.
- The container runs `runner_service/harness.py`, which launches a worker process for each curated
  test case.

## 5. Current Coding Workflow

The specification state names and implementation state names are not identical. The code uses
`WorkflowState` in `apps/learning_core/state_machine.py`:

```text
TOPIC_SELECTED
  -> DIAGNOSTIC_QUIZ
  -> FIRST_ATTEMPT
  -> RESPONSE_EVALUATION
  -> DIAGNOSIS
  -> GUIDED_REVISION
  -> TEACH_BACK
  -> TRANSFER_TASK
  -> MASTERED | NEEDS_REVIEW
```

`apps/coding_quiz/views.py::STATE_TO_STAGE` collapses these into display stages: First Attempt,
Diagnosis, Revision, Teach-Back, Transfer Check, and Completed.

### Stage 1: Problem / task presentation

Status: **IMPLEMENTED for Coding, but narrower than the specification.**

`apps/coding_quiz/views.py::home` lists active database-backed `CodingExercise` records. The detail
view displays `LearningActivity.prompt`, `public_test_description`, and `starter_code` from the
database. The current catalog contains:

- `double-numbers`
- `square-numbers`
- `increment-numbers`

Content is authored in `apps/coding_quiz/catalog.py`, validated by
`apps/coding_quiz/catalog_validation.py`, and seeded/upserted by migrations or the
`sync_coding_catalog` management command.

There is no separate plan/predicted-output field or Coding diagnostic quiz UI. `TOPIC_SELECTED` is
automatically advanced to `DIAGNOSTIC_QUIZ` on the first GET of an exercise by
`_browser_learning_session`.

### Stage 2: Student first attempt

Status: **IMPLEMENTED.**

`CodingAttemptForm` in `apps/coding_quiz/forms.py` requires source code, reasoning, and confidence
1–5. `apps/learning_core/validators.py::validate_first_attempt` repeats the server-side gate.
`apps/coding_quiz/services.py::submit_first_attempt` also locks the session row, rejects wrong
states or duplicate revision zero attempts, creates a `LearnerAttempt`, and preserves all three
fields.

The browser template keeps AI and hints unavailable while the state is the first-attempt stage.

### Stage 3: Error detection / response evaluation

Status: **PARTIALLY IMPLEMENTED.**

The first attempt is sent through `build_python_request()` to the configured code runner. Its
result is stored in `LearnerAttempt.evaluation` with status, message, and test evidence. Supported
statuses are `PASSED`, `FAILED`, `SYNTAX_ERROR`, `RUNTIME_ERROR`, `TIMEOUT`, and `NOT_EXECUTED`.

The runner distinguishes syntax/runtime/timeout and public versus hidden test failure messages, but
there are no explicit `LOGIC_ERROR` or `OUTPUT_MISMATCH` statuses. A wrong returned value is
usually `FAILED`; a hidden test response intentionally does not include expected/actual values.

The application always proceeds from a submitted first attempt through `RESPONSE_EVALUATION` to
`DIAGNOSIS`, including when the first attempt passes. It does not implement the shared-spec branches
for “correct and clear reasoning”, “correct but low confidence”, or “correct but contradictory
reasoning” as distinct server paths.

### Stage 4: Reflection / diagnosis

Status: **IMPLEMENTED for the current loop-value concept.**

`submit_first_attempt` calls `_ensure_diagnostic_interaction`, which:

1. Builds privacy-minimized context from target concept/operation, confidence, execution status,
   aggregate test counts, source line count, boolean structure signals, attempt count, and highest
   hint level.
2. Sends that context through `orchestrate_diagnostic` when AI is configured.
3. Validates the response against `DiagnosticResponse`.
4. Falls back to the exercise’s curated question if AI is unavailable or invalid.
5. Stores `CoachInteraction` and a `MisconceptionRecord` with `HYPOTHESIS` status.

The current catalog’s principal misconception is `loop-value-misuse`. The initial question is
exercise-specific from `activity.rubric['diagnosis']['question']` when present.

`submit_diagnosis` accepts one learner answer for the latest diagnostic or hint interaction. It uses
the AI evaluator or deterministic fallback to decide whether the hypothesis is understood. It then
stores a new misconception record with `DISMISSED`, `CONFIRMED`, or `RESOLVED` status and a
`supersedes` link. A semantically understood answer transitions to `GUIDED_REVISION`; an unclear
answer stores a new Hint interaction and remains in `DIAGNOSIS`.

### Stage 5: Hint / scaffolding

Status: **IMPLEMENTED in two server-controlled ladders.**

Diagnosis uses levels 1–4: guiding question, concept reminder, related example, and partial method.
The server chooses the next response type and level. At level 4, the next learner answer can unlock
a conceptual solution reveal, which must be acknowledged before Revision.

Revision uses `request_curated_hint` and `HintUsage`. It starts at level 1 and only unlocks the next
level after a new revision exists after the previous hint. After level 4 and another failed revision,
the exercise-specific `activity.rubric['revision_solution']` may be revealed. A solution reveal does
not itself pass the exercise or grant mastery.

AI responses cannot choose a state, skip a level, change `should_reveal_solution`, or introduce an
uncurated misconception code. Every delivered revision hint is stored in `HintUsage` and mirrored
as a `CoachInteraction`.

### Stage 6: Retry / revision

Status: **IMPLEMENTED.**

`submit_revision` accepts only `GUIDED_REVISION`, validates code/reasoning/confidence, creates a new
`LearnerAttempt` with an incremented `revision_number`, and runs the original public plus hidden
test IDs. `save_revision` preserves the state; `finish_revision` advances only when status is
`PASSED`. Previous code and reasoning remain in history.

### Stage 7: Teach-Back

Status: **IMPLEMENTED with rubric-based deterministic fallback and optional AI evaluation.**

Teach-Back is available only after the latest revision is runner-verified `PASSED`. The form asks
for original issue, failure reason, correction, concept, and prevention. The rubric is authored per
exercise in `catalog.py`, built from `apps/coding_quiz/teach_back_rubric.py`.

`submit_teach_back` sends only rubric and learner answers to the AI provider. The validated output
evaluates every field once and may report a curated misconception. The local
`evaluate_teach_back` implementation is the fallback. Results are:

- `CLEAR_UNDERSTANDING`: transition to `TRANSFER_TASK`.
- `PARTIAL_UNDERSTANDING`: save feedback/follow-up and remain in Teach-Back.
- `MISCONCEPTION_REMAINS`: save a confirmed misconception and remain in Teach-Back.
- `ASSISTED_COMPLETION`: after the final Teach-Back ladder level, show a conceptual answer and
  require acknowledgement; the learner may reach Transfer Check but cannot satisfy clear Teach-Back
  mastery.

### Stage 8: Transfer Check

Status: **IMPLEMENTED for Coding.**

`submit_transfer_check` accepts only `TRANSFER_TASK`, requires the original revision to be passed
and an acceptable Teach-Back, then runs the exercise’s `transfer_test_ids` against the new source.
The transfer activity has different prompt/test data. The page does not show the original problem
or prior solution during this stage, and the view exposes no hint/AI action. The form requires new
source code, reasoning, and confidence.

`TransferAttempt.used_assistance` is always stored as `False` by the current server path. This is
consistent with server-disabled assistance, but the application cannot detect untracked external
assistance. `UNCLEAR — requires verification` whether future product requirements expect a stronger
attestation or monitoring mechanism.

If the runner returns `NOT_EXECUTED`, the transfer attempt is preserved and the session remains in
`TRANSFER_TASK`, allowing a retry. If the runner returns any evaluated result, a mastery decision is
recorded and the session becomes terminal `MASTERED` or `NEEDS_REVIEW`.

### Stage 9: Mastery evaluation

Status: **IMPLEMENTED for the Coding vertical slice.**

`apps/learning_core/services.py::evaluate_mastery` requires all of:

- original exercise passed;
- clear Teach-Back;
- transfer passed;
- transfer unassisted;
- no repeated confirmed misconception.

`record_mastery_decision` stores a `ConceptMastery` evidence JSON object. The state machine refuses
to enter `MASTERED` or `NEEDS_REVIEW` unless the matching mastery record already exists.

An assisted Teach-Back can unlock Transfer Check but is passed into mastery as not-clear, producing
`NEEDS_REVIEW`. A failed evaluated Transfer Check also produces `NEEDS_REVIEW`. A runner outage does
not create a premature mastery record.

### Stage 10: Progress / dashboard data

Status: **PARTIALLY IMPLEMENTED.**

`apps/progress` lists browser-scoped `LearningSession` history and links to a detail page. Detail
shows code attempts, Teach-Back attempts, Transfer attempts, misconception history, and mastery
decisions. The Coding page also shows saved work, hints, coach interactions, and final evidence.

The dashboard is not the full dashboard described by `OVERALL_LEARNING_WORKFLOW.md`. It does not
currently compute mastered-concept totals, unresolved counts, unassisted accuracy, confidence
calibration, retention/spaced review, or independent-correction metrics. The detail template does
not display all `CoachInteraction` and `HintUsage` data even though those records exist. `UNCLEAR —
requires verification` whether those omissions are intentionally outside the current Coding MVP or
are unfinished work.

## 6. Current Implementation Status

### IMPLEMENTED

- Django project configuration for development and production environments.
- Shared `Subject` → `Topic` → `Concept` → `LearningActivity` hierarchy.
- Explicit server-side `WorkflowState` transitions.
- Browser-session-scoped Coding sessions with ended-session history.
- Database-backed curated Coding catalog and validation/sync commands.
- First-attempt code/reasoning/confidence gate.
- Public/hidden curated test execution through an isolated-runner boundary.
- Diagnostic hypothesis, learner response, progressive diagnosis, and misconception history.
- Revision history and progressive revision hints.
- Exercise-specific Teach-Back rubrics, optional AI semantic evaluation, and deterministic fallback.
- Transfer Check with different exercise/test IDs and assistance lockout in the UI/state path.
- Mastery/needs-review decision logic with evidence and recommendations.
- Optional DeepSeek and Gemini providers with strict structured-response validation.
- Failing-closed behavior when AI or runner is unavailable.
- Browser-scoped progress dashboard and session detail pages.
- Django, AI boundary, Coding workflow, progress, route, and runner tests.

### PARTIALLY IMPLEMENTED

- Shared four-subject workflow: the shared models exist, but only Coding uses them end-to-end.
- Response evaluation: runner statuses exist, but no full reasoning-aware evaluation branches.
- Error classification: syntax/runtime/timeout/failure are supported, but not the full documented
  category set.
- Dashboard: durable evidence is displayed, but the richer metrics in the spec are absent.
- Misconception detection: the current rules are primarily one loop-value misconception and
  keyword/structure heuristics for the deterministic fallback; broader concepts are not present.
- Session handling: browser session isolation works for the demo, but no authenticated learner
  identity or cross-device history exists.
- Production deployment: settings/checklist are present, but deployment infrastructure and a
  production smoke test are not in this repository.
- Runner security: Docker isolation is configured, but the complete production threat model has
  not been independently audited.

### NOT IMPLEMENTED

- Separate topic-selection data flow and topic UI that creates/resumes shared activities.
- Diagnostic quizzes for Mathematics, Languages, or Other Subjects.
- End-to-end Math, Language, or Other Subjects learning sessions.
- Subject-specific AI orchestration and evaluation services for those three areas.
- User accounts, authentication, learner profiles, or durable learner identity.
- Spaced retention/review scheduling.
- Full progress analytics such as confidence calibration or retention.
- Multiple programming languages, arbitrary packages, multi-file projects, or free-form chatbot
  behavior.
- Dynamic content authoring UI; Coding catalog authoring is source-code based.
- Automated exercise/test generation.

### UNCLEAR / NEEDS VERIFICATION

- Whether the source specification’s separate diagnostic quiz is intentionally deferred from the
  Coding MVP or must be added before the next release.
- Whether `LearningSession` is intended to be reusable for all subjects or whether each subject will
  receive adapters/services with an explicit common activity contract.
- Whether an authenticated account model is required for the final product; the current README and
  code explicitly describe a no-account browser demo.
- Whether the current local/Docker runner hardening is sufficient for the intended deployment threat
  model.
- Whether the progress detail page should expose complete coach/hint evidence or only the current
  summary.

## 7. Mastery and Misconception System

### Mastery representation

`apps/learning_core/models.py::ConceptMastery` stores:

- `learning_session` and `concept` foreign keys;
- `status`: `MASTERED` or `NEEDS_REVIEW`;
- human-readable `reason` and optional `recommendation`;
- arbitrary `evidence` JSON;
- `created_at`.

Mastery is append-only per session. `LearningSession.current_state` is the workflow’s current
terminal state, but the stored `ConceptMastery` record is required before
`transition_session()` will allow the terminal transition.

### Misconception representation

`MisconceptionRecord` stores a session/concept, a stable slug `code`, evidence, a status, optional
`supersedes` link, and timestamp. Statuses are `HYPOTHESIS`, `CONFIRMED`, `DISMISSED`, `RESOLVED`,
and `REPEATED`.

Current Coding content uses `loop-value-misuse`. `apps/coding_quiz/misconception_rules.py` provides
the deterministic fallback functions:

- `diagnosis_confirms_loop_value_misconception()` checks whether an answer identifies a current
  element and the required operation.
- `transfer_repeats_loop_value_misconception()` checks code/reasoning signals and transfer action
  terms.

These functions are fallback/evidence rules. When a valid AI diagnosis/Teach-Back result is supplied,
the service uses the validated semantic result for the transition. A confirmed misconception can be
resolved after a passing transfer that does not repeat it, or marked `REPEATED` when the transfer
repeats it. A repeated misconception blocks mastery even when transfer tests pass.

Limitations: the current deterministic rules are concept-specific and partly term-based; they do
not form a general misconception taxonomy. `UNCLEAR — requires verification` whether the project
wants persisted learner-level misconceptions across multiple sessions; current records are scoped
to one `LearningSession`.

## 8. Transfer Check

Transfer content is linked from `CodingExercise.transfer_activity` and configured through
`transfer_prompt`, `transfer_test_ids`, and the transfer activity rubric. Catalog entries use
different function names/operations and different hidden test data. For example, the
`double-numbers` exercise transfers to word lengths; `increment-numbers` transfers to absolute
values.

Expected/current behavior:

| Learner outcome | Current behavior |
|---|---|
| Passes evaluated transfer without detected repeated misconception | Stores `TransferAttempt`, stores `ConceptMastery(MASTERED)`, transitions to `MASTERED`. |
| Passes tests but repeats a confirmed misconception | Stores `REPEATED` evidence, stores `NEEDS_REVIEW`, transitions to `NEEDS_REVIEW`. |
| Fails evaluated transfer | Stores the failed attempt and `NEEDS_REVIEW` mastery with recommendation. |
| Gives incomplete form data | Form validation returns errors; no transfer attempt is created. |
| Runner unavailable / `NOT_EXECUTED` | Stores the attempt, creates no mastery decision, remains in `TRANSFER_TASK`, allows retry. |
| Requests a hint during transfer | Server rejects the action because `hints_allowed()` is false. |
| Uses an assisted Teach-Back before transfer | Can reach Transfer Check after acknowledgement, but mastery is not awarded because Teach-Back is not clear. |

The code sets `used_assistance=False` for submitted transfer attempts because assistance controls are
disabled. There is no independent proof of outside assistance.

## 9. AI Engine

### Where calls happen

Only `apps/coding_quiz/services.py` calls the orchestrator. The four service paths are:

- `_ensure_diagnostic_interaction()` → `orchestrate_diagnostic()`.
- `submit_diagnosis()` → `orchestrate_diagnosis_evaluation()`.
- `request_curated_hint()` → `orchestrate_hint()`.
- `submit_teach_back()` → `orchestrate_teach_back()`.

### Prompts

`apps/coding_quiz/ai_prompts.py` contains the system prompts:

- `DIAGNOSTIC_SYSTEM_PROMPT`: one diagnostic question, hypothesis only, no solution/workflow
  control.
- `DIAGNOSIS_EVALUATION_SYSTEM_PROMPT`: semantic evaluation and server-selected next hint.
- `TEACH_BACK_SYSTEM_PROMPT`: rubric-based field evaluation and one focused follow-up.
- `REVISION_HINT_SYSTEM_PROMPT`: obey server-selected response type/level and reveal permission.

These prompts describe the current loop-value concept. They are not a general subject-neutral
prompt system.

### Structured outputs and validation

`apps/ai_engine/schemas.py` defines dataclasses and validators for `DiagnosticResponse`,
`DiagnosisEvaluationResponse`, `HintResponse`, `TeachBackResponse`, and
`TeachBackFieldEvaluation`. Validators reject missing/extra fields, uncurated misconception codes,
wrong levels/types, unauthorized reveal flags, multiple questions, code fences in progressive
responses, and workflow/mastery fields.

The server selects hint level, response type, and solution reveal permission before the provider
call. The model can propose content only inside that contract. The application—not the provider—
performs state transitions and mastery decisions.

### Provider and fallback logic

`config/settings.py` honors an explicit `AI_PROVIDER_CLASS`. Otherwise it selects DeepSeek when
`DEEPSEEK_API_KEY` is present, then Gemini when `GEMINI_API_KEY` is present. `DeepSeekProvider`
uses the OpenAI-compatible `/chat/completions` HTTP endpoint with JSON Object mode and includes the
requested schema in the system instruction. `GeminiProvider` remains available through
`google-genai`. Both use a 2048-token output limit. Secrets are read from environment variables;
no secret belongs in this document.

If no provider is configured, the provider raises `AIServiceUnavailable`. Unexpected provider
exceptions are normalized at `generate_ai_response`. Invalid structured output raises
`InvalidAIResponse`. The orchestrator records `source='AI'` for valid provider results and
`source='CURATED_FALLBACK'` plus a failure code for fallback results. Curated fallback content is
validated before storage/display.

The Coding service intentionally sends data-minimized signals for diagnosis and does not send raw
learner code or reasoning to the selected provider. Teach-Back sends rubric/answers but not learner identity or
source code. This privacy behavior is tested in `apps/coding_quiz/tests.py` and documented in
`README.md`.

## 10. Code Runner

### Django boundary

`apps/code_runner/runner.py` defines `ExecutionRequest`, `ExecutionResult`, `ExecutionStatus`, and
the gateway protocol. `apps/code_runner/validators.py` accepts Python only and limits source to
20,000 characters. `build_python_request()` packages source and curated test IDs.

The default gateway is fail-closed: if `CODE_RUNNER_URL` is empty, the submission is recorded as
`NOT_EXECUTED`. Django never calls `exec`, `eval`, or `subprocess` on learner source. The HTTP
gateway posts only language/source/test IDs to `/execute`, caps the response at 64 KiB, maps invalid
or unavailable responses to `NOT_EXECUTED`, and does not trust arbitrary status strings.

### Separate service and isolation

`runner_service/server.py` is a standard-library HTTP server. It validates Python, non-empty source,
non-empty curated test IDs, and an allowlist of known IDs. It starts a fresh Docker container per
request with:

- `--network none`;
- `--memory 128m`;
- `--cpus 1.0`;
- `--pids-limit 64`;
- `--read-only` root filesystem;
- a no-exec temporary filesystem;
- `no-new-privileges`;
- dropped Linux capabilities;
- a 3-second container timeout and cleanup on timeout.

`runner_service/Dockerfile` uses Python 3.12 Alpine and copies only the harness/worker. The harness
uses a 2-second learner-process timeout, compiles source to classify syntax errors, and executes the
learner function in `worker.py` for each curated test. Public failures may expose expected/actual
values; hidden failures do not. The worker process is launched as UID/GID 10001 on POSIX.

Security assumptions/risks to preserve in future work:

- This is an isolated service, but learner code is still executed with Python `exec()` inside the
  container worker. The container boundary is the essential safety boundary.
- The Docker image creates a non-root user, but the Dockerfile does not set a `USER` directive; the
  harness starts as the container default and then launches the worker as UID/GID 10001 on POSIX.
  Verify this intentionally in any production hardening review.
- The server is bound to `127.0.0.1` by default and should remain private behind deployment
  networking. Production requires a runner URL and token.
- The runner does not receive Django/database/Gemini secrets by design.
- `UNCLEAR — requires verification` whether the Docker flags and Python environment satisfy the
  final deployment threat model, including syscall/file-read/import escape scenarios.

## 11. Progress Tracking

Durable evidence is stored in `apps/learning_core`:

- `LearnerAttempt`: every original/revision code answer, reasoning, confidence, evaluation, and
  revision number.
- `HintUsage`: delivered revision hint level/content.
- `CoachInteraction`: diagnostic/hint request context, structured response, source, and failure code.
- `CoachLearnerResponse`: learner answer to a diagnostic interaction.
- `MisconceptionRecord`: hypothesis/confirmation/resolution/repetition history.
- `TeachBackAttempt`: serialized five-field response, evaluation, feedback, follow-up, rubric JSON.
- `TransferAttempt`: transfer code/reasoning/confidence, assistance flag, pass flag, evaluation.
- `ConceptMastery`: terminal status, reason, recommendation, evidence IDs.

`apps/progress/services.py::sessions_for_browser` filters by the current Django session key and
returns history ordered newest first. `apps/progress/views.py` exposes `/progress/` and
`/progress/sessions/<id>/`; the detail view uses the same browser filter and returns 404 for another
browser’s session.

Current progress limitations include browser-only identity, no aggregation by concept across
sessions, no retention scheduling, and incomplete presentation of coach/hint evidence on the detail
page.

## 12. Database / Models

### Shared learning models

`Subject` has unique `slug`; `Topic` belongs to Subject and is unique by `(subject, slug)`; `Concept`
belongs to Topic and is unique by `(topic, slug)`; `LearningActivity` belongs to Concept and stores
title, type, prompt, reference answer, and JSON rubric.

`LearningSession` belongs to Topic and optionally an Activity. It stores browser session key, current
state, timestamps, `ended_at`, and nullable `active_slot`. Migration `0007` uses a nullable active
slot in the unique key `(browser_session_key, activity, active_slot)` so ended sessions can coexist,
including on MySQL.

### Coding model

`apps/coding_quiz/models.py::CodingExercise` is one-to-one with the main `LearningActivity`. It
stores slug, Python language, difficulty/order, starter code, public/hidden test ID JSON, transfer
prompt/test IDs, transfer activity, and `active`. Active exercises run catalog validation in
`clean()`.

### Other subject models

- `MathQuestion`: prompt, question type, choices, reference answer, reasoning rubric.
- `LanguageQuestion`: prompt, vocabulary/grammar/reading/written type, reference answer, rubric.
- `OtherSubjectQuestion`: subject name, prompt, type, reference answer, rubric.

These models have migrations but are not connected to `LearningSession` or the shared workflow.

### Migration history

`apps/learning_core/migrations/0001_initial.py` creates the original shared hierarchy/evidence
models; `0002` adds transfer evaluation; `0003` replaces legacy misconception booleans with status
history and adds mastery; `0004` adds Teach-Back follow-up/rubric evidence; `0005` adds coach
interactions; `0006` adds activity-scoped sessions/ended history; `0007` changes active-session
uniqueness for MySQL compatibility.

`apps/coding_quiz/migrations/0001` creates CodingExercise; `0002` adds catalog fields; `0003` seeds
the curated catalog; `0004` makes slug required. Math/Language/Other each have only an initial
question-table migration.

## 13. Session State

### Django session keys

The view creates a Django session if `request.session.session_key` is missing. It writes:

- `coding_demo_learning_session_id` for `double-numbers`.
- `coding_demo_learning_session_id:<exercise.slug>` for other Coding exercises.

These values are currently bookkeeping/population only. The authoritative lookup is
`get_or_create_demo_session()` using the browser session key, exercise activity, active slot, and
`ended_at`; the stored ID is not used to authorize or retrieve the session.

### Database workflow state

`LearningSession.current_state` is authoritative. Allowed transitions are defined in
`apps/learning_core/state_machine.py`; `transition_session()` uses `select_for_update()`, validates
the edge, and requires a matching stored mastery record for terminal states. `ai_assistance_allowed()`
returns true only for `DIAGNOSIS` and `GUIDED_REVISION`; `hints_allowed()` returns true only for
`GUIDED_REVISION`.

There is no `NOT_STARTED`, `REVISION`, or `TRANSFER_CHECK` enum value in the current code; the
display/service mapping uses `TOPIC_SELECTED`, `GUIDED_REVISION`, and `TRANSFER_TASK` respectively.

## 14. URLs and Main Views

Root routes in `config/urls.py`:

| URL | Namespace/name | Responsibility |
|---|---|---|
| `/` | `core:home` | Landing page with four subject links |
| `/subjects/` | `core:subject_selection` | Subject-selection partial page |
| `/math/` | `math_quiz:home` | Mathematics scaffold screen |
| `/coding/` | `coding_quiz:home` | Active Coding catalog |
| `/coding/exercise/` | `coding_quiz:exercise` | Default `double-numbers` session |
| `/coding/exercises/<slug>/` | `coding_quiz:exercise_detail` | Slug-selected Coding session |
| `/languages/` | `lang_quiz:home` | Languages scaffold screen |
| `/other-subjects/` | `other_quiz:home` | Other Subjects scaffold screen |
| `/progress/` | `progress:dashboard` | Browser-scoped session list |
| `/progress/sessions/<id>/` | `progress:session_detail` | Browser-authorized evidence detail |
| `/admin/` | Django admin | Registered shared/Coding/question models |

Coding actions are POSTed to the current exercise URL using the `action` field: `first_attempt`,
`diagnosis`, `acknowledge_diagnosis_solution`, `hint`, `save_revision`, `finish_revision`,
`teach_back`, `acknowledge_teach_back_solution`, `transfer`, and `reset`. Unknown actions return
400. The view catches `ValidationError`/`PermissionDenied` and renders a message rather than
performing a transition.

## 15. Documentation vs Implementation Differences

1. `OVERALL_LEARNING_WORKFLOW.md` specifies four end-to-end subject workflows; only Coding is
   implemented end-to-end. Math/Language/Other views are static scaffolds.
2. The shared spec starts with topic selection and a diagnostic quiz; the current Coding view
   creates/loads a database session and immediately advances to `DIAGNOSTIC_QUIZ`, but there is no
   diagnostic quiz content or attempt model for it.
3. `CODING_WORKFLOW.md` uses conceptual names `NOT_STARTED`, `FIRST_ATTEMPT`, `DIAGNOSIS`,
   `REVISION`, `TRANSFER_CHECK`; implementation uses `TOPIC_SELECTED`, `DIAGNOSTIC_QUIZ`,
   `GUIDED_REVISION`, and `TRANSFER_TASK`.
4. The Coding specification allows distinct branches for passed/low-confidence/weak reasoning;
   the current service always creates a diagnosis interaction after the first attempt.
5. The specification lists syntax/runtime/logic/output categories; the runner has syntax/runtime,
   timeout, generic failed, and not-executed statuses, without explicit logic/output enum values.
6. The specification says AI may use submitted reasoning/code/test evidence, while the current
   README and service intentionally send only data-minimized signals for diagnosis and no raw source
   or reasoning to Gemini.
7. The specification calls for recording requested and delivered hint usage; the current system
   records delivered revision hints and coach interactions, but does not have a separate request
   event for an invalid/denied hint request.
8. The shared progress specification recommends mastered concepts, unresolved misconceptions,
   unassisted accuracy, confidence calibration, retention, and correction rates. Current dashboard
   pages show session evidence/counts but do not calculate those metrics.
9. `CODING_WORKFLOW.md` describes `TransferExercise`/test-case domain concepts, while the current
   schema uses `LearningActivity` plus JSON test ID lists and a runner-side catalog.
10. The specification says “the same misconception is not repeated”; the current implementation
    applies a specific `loop-value-misuse` heuristic and treats other confirmed codes as repeated by
    default in transfer logic. `UNCLEAR — requires verification` whether that fallback is acceptable
    for future non-loop concepts.
11. The repository’s top-level fixtures for all four subjects are empty arrays. They are not the
    source of the current Coding catalog; migrations/catalog code are.

## 16. Known Problems / Technical Debt

- The non-Coding apps are structural scaffolds, not usable learning workflows.
- No account/authentication layer means browser cookie possession is the only progress boundary.
- `LearningSession` and evidence records are not linked to `django.contrib.auth.User`.
- Diagnostic and Teach-Back fallbacks are specialized to the loop-values exercise family.
- `misconception_rules.py` uses simple term/structure heuristics and can misclassify paraphrases;
  AI semantic evaluation is optional and unavailable by default.
- `CodingExercise.clean()` can reach `allowed_codes[0]` in service code if a malformed rubric leaves
  no allowed misconception codes; catalog validation should be strengthened before arbitrary catalog
  content is trusted. This is an identified risk, not a claimed observed failure.
- `database_exercise_payload()` and catalog sync compare nested catalog data in ways that should be
  regression-tested whenever catalog schema changes.
- The active-session uniqueness constraint relies on nullable `active_slot` semantics and should be
  tested against the supported MySQL version as well as SQLite.
- Progress templates perform several related counts/accesses and may produce avoidable queries as
  history grows; no performance budget or query-count test exists.
- Progress detail omits coach interactions and hint usage despite those being durable learning data.
- `used_assistance=False` is a server assertion, not proof of no outside assistance.
- The runner’s Docker security posture needs an explicit production review; see Section 10.
- The runner server has no rate limiting, request authentication unless `RUNNER_AUTH_TOKEN` is set,
  or operational metrics. Production configuration requires a token, but the local default is empty.
- There is no deployment/CI configuration in the inspected project beyond documentation and tests.
- The worktree is dirty. Do not interpret the current uncommitted diff as disposable or reset it.
- Search found no product `TODO`/`FIXME` backlog in application code. Occurrences of “mock” are test
  doubles or the documented provider boundary; the default runner “placeholder” intentionally never
  executes code.

## 17. Tests

The audited command was:

```powershell
venv\Scripts\python.exe manage.py test --settings=config.settings_test
```

Latest result after adding the DeepSeek provider: **118 tests passed**. Also verified:

```powershell
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Both checks passed; the latter reported `No changes detected`.

Coverage by test area:

- `apps/ai_engine/tests.py`: provider boundary, invalid provider responses, exact schemas,
  unauthorized mastery/state fields, progressive-response restrictions, Gemini structured JSON,
  and DeepSeek JSON/envelope/transport/truncation failure handling.
- `apps/code_runner/tests.py`: Python-only boundary, unavailable gateway, HTTP response mapping,
  factory selection.
- `runner_service/tests.py`: curated cases, public/hidden evidence behavior, syntax/runtime/timeout,
  unknown IDs, Docker isolation flags, missing Docker, cleanup after timeout.
- `apps/learning_core/tests.py`: state transition rules, AI/hint gating, mastery prerequisites.
- `apps/coding_quiz/tests.py`: catalog, session isolation/reset/recovery, first-attempt gate, AI
  fallback/privacy, diagnosis, hint order, revision append-only behavior, runner gating,
  Teach-Back rubric/assisted completion, transfer retry/mastery/needs-review, browser isolation,
  service-level semantic/fallback behavior.
- `apps/progress/tests.py`: dashboard/detail rendering and cross-browser session protection.
- `apps/core/tests.py`, `apps/math_quiz/tests.py`, `apps/lang_quiz/tests.py`,
  `apps/other_quiz/tests.py`: route/scaffold checks and one Other Subjects rubric safety check.
- `tests/integration/test_routes.py`: basic route loading for all four areas and progress.
- `config/tests.py`: environment boolean/CSV/required-value helpers.

Important behavior lacking tests:

- End-to-end Math/Language/Other workflow behavior, because it does not yet exist.
- Real DeepSeek/Gemini network integration and production MySQL integration.
- Browser/session behavior across multiple processes/workers and concurrent POST races beyond the
  database uniqueness/unit locking checks.
- Full production deployment, HTTPS proxy, runner authentication, rate limiting, and observability.
- Rich dashboard metric correctness and query performance.
- Generalized misconception/content rubrics beyond the current catalog.

## 18. What Gemini Should Work on Next

The order below assumes the goal is to continue the product safely, not to broaden scope
speculatively.

### Priority 1 — Confirm the next vertical slice boundary

- Objective: Decide whether the next request is Coding hardening, shared workflow extraction, or a
  first non-Coding vertical slice.
- Relevant files: `OVERALL_LEARNING_WORKFLOW.md`, `CODING_WORKFLOW.md`, `README.md`,
  `apps/learning_core/*`, `apps/coding_quiz/*`.
- Expected behavior: One explicit scope and acceptance criteria; no duplicate state machine or
  parallel evidence model.
- Dependencies: Product decision on account identity and subject priority.
- Risks: Premature abstraction could destabilize the working Coding flow.
- Verify: Write/agree on a focused task list and map each task to existing services/models/tests.

### Priority 2 — Protect the Coding MVP with identified hardening tests

- Objective: Add regression tests for malformed catalog rubrics, concurrency/session recovery,
  all transfer outcomes, and denied actions.
- Relevant files: `apps/coding_quiz/catalog_validation.py`, `apps/coding_quiz/services.py`,
  `apps/learning_core/services.py`, `apps/coding_quiz/tests.py`, `apps/progress/tests.py`.
- Expected behavior: Invalid catalog data fails closed; no invalid transition or premature mastery;
  `NOT_EXECUTED` remains retryable; evaluated failure is terminal needs-review with evidence.
- Dependencies: None beyond current models.
- Risks: Tests may expose assumptions in the current one-concept catalog.
- Verify: `manage.py check`, `makemigrations --check --dry-run`, focused tests, full test suite.

### Priority 3 — Complete progress evidence presentation

- Objective: Make `/progress/` useful for the evidence already stored, especially coach interactions,
  hint levels, confidence, execution statuses, and mastery evidence.
- Relevant files: `apps/progress/services.py`, `apps/progress/views.py`,
  `apps/progress/templates/progress/*`, `static/css/base.css`, tests.
- Expected behavior: Browser-authorized pages expose durable evidence without leaking other browser
  sessions; no new source of truth is introduced.
- Dependencies: Product definition of the first dashboard metrics.
- Risks: N+1 queries and accidental cross-session exposure.
- Verify: Add template/security tests, use `select_related/prefetch_related`, run full suite.

### Priority 4 — Harden the runner boundary before real deployment

- Objective: Validate and, if explicitly approved, strengthen Docker/user/network/resource/request
  security.
- Relevant files: `runner_service/Dockerfile`, `runner_service/server.py`,
  `runner_service/harness.py`, `runner_service/worker.py`, `runner_service/README.md`,
  `apps/code_runner/http_gateway.py`, `PRODUCTION.md`.
- Expected behavior: Learner code remains outside Django, hidden data is not returned, runner access
  is private/authenticated, and failures remain `NOT_EXECUTED`/classified safely.
- Dependencies: A defined deployment threat model and supported Docker/OS environment.
- Risks: Over-hardening can break the local Windows/Docker workflow; under-hardening is a security
  risk.
- Verify: Runner tests, real local smoke tests with Docker, deployment checks, and a security review.

### Priority 5 — Generalize the shared workflow only when a subject is selected

- Objective: Implement one non-Coding subject end-to-end using `learning_core` rather than creating
  a second state/evidence architecture.
- Relevant files: selected subject app, `apps/learning_core/models.py`, `state_machine.py`,
  `services.py`, subject forms/services/tests, `config/urls.py`.
- Expected behavior: same first-attempt gate, progressive support, Teach-Back, transfer, and
  mastery semantics with subject-appropriate evaluation.
- Dependencies: Subject content, rubric/evaluator design, transfer tasks, and any account decision.
- Risks: Generic abstractions may hide subject-specific evaluation needs; keep the vertical slice
  narrow.
- Verify: Subject-specific workflow tests plus shared state/mastery regression tests.

### Priority 6 — Add durable identity only if product requirements require it

- Objective: Replace browser-only identity with authenticated learner ownership without breaking old
  demo data/session behavior.
- Relevant files: `apps/learning_core/models.py` and migrations, views, progress queries,
  settings/auth templates, tests, `PRODUCTION.md`.
- Expected behavior: Every progress read/write is authorized to the learner; historical demo data
  migration/compatibility is explicitly handled.
- Dependencies: Product decision and migration plan.
- Risks: This is a schema/security change; do not implement casually or as part of an unrelated task.
- Verify: Migration tests, authorization tests, cross-user isolation tests, full suite, MySQL smoke.

## 19. Files Gemini Must Read First

Read in this order before editing:

1. `GEMINI_PROJECT_HANDOFF.md`
2. `README.md`
3. `OVERALL_LEARNING_WORKFLOW.md`
4. `CODING_WORKFLOW.md`
5. `CODING_CATALOG.md` and `PRODUCTION.md`
6. `config/settings.py`, `config/settings_test.py`, and `config/urls.py`
7. `apps/learning_core/models.py`, `state_machine.py`, `services.py`, and `validators.py`
8. `apps/coding_quiz/models.py`, `catalog.py`, `forms.py`, `views.py`, and `services.py`
9. `apps/coding_quiz/ai_prompts.py`, `teach_back_rubric.py`, and `misconception_rules.py`
10. `apps/ai_engine/schemas.py`, `orchestrator.py`, `client.py`, and both provider adapters
11. `apps/code_runner/runner.py`, `http_gateway.py`, and `runner_service/README.md`
12. Relevant templates and the tests for the requested behavior

For a runner or deployment task, also read all of `runner_service/server.py`, `harness.py`,
`worker.py`, `Dockerfile`, and `runner_service/tests.py` before changing isolation behavior.

## 20. Rules for Future AI Agents

- Preserve unrelated user changes; inspect `git status` before and after work.
- Read the specification and this handoff before editing.
- Inspect the actual implementation path for the requested behavior; do not rely on filenames alone.
- Implement only the requested scope and state assumptions that materially affect product behavior.
- Do not create a duplicate state machine, AI boundary, runner boundary, mastery model, or progress
  architecture when an existing one applies.
- Do not bypass server-side workflow states with hidden buttons, client-only flags, or direct model
  writes from views.
- Keep the application in control of transitions, permissions, hint levels, and mastery.
- Do not replace real logic with mock behavior; mocks belong in tests/provider boundaries only.
- Keep curated prompts, hints, rubrics, misconception rules, and catalog data separate where the
  current design already does so.
- Do not expose hidden test data, reference solutions, raw learner data to an AI provider contrary
  to the privacy policy, or any secret/API key.
- Never execute learner code inside the Django process.
- Maintain Django conventions and compatibility with the current database/session design unless a
  schema change is explicitly required.
- Add a migration for model changes and add/update tests for every changed workflow rule.
- Run `manage.py check`, `makemigrations --check --dry-run`, relevant focused tests, and the full
  test suite before claiming completion.
- Report changed files, verification commands/results, and remaining limitations honestly.
- If repository behavior and documentation conflict, describe the conflict and ask for direction
  when it changes scope; do not silently choose a new product behavior.

## 21. Recommended Prompt for Gemini

Copy and adapt the following prompt for a future development task:

```text
You are continuing development in the existing AI-thinking-review Django repository.

1. Read GEMINI_PROJECT_HANDOFF.md completely before editing.
2. Read README.md, OVERALL_LEARNING_WORKFLOW.md, CODING_WORKFLOW.md, and any task-specific
   specification files completely.
3. Inspect the actual models, state machine, services, views, URLs, templates, AI schemas/provider
   boundary, runner boundary, migrations, and tests related to the requested task. Trace the real
   request/data flow; do not infer behavior from filenames.
4. Check Git status first and preserve all unrelated valid user changes. Do not reset, delete, or
   rewrite existing work.
5. Implement only the requested scope. Reuse the existing learning_core state machine, evidence
   models, AI orchestrator, and isolated code-runner boundary when applicable. Do not create a
   duplicate architecture or bypass server-side workflow permissions.
6. Preserve existing valid behavior: first-attempt gating, progressive hints, append-only evidence,
   Teach-Back, unassisted Transfer Check, mastery rules, privacy-minimized AI context, and
   fail-closed AI/runner behavior.
7. If the specification and implementation differ, identify the difference explicitly and state any
   assumption that changes product behavior before proceeding.
8. Add or update Django migrations and focused tests whenever behavior or models change. Never put
   secrets/API keys in source, logs, prompts, or the handoff.
9. Run:
   - venv\Scripts\python.exe manage.py check
   - venv\Scripts\python.exe manage.py makemigrations --check --dry-run
   - relevant focused tests
   - venv\Scripts\python.exe manage.py test --settings=config.settings_test
10. Review the final diff for unrelated files, secrets, hidden-test leakage, and unsafe learner-code
    execution.
11. Report the changed files, implementation details, verification commands/results, and remaining
    limitations. Do not claim completion if required checks fail.

Requested task:
<PASTE THE SPECIFIC DEVELOPMENT REQUEST HERE>
```

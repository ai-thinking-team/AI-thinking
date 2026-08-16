# Coding catalog authoring

Coding exercises are authored in `apps/coding_quiz/catalog.py`. The source catalog is reviewed in
Git, while MySQL stores the published runtime records used by the web app.

## Validate before syncing

Validation checks required exercise fields, unique slug/order/title, rubric structure, public versus
hidden runner IDs, Transfer Check IDs, and known IDs in `runner_service.harness.TEST_CATALOG`.

```powershell
.\venv\Scripts\python.exe manage.py validate_coding_catalog
.\venv\Scripts\python.exe manage.py validate_coding_catalog --json
```

An exercise cannot be active in Admin if it fails the same validation. Hidden IDs must exist in the
runner catalog but are never sent to the learner browser.

## Preview and publish

Preview database changes first:

```powershell
.\venv\Scripts\python.exe manage.py sync_coding_catalog --dry-run
```

Then publish the validated source catalog:

```powershell
.\venv\Scripts\python.exe manage.py sync_coding_catalog
```

The command is idempotent and reports created, updated, and unchanged slugs. It never deletes a
database exercise, attempt, session, misconception, Transfer Check, or mastery record. Set an
exercise's `active` field to `false` in the source catalog and sync it to stop new learners from
selecting it while preserving its historical evidence.

## Adding a new exercise

1. Add a curated runner test case to `runner_service/harness.py` and, when the runner is HTTP,
   allow its ID in `runner_service/server.py`.
2. Add the exercise and its Transfer Check to `CODING_CATALOG` with a unique slug and display order.
3. Run `validate_coding_catalog` and inspect the JSON output.
4. Run `sync_coding_catalog --dry-run`, review the report, then run the sync command.
5. Add focused tests for the operation, hidden boundary cases, misconception rubric, and Transfer
   Check. Run the full suite before using the exercise.

Catalog sync is a management operation, not a request-time side effect. Opening `/coding/` never
creates or modifies catalog records.

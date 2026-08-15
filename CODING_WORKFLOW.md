# Coding Module Workflow and AI Interaction Rules

## 1. Purpose of this file

This file defines the product behavior and engineering rules that coding agents must preserve when working in this repository.

When this file refers to the **AI Coach**, it means the learner-facing AI feature inside the web application. It does not restrict the development agent from answering the project team's technical questions directly.

The project does not have a final product name yet. Do not invent or introduce a brand name in code, UI text, documentation, metadata, or generated assets unless the project team explicitly chooses one.

## 2. Project context

This is a gPBL 2026 web application built by Japanese and Vietnamese students using Python and Django.

The project theme is:

> Design a learning method that helps students continue to think, judge, and grow independently in an era where AI use is normal.

The web application is a means of implementing the learning method. Do not treat “building a platform” or “adding AI” as the solution by itself.

The intended product may support multiple subjects in the future. The first vertical slice is the **Programming module**, initially focused on beginner Python concepts such as lists, dictionaries, loops, and functions.

## 3. Core product problem

Students can submit code to a general AI assistant, copy the corrected answer, and complete an exercise without understanding the cause of the error or being able to solve a similar problem independently.

The desired outcome is not merely working code. A learner should be able to:

- make a genuine attempt before receiving AI assistance;
- identify and correct the underlying misconception;
- explain why the original code failed and why the correction works;
- apply the same concept to a similar task without AI assistance.

## 4. Non-negotiable product rules

All implementations of the Programming module must preserve these rules:

1. The learner must submit code, reasoning, and confidence before AI assistance is unlocked.
2. The AI Coach asks a diagnostic or guiding question before giving a direct hint.
3. Help is unlocked progressively. The AI Coach provides no more help than the learner currently needs.
4. The AI Coach must not rewrite the complete solution as its first response.
5. Each AI response should focus on one issue at a time.
6. Every hint must be followed by a new learner action, such as answering a question or revising code.
7. Passing the original test cases is necessary but not sufficient for mastery.
8. The learner must complete Teach-Back and an unassisted Transfer Check before mastery is recorded.
9. The application, not the language model, controls workflow transitions and mastery status.
10. Learner code must never execute inside the main Django application process.

Do not weaken or bypass these rules for UI convenience.

## 5. Programming learning state machine

Use an explicit server-controlled state machine. The expected flow is:

```text
NOT_STARTED
    -> FIRST_ATTEMPT
    -> DIAGNOSIS
    -> REVISION
    -> TEACH_BACK
    -> TRANSFER_CHECK
    -> MASTERED | NEEDS_REVIEW
```

Recommended meanings:

- `NOT_STARTED`: The learner has not submitted a formal attempt.
- `FIRST_ATTEMPT`: Code, reasoning, and confidence have been submitted.
- `DIAGNOSIS`: The system is investigating an error or possible misconception.
- `REVISION`: The learner is revising code after a question or hint.
- `TEACH_BACK`: The original exercise passes and the learner must explain the bug and correction.
- `TRANSFER_CHECK`: The learner solves a parallel task without AI or hints.
- `MASTERED`: Every mastery criterion has been satisfied.
- `NEEDS_REVIEW`: The learner could not yet demonstrate independent transfer.

Reject invalid transitions on the server. Do not rely only on hidden buttons or client-side checks.

## 6. Detailed learner workflow

### Stage 1: Understand and plan

Present the problem, examples, starter code, expected behavior, and public test information. Ask the learner to write a short solution plan. Selected exercises may also ask the learner to predict the output before running code.

The AI Coach remains unavailable.

### Stage 2: Submit a genuine first attempt

A formal attempt requires:

- non-empty learner code;
- a short explanation of the intended approach;
- a confidence value from 1 to 5.

Recommended confidence labels:

- `1`: I am guessing.
- `2`: I am not sure.
- `3`: I understand part of it.
- `4`: I am fairly confident.
- `5`: I can explain my solution.

Do not unlock the AI Coach until all required fields are submitted and stored.

### Stage 3: Evaluate the attempt

Run public and hidden tests in an isolated execution environment. Classify the result when possible:

- syntax error;
- runtime error;
- logic error;
- output mismatch;
- passed.

Show useful evidence, such as the failed test category or boundary condition, without revealing the final solution.

### Stage 4: Diagnose the misconception

The AI Coach may use:

- the exercise and target concept;
- the submitted code;
- the learner’s reasoning;
- the confidence value;
- public and hidden test results;
- prior attempts;
- hint history;
- previously detected misconceptions.

The AI Coach must treat a misconception as a hypothesis until the learner’s answer confirms it.

Good interaction:

> What type of data structure is `student`, and how are its values identified?

Bad interaction:

> Replace `student[0]` with `student["name"]`. Here is the complete solution.

### Stage 5: Provide progressive hints

Use the following Hint Ladder:

1. **Guiding question** — direct attention to the relevant part of the problem.
2. **Concept reminder** — restate the underlying rule without applying it fully.
3. **Related example** — demonstrate the concept in a different context.
4. **Partial method** — provide an incomplete structure that the learner must finish.

A complete solution is a last resort. If it is ever shown, the concept must not be marked as mastered based only on the original exercise.

Record every unlocked hint and the highest hint level used.

### Stage 6: Teach-Back

After the original code passes all required tests, ask the learner to explain:

- what the original error was;
- why the original code failed;
- what was changed;
- which concept explains why the correction works;
- how the same error can be avoided later.

Evaluate the explanation against an explicit exercise or concept rubric. Use results such as:

- `CLEAR_UNDERSTANDING`;
- `PARTIAL_UNDERSTANDING`;
- `MISCONCEPTION_REMAINS`.

If the explanation is incomplete, ask one focused follow-up question.

### Stage 7: Transfer Check

Give the learner a parallel exercise that tests the same concept with different names, values, or context.

During the Transfer Check:

- disable the AI Coach;
- disable all hints;
- hide the previous solution;
- use different test data;
- require a new confidence value;
- record whether the solution was completed without assistance.

## 7. Mastery rules

A concept may be marked `MASTERED` only when all of the following are true:

- the original solution passes all required tests;
- the Teach-Back accurately explains the bug and correction;
- the Transfer Check passes without AI or hints;
- the same misconception is not repeated in the Transfer Check.

Otherwise, mark the concept `NEEDS_REVIEW` and recommend a specific concept or corrective exercise.

Never use the number of AI messages or the number of submissions alone as evidence of mastery.

## 8. Learner-facing AI contract

Prefer structured AI output over unrestricted text. A diagnostic response should be representable in a form similar to:

```json
{
  "possible_misconception": "dictionary_as_list",
  "diagnostic_confidence": 0.84,
  "response_type": "guiding_question",
  "message": "How are values identified inside a dictionary?",
  "hint_level": 1,
  "should_reveal_solution": false
}
```

Validate model output before storing or displaying it. The model may recommend a next action, but application code must enforce permissions, hint availability, and state transitions.

If the AI service is unavailable or returns invalid output, preserve the learning flow with curated diagnostic questions and hints. AI failure must not expose an answer or corrupt learner progress.

## 9. Data that must be preserved

Store enough information to reconstruct the learner’s path:

- exercise and target concept;
- submitted code for every formal attempt;
- reasoning and confidence for every formal attempt;
- test results and error classification;
- diagnostic questions and learner responses;
- hints unlocked and their levels;
- possible and confirmed misconceptions;
- Teach-Back response and rubric result;
- Transfer Check attempt and assistance status;
- final mastery status and reason.

Formal attempts and hint usage are learning evidence. Prefer append-only history over silently overwriting earlier attempts.

## 10. Code-execution safety

Never use unrestricted `exec()`, `eval()`, `subprocess`, or equivalent execution of learner code inside the Django web process.

Use one of these approaches:

- a browser-based Python runtime; or
- a separate isolated execution service with strict CPU, time, memory, filesystem, process, and network limits.

Treat learner code as hostile input. Never pass secrets or production credentials into the execution environment. Hidden tests and reference solutions must not be exposed to the client.

## 11. MVP scope

Prioritize a complete, demonstrable Python learning loop over broad feature coverage.

The first MVP should include:

- a curated set of beginner Python exercises;
- concepts, exercises, starter code, and test cases;
- code, reasoning, and confidence submission;
- public and hidden test evaluation;
- basic error classification;
- curated misconception rules;
- a three- or four-level Hint Ladder;
- attempt and hint history;
- Teach-Back;
- an unassisted Transfer Check;
- concept mastery status.

Defer unless explicitly requested:

- multiple programming languages;
- free-form general chatbot behavior;
- multi-file projects;
- arbitrary package installation;
- fully AI-generated exercises and test cases;
- complex performance or optimization scoring;
- features unrelated to demonstrating the core learning method.

## 12. Suggested domain model

Keep the model names consistent with the existing codebase. The following concepts should exist even if the exact names change:

- `Concept`;
- `Exercise`;
- `TestCase`;
- `Attempt`;
- `Hint`;
- `HintUsage`;
- `Misconception`;
- `LearnerMisconception`;
- `TeachBackResponse`;
- `TransferExercise` or a relationship between parallel exercises;
- `TransferAttempt`;
- `ConceptMastery`.

Do not create all models speculatively in one large migration. Add the smallest coherent set needed for the current vertical slice.

## 13. Engineering workflow for coding agents

Before making changes:

1. Read this file and the repository README.
2. Inspect the current repository structure and Git status.
3. Identify the smallest vertical slice that satisfies the request.
4. State any assumption that materially changes product behavior.

While implementing:

1. Keep changes focused and reviewable.
2. Preserve existing user changes and avoid unrelated refactors.
3. Put business rules in server-side domain or service logic, not only templates or JavaScript.
4. Keep AI-provider code behind a small interface so it can be mocked and replaced.
5. Keep curated hints, rubrics, and misconception rules separate from prompt text where practical.
6. Never commit `.env`, API keys, learner secrets, or production credentials.
7. Add a Django migration whenever models change.
8. Add or update tests for every workflow rule changed.

Before finishing:

1. Run `python manage.py check`.
2. Run `python manage.py makemigrations --check --dry-run`.
3. Run `python manage.py test`.
4. Run focused tests for the changed module.
5. Review the diff for secrets, accidental generated files, and unrelated edits.
6. Report what changed, what was verified, and any remaining limitation.

Do not claim completion when required tests fail or when a critical user flow has not been exercised.

## 14. Minimum acceptance tests

At minimum, automated tests should verify:

- AI assistance is unavailable before a complete first attempt;
- an attempt without code, reasoning, or confidence is rejected;
- hints unlock only in the allowed order;
- every hint use is recorded;
- a model response cannot directly set mastery;
- Teach-Back cannot begin before the original exercise passes;
- Transfer Check cannot begin before an acceptable Teach-Back;
- AI and hints remain disabled during Transfer Check;
- passing only the original exercise does not create mastery;
- mastery requires an unassisted passing Transfer Check;
- invalid workflow transitions are rejected server-side;
- AI failures fall back safely without exposing a solution;
- learner code is sent only to the isolated execution boundary.

## 15. Definition of done for the Programming vertical slice

A new learner can:

1. choose a Python exercise;
2. submit code, reasoning, and confidence;
3. receive test evidence without receiving the solution;
4. answer a diagnostic question;
5. unlock and use staged hints;
6. revise and pass the original exercise;
7. explain the error and correction;
8. solve a parallel task without AI;
9. receive an evidence-based `MASTERED` or `NEEDS_REVIEW` result;
10. review their attempt, hint, and misconception history.

The feature is not done if the demo requires manually editing the database, bypassing the state machine, or pretending that an unimplemented AI or code-execution step succeeded.

## 16. Project evaluation alignment

When proposing or implementing a feature, explain which part of the solution it serves:

- **Think-First Gate** supports independent effort before AI use.
- **Diagnostic questions** identify the reason behind an incorrect answer.
- **Hint Ladder** prevents unnecessary answer disclosure.
- **Teach-Back** checks conceptual understanding.
- **Transfer Check** verifies independent application.
- **Mastery and misconception history** provide evidence of learning progress.

Prefer features that improve the demonstrable user story and the core learning outcome. Avoid adding features only because they look impressive or because the AI provider supports them.

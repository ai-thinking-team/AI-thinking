# Overall Learning Workflow

## 1. Purpose

This document defines the shared learning process for the four learning areas in the web application:

1. Mathematics
2. Languages
3. Programming
4. Other Subjects

All four areas must follow the same learning philosophy: learners think first, receive only the support they need, explain what they understand, and demonstrate that understanding on a new task.

This is the project-level workflow. More detailed rules for the Programming area are defined in `CODING_WORKFLOW.md`.

## 2. Core Learning Principles

The following rules apply to every subject:

1. The learner must make an attempt before AI support becomes available.
2. The learner must submit an answer, reasoning, and confidence level.
3. The AI should diagnose the learner's thinking, not only mark the final answer.
4. Help must be delivered progressively through a controlled hint ladder.
5. A complete answer is the last resort, not the default response.
6. Receiving the correct answer does not mean that the concept is mastered.
7. The learner must explain the concept in their own words.
8. The learner must complete a similar task without AI assistance.
9. The system must record misconceptions, hint usage, confidence, and retention.
10. The AI must sometimes remain silent when the learner can continue independently.

## 3. Shared Learning State Machine

Every learning attempt should follow these states:

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

The system must not skip directly from `FIRST_ATTEMPT` to `MASTERED`.

## 4. Common Learning Process Across Subjects

### Stage 1: Choose a Subject and Topic

The learner selects one learning area and then chooses a topic.

Examples:

- Mathematics: linear equations, probability, geometry
- Languages: vocabulary, grammar, reading comprehension
- Programming: variables, conditions, loops, functions
- Other Subjects: biology, history, economics, or another supported topic

The system creates or resumes a learning session for the selected topic.

### Stage 2: Take a Diagnostic Quiz

The system presents a short diagnostic quiz to estimate the learner's current knowledge and identify possible weaknesses.

The diagnostic quiz should:

- Contain a small number of focused questions.
- Cover prerequisite and target concepts.
- Avoid giving AI hints during the initial diagnostic attempt.
- Record correct answers, incorrect answers, confidence, and response time.
- Produce an initial list of weak concepts rather than a single overall score.

The diagnostic result determines the recommended starting difficulty and learning path.

### Stage 3: Think Before Receiving AI Support

Before AI help is unlocked, the learner must submit:

- An answer or attempted solution.
- A short explanation of their reasoning.
- A confidence level.

Recommended confidence values are:

- Low
- Medium
- High

The system must not enable the hint controls until all required fields have been submitted.

The first attempt must be preserved even after the learner revises it.

### Stage 4: Evaluate the Response

The system evaluates both the answer and the reasoning.

#### Correct answer and clear reasoning

The learner proceeds to the Teach-Back stage. The concept is not yet marked as mastered.

#### Correct answer and low confidence

The system asks a verification question to determine whether the learner understood the concept or guessed correctly.

#### Correct answer and weak or contradictory reasoning

The system asks a diagnostic question. A correct final answer must not hide a reasoning error.

#### Incorrect answer

The system identifies the likely misconception and asks a diagnostic question before giving a hint.

#### Incomplete or unclear answer

The system asks the learner to clarify the missing part instead of immediately explaining the solution.

### Stage 5: Provide Progressive Support

AI support follows a four-level hint ladder:

1. **Level 1 — Guiding Question:** Direct the learner's attention to the relevant part of the problem.
2. **Level 2 — Concept Reminder:** Remind the learner of a principle, rule, or definition without applying it completely.
3. **Level 3 — Related Example:** Show a different example that uses the same concept.
4. **Level 4 — Partial Method:** Reveal part of the method while leaving meaningful work for the learner.

Rules for the hint ladder:

- Start with Level 1.
- Unlock the next level only after another learner attempt.
- Do not reveal the complete answer inside a lower-level hint.
- Connect hints to the detected misconception.
- Record every requested and delivered hint.
- Provide a complete explanation only after the progressive support process has failed or when required for accessibility or safety.

### Stage 6: Revise the Answer

After receiving a diagnostic question or hint, the learner submits a revised answer and updated reasoning.

The system records:

- The original answer.
- Every revision.
- Changes in the learner's reasoning.
- Confidence before and after support.
- Hint levels used.
- Whether the learner corrected the mistake independently.

The system should reward meaningful improvement, not repeated guessing.

### Stage 7: Teach Back the Concept

The learner explains the underlying concept in their own words.

The AI may ask follow-up questions such as:

- Why does this method work?
- When would this rule not apply?
- What was wrong with your first approach?
- How would you explain this idea to another learner?

The Teach-Back response must be evaluated for conceptual understanding, not exact wording.

If the explanation contains a misconception, the learner returns to guided revision.

### Stage 8: Complete a Transfer Task

The learner receives a new task that:

- Assesses the same underlying concept.
- Uses different values, wording, examples, or context.
- Is completed without AI hints.
- Is not a trivial copy of the original task.

The purpose is to determine whether the learner can transfer the idea instead of repeating a memorized procedure.

If the learner requests help during this stage, the attempt is no longer considered unassisted. The system may provide support, but it must generate another transfer task before mastery can be awarded.

### Stage 9: Update Learning Progress

The concept is marked `MASTERED` only when the learner:

1. Produces a correct or acceptable revised solution.
2. Gives a satisfactory Teach-Back explanation.
3. Completes a transfer task without AI assistance.
4. Does not repeat the same critical misconception.

Otherwise, the concept is marked `NEEDS_REVIEW`.

For `NEEDS_REVIEW`, the system should:

- Save the unresolved misconception.
- Recommend a specific concept or prerequisite to review.
- Recommend suitable exercises.
- Schedule the concept for later practice.
- Avoid presenting only a generic message such as "Study more."

## 5. Subject-Specific Application

The common workflow remains unchanged, but each learning area uses different answer formats and evaluation methods.

| Learning area | Typical learner submission | Main evaluation focus | Example transfer task |
|---|---|---|---|
| Mathematics | Final result, calculation steps, reasoning | Method, logical steps, conceptual errors, calculation accuracy | Same concept with different values or context |
| Languages | Selected answer, written response, definition, translation, or recording | Meaning, grammar, vocabulary use, comprehension, communication | Use the same language concept in a new sentence or passage |
| Programming | Source code, explanation, expected output, confidence | Correctness, tests, debugging process, code reasoning, misconception | Solve a similar programming problem without hints |
| Other Subjects | Short answer, explanation, classification, comparison, or evidence-based response | Conceptual accuracy, evidence, cause-and-effect reasoning, source use | Apply the concept to a different case or scenario |

### 5.1 Mathematics

The Mathematics area should support:

- Multiple-choice and open-response questions.
- Step-by-step calculations.
- Formula and concept explanations.
- Identification of the first incorrect reasoning step.
- Diagnostic categories such as sign errors, incorrect formulas, unit errors, and misunderstanding of variables.

The AI should ask about the learner's method before showing calculations.

### 5.2 Languages

The Languages area should support:

- Vocabulary and definition questions.
- Grammar questions.
- Reading comprehension.
- Sentence construction.
- Written explanations and, in later versions, speaking or pronunciation practice.

The AI should distinguish between a vocabulary gap, a grammar misconception, and misunderstanding of context.

### 5.3 Programming

The Programming area should support:

- Writing and revising source code.
- Running curated test cases in an isolated environment.
- Comparing expected and actual output.
- Explaining the cause of an error.
- Reducing errors through multiple learner revisions.
- Completing an unassisted parallel coding task.

The AI must guide debugging without immediately rewriting the learner's code. Detailed behavior is defined in `CODING_WORKFLOW.md`.

### 5.4 Other Subjects

The Other Subjects area provides a reusable framework for subjects that do not yet have a dedicated module.

It should support:

- Multiple-choice questions.
- Definitions and concept explanations.
- Comparison and classification tasks.
- Cause-and-effect questions.
- Evidence-based short answers.

Content must include subject metadata and evaluation criteria. The AI must not evaluate an open-ended answer without a rubric or reliable reference answer.

## 6. Common Data to Record

Every learning attempt should preserve:

- Learner identifier.
- Subject, topic, and concept.
- Question and question type.
- Original answer.
- Original reasoning.
- Initial confidence level.
- Diagnostic result.
- Detected misconception.
- Hint history and highest hint level.
- Revised answers and reasoning.
- Teach-Back response and evaluation.
- Transfer task response and evaluation.
- Final learning status.
- Timestamps for attempts and reviews.

Do not overwrite previous attempts. Learning progress depends on comparing the learner's thinking over time.

## 7. AI Interaction Rules

The learner-facing AI must:

- Ask one focused question at a time.
- Use language appropriate to the learner's level.
- Refer to the learner's submitted reasoning.
- Separate confirmed errors from possible misconceptions.
- Explain why a hint is relevant without revealing too much.
- Encourage source checking when factual evidence is required.
- State uncertainty when an answer cannot be evaluated reliably.
- Avoid rewarding the number of AI interactions.

The learner-facing AI must not:

- Appear before the learner's first attempt.
- Replace the learner's work with a complete solution by default.
- Mark mastery immediately after showing an answer.
- Treat confidence as proof of correctness.
- Treat a correct answer as proof of understanding.
- Invent facts, sources, test results, or learner progress.

## 8. Progress Dashboard

The dashboard should show learning evidence rather than only quiz scores.

Recommended indicators include:

- Mastered concepts.
- Concepts that need review.
- Unresolved misconceptions.
- Unassisted accuracy.
- Teach-Back quality.
- Transfer-task success rate.
- Confidence calibration.
- Hint usage by level.
- Retention after spaced review.
- Independent correction rate.

## 9. Recommended MVP Boundary

The first MVP should implement one shared learning engine and a small curated content set for each subject area.

Recommended MVP features:

- User accounts.
- Four subject areas.
- Topic and concept selection.
- Diagnostic quizzes.
- Think-First submission gate.
- Response evaluation.
- Four-level hint ladder.
- Revision history.
- Teach-Back questions.
- Transfer tasks.
- `MASTERED` and `NEEDS_REVIEW` states.
- Basic progress dashboard.
- Curated rubrics and misconception rules.

Keep the first content set narrow. A working end-to-end learning loop in each area is more important than supporting many topics without reliable evaluation.

## 10. Definition of Done for a Learning Activity

A learning activity is complete only when:

- The learner selected a subject and topic.
- A diagnostic or learning question was presented.
- The first attempt contained an answer, reasoning, and confidence.
- The response was evaluated using subject-appropriate criteria.
- Any help followed the progressive hint ladder.
- Revisions and hint usage were recorded.
- A Teach-Back response was evaluated.
- A transfer task was attempted without AI assistance.
- The final status and recommendation were saved.

## 11. Relationship Between Project Documents

- `README.md` defines the project context, goals, constraints, and evaluation requirements.
- `OVERALL_LEARNING_WORKFLOW.md` defines the shared process for all four learning areas.
- `CODING_WORKFLOW.md` defines the detailed behavior of the Programming area.
- Future subject-specific documents may be named `MATH_WORKFLOW.md`, `LANGUAGE_WORKFLOW.md`, and `OTHER_SUBJECTS_WORKFLOW.md`.

When implementing a subject-specific feature, follow both this document and the relevant subject workflow. If two instructions conflict, preserve the core principles in Section 2 and choose the behavior that requires more independent learner thinking.

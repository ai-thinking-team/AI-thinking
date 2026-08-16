# Kế hoạch hoàn thiện Coding vertical slice cho Codex

> Phạm vi: module Coding trong repository Django `AI-thinking-review`  
> Trọng tâm: một learning loop Python hoàn chỉnh, có thể kiểm chứng và demo end-to-end  
> Ngoài phạm vi: Math, Languages, Other Subjects và các tính năng nền tảng không cần thiết cho Coding demo

## 1. Mục tiêu

Hoàn thiện phần Coding thành một trải nghiệm học tập trong đó người học phải tự suy nghĩ, sửa lỗi và chứng minh khả năng áp dụng kiến thức độc lập. AI chỉ đóng vai trò huấn luyện viên có kiểm soát, không phải chatbot trả lời tự do.

Một Coding session hợp lệ phải giữ được chuỗi bằng chứng:

1. Người học đọc đề, dự đoán kết quả và lập kế hoạch.
2. Người học nộp code, reasoning và confidence trước khi nhận hỗ trợ.
3. Code được đánh giá qua isolated runner bằng public và hidden tests curated.
4. Hệ thống hỏi câu chẩn đoán trước khi mở hint.
5. Hint mở theo từng cấp và luôn yêu cầu hành động mới của người học.
6. Người học tự sửa code cho tới khi runner xác nhận `PASSED`.
7. Người học hoàn thành Teach-Back theo rubric của exercise.
8. Người học làm Transfer Check khác ngữ cảnh, không có AI/hint trong app.
9. Backend mới quyết định `MASTERED` hoặc `NEEDS_REVIEW` từ evidence đã lưu.

Tài liệu nghiệp vụ chính:

- `CODING_WORKFLOW.md`
- `OVERALL_LEARNING_WORKFLOW.md`, chỉ dùng cho các nguyên tắc học tập chung áp dụng vào Coding
- `CODING_CATALOG.md`
- `PRODUCTION.md`
- `GEMINI_PROJECT_HANDOFF.md`

Nếu tài liệu chung mâu thuẫn với `CODING_WORKFLOW.md`, ưu tiên quy tắc Coding và phương án buộc người học suy nghĩ độc lập nhiều hơn.

## 2. Phạm vi

### 2.1 Trong phạm vi

- Sáu beginner Python exercises hiện có:
  - `double-numbers`
  - `square-numbers`
  - `increment-numbers`
  - `lookup-dictionary-grade`
  - `safe-divide-function`
  - `first-list-item`
- Understand & Plan, First Attempt, Diagnosis, Hint Ladder, Revision, Teach-Back, Transfer Check và Mastery.
- Catalog, rubric, misconception rule và transfer task của Coding.
- AI provider boundary cùng curated fallback phục vụ Coding.
- Isolated Python runner, curated test IDs và redaction hidden-test evidence.
- Coding session history và progress evidence cần cho demo.
- UI, accessibility, responsive behavior và local runner cần để chạy Coding demo an toàn.
- Browser-session ownership trong phạm vi demo hiện tại.

### 2.2 Ngoài phạm vi

- Xây dựng workflow end-to-end cho Math, Languages hoặc Other Subjects.
- Tạo shared diagnostic quiz cho toàn bộ môn học.
- Account/login/profile hoặc migration từ browser session sang user account.
- Course space, PDF upload, document parsing và external knowledge sources.
- Adaptive/spaced review, retention scheduling hoặc “AI Agency Score”.
- Nhiều ngôn ngữ lập trình, package installation hoặc multi-file projects.
- Public JSON API nếu server-rendered Django vẫn đáp ứng Coding demo.
- Content authoring UI; catalog tiếp tục được version hóa trong code và đồng bộ bằng command.
- Deployment public, HTTPS, hosting target, production database và public internet operations.

Các module ngoài Coding chỉ được sửa khi đó là dependency trực tiếp của Coding, ví dụ `learning_core`, `ai_engine`, `code_runner`, `progress`, cấu hình Django hoặc shared template/CSS. Không mở rộng hành vi của môn khác.

## 3. Kiến trúc cần giữ

```text
Browser
  -> apps/coding_quiz/views.py
  -> apps/coding_quiz/services.py
       -> apps/learning_core/state_machine.py
       -> apps/learning_core/models.py
       -> apps/code_runner/* -> runner_service/* -> Docker
       -> apps/ai_engine/orchestrator.py -> provider hoặc curated fallback
  -> database evidence
  -> Coding/progress Django templates
```

Quyền sở hữu nghiệp vụ:

- `coding_quiz`: exercise catalog, Coding forms, prompts, rubric, misconception rules và Coding workflow orchestration.
- `learning_core`: state machine, session, attempts, hints, misconception history, Teach-Back, transfer và mastery records.
- `ai_engine`: provider interface, schema validation và fallback; không được tự đổi state hoặc mastery.
- `code_runner` và `runner_service`: biên thực thi code; Django không chạy learner code trực tiếp.
- `progress`: chỉ đọc và trình bày evidence của Coding session thuộc browser hiện tại.

Không tạo state machine, mastery model, AI client hoặc runner thứ hai.

## 4. Trạng thái hiện tại

### 4.1 Đã có

- Sáu exercise database-backed cùng public, hidden và transfer test IDs curated.
- Catalog validation và command đồng bộ không chạy ở request time.
- Plan evidence bắt buộc trước First Attempt.
- Code, reasoning, confidence và revision history được lưu append-only.
- Runner status gồm `PASSED`, `OUTPUT_MISMATCH`, `LOGIC_ERROR`, `SYNTAX_ERROR`, `RUNTIME_ERROR`, `TIMEOUT`, `NOT_EXECUTED` và legacy `FAILED`.
- Diagnosis, misconception history, Hint Ladder bốn cấp và explicit acknowledgement khi reveal đáp án.
- Teach-Back theo rubric từng concept, hỗ trợ AI semantic grading và deterministic fallback.
- Transfer Check dùng test/task khác, khóa AI/hint và hỗ trợ retry sau `NOT_EXECUTED`.
- Mastery cần original pass, Teach-Back clear, transfer pass, unassisted và không lặp misconception.
- Recommendation `NEEDS_REVIEW` lấy từ rubric/concept thay vì hard-code cho loop.
- Runner status có learner-facing guidance và vẫn giữ raw evidence.
- Reset kết thúc session cũ nhưng không xóa learning evidence.
- Test settings mặc định offline, không dùng API key hoặc auto-start runner từ `.env`.
- Coding/progress access được giới hạn theo browser session key.

### 4.2 Còn cần hoàn thiện

- Audit đầy đủ nội dung, final reveal và transfer separation của cả sáu exercise.
- Mở rộng regression matrix để từng concept family có các nhánh pass/fail/error quan trọng.
- Làm progress dashboard kể được learning journey thay vì chủ yếu liệt kê record.
- Sửa UI Coding cho responsive, keyboard và accessibility.
- Bổ sung E2E browser smoke thực tế.
- Chuẩn hóa local demo startup, runner readiness và fallback khi AI/runner unavailable.

## 5. Invariant bắt buộc

Mọi thay đổi phải giữ các điều kiện sau:

- Không có AI/hint trước khi First Attempt hợp lệ được lưu.
- Plan, code, reasoning và confidence được backend kiểm tra.
- AI hỏi chẩn đoán trước khi đưa direct help.
- Hint tăng cấp theo thứ tự và cần learner action mới.
- Model output không thể đặt workflow state hoặc mastery.
- Original code pass không tự tạo mastery.
- Teach-Back chỉ mở sau runner-verified `PASSED`.
- Transfer Check chỉ mở sau Teach-Back hợp lệ hoặc assisted completion đã được acknowledge.
- AI/hints bị khóa trong Transfer Check.
- `NOT_EXECUTED` không tạo mastery và không làm mất submission.
- Hidden expected/actual và reference solution không tới browser hoặc AI provider trái policy.
- Learner code chỉ đi qua isolated execution boundary.
- Attempts, hints, misconceptions, Teach-Back, transfer và mastery evidence không bị silently overwrite.

## 6. Rủi ro ưu tiên

### P0 — Trước local demo

1. Local runner cần Docker Desktop/WSL2 và phải được kiểm tra readiness trước khi chạy bài.
2. Runner local vẫn cần giữ authentication boundary, resource limits, image lifecycle và không log dữ liệu nhạy cảm.
3. Cần một full Coding journey chạy local mà không sửa database thủ công.

### P1 — Chất lượng Coding demo

1. Cần regression matrix rõ cho cả sáu exercise, đặc biệt syntax/runtime/hidden failure và transfer failure.
2. Progress detail cần trình bày Teach-Back và evidence theo field có label, không dump JSON thô.
3. Dashboard có nguy cơ N+1 khi đếm attempts, Teach-Back và transfer theo từng session.
4. Label AI phải phân biệt “configured” với health check thực tế.
5. Double-submit và concurrent request cần được kiểm tra ở các action tạo evidence.

### P2 — UX và maintainability

1. Progress bar Coding có bảy stage nhưng desktop CSS cần bảo đảm hiển thị đúng bảy cột.
2. Navbar và Coding forms cần mobile layout, keyboard flow, focus handling và error summary tốt hơn.
3. Inline styles trong progress detail cần chuyển về stylesheet.
4. Cần quyết định system font/self-hosted font và CSP-compatible asset loading.
5. Cần automated accessibility smoke và manual 320px/200% zoom checks.

## 7. Kế hoạch triển khai

### Giai đoạn 0 — Coding scope và baseline

Trạng thái: cần duy trì tài liệu, không mở rộng tính năng.

Mục tiêu:

- Chốt Coding-only demo dựa trên sáu exercise hiện có.
- Định nghĩa một acceptance journey từ Coding home đến `MASTERED` và một journey đến `NEEDS_REVIEW`.
- Giữ handoff và tài liệu đồng bộ với code/test hiện tại.

File chính:

- `README.md`
- `GEMINI_PROJECT_HANDOFF.md`
- Có thể thêm `CODING_DEMO_ACCEPTANCE.md`

Điều kiện nghiệm thu:

- Tài liệu không tuyên bố các subject khác đã hoạt động end-to-end.
- Số exercise, workflow state và test command khớp repository.

### Giai đoạn 1 — Deterministic Coding test baseline

Trạng thái: đã triển khai.

Mục tiêu:

- Test mặc định chạy offline, không dùng secret/network/Docker ngoài ý muốn.
- Khóa các invariant của Coding workflow trước khi sửa domain/UI.

Đã thực hiện:

- Tắt external AI provider, runner URL và runner autostart trong `config.settings_test`.
- Thêm regression cho test isolation, mastery recommendation và safe fallback.
- Giữ live AI/runner integration ở chế độ opt-in.

Điều kiện tiếp tục duy trì:

- Full suite ổn định cả trên máy có và không có `.env`.
- Không có migration drift.

### Giai đoạn 2 — Harden sáu Coding exercises

Trạng thái: phần core đã triển khai; tiếp tục audit regression matrix.

Mục tiêu:

- Mỗi exercise có rubric, misconception, recommendation, final reveal và transfer task đúng concept.
- Runner/AI failures có thông báo rõ và không làm mất evidence.

Đã thực hiện:

- Recovery guidance theo rubric cho loop, dictionary, function và list indexing.
- Catalog validation chặn recommendation mapping thiếu hoặc sai code.
- Chuẩn hóa learner-facing feedback cho mọi runner status.
- Hiển thị riêng trạng thái runner chưa cấu hình, đã cấu hình nhưng unavailable và configured/ready.
- Có browser journey tới mastery cho các concept family hiện có.
- Thêm contract regression cho cả sáu exercise: revision reveal, Teach-Back rubric, original/transfer test IDs và không overlap test.

Việc còn lại:

- Audit source/reference/final reveal của cả sáu exercise.
- Bổ sung ma trận test tối thiểu cho mỗi exercise:
  - original pass;
  - public output mismatch;
  - hidden logic failure;
  - syntax/runtime failure;
  - Teach-Back clear/partial;
  - transfer pass/fail/`NOT_EXECUTED`;
  - repeated misconception dẫn tới `NEEDS_REVIEW`.
- Kiểm tra double-submit, PRG redirect và idempotency cho mọi action tạo evidence.
- Giữ một opt-in real Docker journey cho mỗi concept family nếu môi trường cho phép.

File chính:

- `apps/coding_quiz/catalog.py`
- `apps/coding_quiz/catalog_validation.py`
- `apps/coding_quiz/services.py`
- `apps/coding_quiz/views.py`
- `apps/coding_quiz/templates/coding_quiz/*`
- `runner_service/harness.py`
- Tests tương ứng

Điều kiện nghiệm thu:

- Không có invalid transition hoặc mastery sớm.
- Hidden evidence không bị lộ.
- Recommendation cuối đúng exercise/concept.
- Runner/AI unavailable vẫn giữ session có thể tiếp tục hoặc retry.

### Giai đoạn 3 — Coding progress evidence dashboard

Trạng thái: phần core đã triển khai; tiếp tục audit regression matrix.

Mục tiêu:

- Biến dữ liệu Coding đã lưu thành câu chuyện học tập dễ hiểu và có thể demo.

Cách triển khai:

- Tạo service/query layer cho Coding progress summary.
- Annotate/prefetch counts để tránh N+1.
- Hiển thị cho mỗi Coding session:
  - exercise và concept;
  - current/final state;
  - số attempts và confidence change;
  - highest hint level;
  - latest unresolved/repeated misconception;
  - Teach-Back result;
  - transfer result;
  - mastery reason và recommendation.
- Render Teach-Back response theo từng field có label.
- Hiển thị nguồn AI/curated fallback mà không lộ request context nhạy cảm.
- Không tự tạo retention hoặc agency metrics khi chưa có dữ liệu/định nghĩa đáng tin cậy.

File chính:

- `apps/progress/services.py`
- `apps/progress/views.py`
- `apps/progress/templates/progress/dashboard.html`
- `apps/progress/templates/progress/session_detail.html`
- `apps/progress/tests.py`
- `static/css/base.css`

Điều kiện nghiệm thu:

- Người xem hiểu learner đã thử gì, sai ở đâu, nhận hỗ trợ mức nào và vì sao đạt/chưa đạt mastery.
- Browser A không đọc được Coding session của browser B.
- Query count không tăng tuyến tính bất hợp lý theo số session.

### Giai đoạn 4 — Coding UI, responsive và accessibility

Trạng thái: đã triển khai các cải tiến UI/accessibility; cần kiểm tra manual keyboard end-to-end và zoom 200% trước khi phát hành.

Mục tiêu:

- Hoàn thành một Coding session bằng keyboard trên laptop và mobile viewport.

Cách triển khai:

- Sửa progress bar bảy stage.
- Làm Coding exercise page và navbar responsive ở 320/768/1024px.
- Thêm skip link, landmarks, visible focus, form error summary và field associations.
- Bảo đảm submit/loading/double-submit state rõ ràng.
- Chuyển inline styles sang CSS.
- Audit contrast, zoom 200%, reduced motion và font/CSP strategy.

Đã thực hiện:

- Progress bar hiển thị đủ bảy stage và chuyển sang lưới hai cột ở màn hình hẹp.
- Navbar, các panel và button row đáp ứng viewport 320px; mobile smoke không có horizontal overflow.
- Thêm skip link, landmark `main`, focus indicator, live region cho message và back link có URL thực.
- Form lỗi có error summary, liên kết tới field, `aria-invalid`/`aria-describedby`; error summary nhận focus sau response lỗi.
- Submit form biểu thị `aria-busy`, vô hiệu hóa nút để tránh double-submit và vẫn giữ đúng action của Revision.

File chính:

- `templates/base.html`
- `templates/components/*`
- `apps/coding_quiz/templates/coding_quiz/*`
- `apps/progress/templates/progress/*`
- `static/css/base.css`

Điều kiện nghiệm thu:

- Không overflow ở viewport mục tiêu.
- Keyboard-only journey hoàn thành được Coding workflow.
- Form errors được liên kết và focus không bị mất sau submit.

### Giai đoạn 5 — Local demo runner và khả năng tái lập

Trạng thái: đã triển khai và kiểm chứng local demo end-to-end.

Mục tiêu:

- Có một local Coding demo chạy được với Django và isolated runner riêng.

Cách triển khai:

- Khởi động Docker Desktop ở chế độ Linux containers/WSL2.
- Build và chạy `runner_service` local tại `127.0.0.1:8765`.
- Chạy Django local tại `127.0.0.1:8004`.
- Kiểm tra runner health trước khi submit code và giữ `NOT_EXECUTED` retry-safe khi runner tắt.
- Không log learner code, API keys, runner token hoặc hidden expected values.
- Rehearse một Coding journey đầy đủ từ Plan tới Mastery bằng database local.

Đã thực hiện:

- `runner_service/start.ps1` hỗ trợ build đầy đủ hoặc restart nhanh với `-SkipBuild`.
- Thêm `manage.py check_local_demo` để kiểm tra Django, catalog và runner `/health`.
- Bổ sung hướng dẫn hai terminal trong `README.md` và `runner_service/README.md`.
- Giữ fallback `NOT_EXECUTED` retry-safe khi runner dừng hoặc Docker unavailable.

File chính:

- `runner_service/README.md`
- `.env.example`
- `runner_service/start.ps1`
- `runner_service/*`
- `apps/code_runner/*`
- Có thể thêm CI workflow và health endpoints

Điều kiện nghiệm thu:

- Django local và runner local hoạt động độc lập.
- Runner health trả về thành công trước khi submit.
- Coding happy path và fallback path đều chạy được.
- Có hướng dẫn khởi động lại và phương án demo khi AI hoặc runner lỗi.

## 8. Definition of Done cho Coding

### Learning workflow

- [x] Learner chọn được một trong sáu Python exercises.
- [x] Understand & Plan bắt buộc trước First Attempt.
- [x] Code, reasoning và confidence được lưu.
- [x] AI/hint permissions được backend enforce.
- [x] Diagnosis xảy ra trước progressive hints.
- [x] Mỗi hint cần learner action mới.
- [x] Teach-Back chỉ mở sau runner-verified pass.
- [x] Transfer dùng task/test khác và khóa AI/hints.
- [x] Mastery có stored evidence và recommendation đúng concept.
- [x] Reset không xóa history.

### Catalog và evaluation

- [x] Cả sáu exercise pass catalog validation.
- [x] Public, hidden và transfer test IDs không overlap sai quy tắc.
- [x] Final reveal, rubric và misconception mapping đúng từng exercise.
- [x] Mọi runner status có hành vi fail-safe và thông báo phù hợp.
- [x] Hidden expected/actual không tới browser/provider/log.
- [x] Invalid AI output dùng curated fallback và không đổi mastery.

### Data và security

- [x] Learner code không chạy trong Django process.
- [x] Attempts/evidence quan trọng được lưu append-only.
- [x] Browser-session ownership tests pass.
- [x] Test settings không gọi external provider/runner mặc định.
- [x] Runner local giữ boundary riêng, authenticated và resource-bounded.
- [x] SQLite local smoke và full Coding journey đều pass.

### UX và progress

- [x] Bảy stage hiển thị đúng trên desktop/mobile.
- [ ] Coding journey dùng được bằng keyboard.
- [x] Form labels, errors, focus và contrast đạt yêu cầu.
- [x] Progress detail không dump Teach-Back JSON thô.
- [x] Dashboard không có N+1 đáng kể.
- [x] Người xem hiểu được evidence dẫn tới `MASTERED` hoặc `NEEDS_REVIEW`.

### Local demo

- [x] Django local và runner local có hướng dẫn khởi động rõ ràng.
- [x] Có ít nhất một full Coding journey được rehearsal.
- [x] Có fallback khi AI unavailable.
- [x] Có retry/fallback plan khi runner unavailable.
- [ ] Không cần sửa database hoặc bypass state machine trong demo.

## 9. Lệnh kiểm tra bắt buộc

```powershell
cd D:\study\gpbl\AI-thinking-review
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
venv\Scripts\python.exe manage.py validate_coding_catalog --json
venv\Scripts\python.exe manage.py sync_coding_catalog --dry-run
venv\Scripts\python.exe manage.py check_local_demo --skip-runner
venv\Scripts\python.exe manage.py test --settings=config.settings_test --durations 10
git diff --check
git status --short
```

Runner local, chỉ khi chủ động kiểm thử integration:

```powershell
powershell -ExecutionPolicy Bypass -File runner_service\start.ps1
```

AI provider health check, chỉ khi chủ động kiểm thử integration:

```powershell
venv\Scripts\python.exe manage.py check_ai_provider
```

Local demo verification:

```powershell
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
venv\Scripts\python.exe manage.py migrate --noinput
Invoke-WebRequest http://127.0.0.1:8765/health
```

## 10. Hướng dẫn cho Codex

1. Đọc file này và `CODING_WORKFLOW.md` trước khi thay đổi Coding behavior.
2. Kiểm tra Git status và giữ nguyên thay đổi không thuộc task.
3. Chỉ triển khai một giai đoạn hoặc một Coding vertical slice nhỏ mỗi lần.
4. Truy vết view → service → state/model → AI/runner → template/test trước khi sửa.
5. Không sửa module môn khác trừ dependency trực tiếp cần cho Coding.
6. Không đổi learning rule chỉ để đơn giản hóa UI.
7. Không tạo duplicate architecture.
8. Model change phải có migration; behavior change phải có focused regression test.
9. Chạy focused tests, full offline suite và các gate ở Mục 9.
10. Báo cáo file đã đổi, hành vi đã xác minh và giới hạn còn lại; không tuyên bố hoàn tất khi critical Coding flow chưa được chạy.

Bước triển khai tiếp theo: **Giai đoạn 3 — Coding progress evidence dashboard**, đồng thời tiếp tục bổ sung regression matrix còn thiếu của Giai đoạn 2 nếu phát hiện gap trong quá trình audit.

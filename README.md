# AI-thinking

Production deployment and security settings are documented in [`PRODUCTION.md`](PRODUCTION.md).
Coding exercise authoring and import are documented in [`CODING_CATALOG.md`](CODING_CATALOG.md).

[日本語](#日本語) | [English](#english) | [Tiếng Việt](#tiếng-việt)

---

## 日本語

### テーマ

AIを当たり前に使う時代に、学生が自分で考え、判断し、成長できる学びをデザインせよ

### 技術スタック

- Python / Django
- 必要になったらライブラリを追加していく（現時点では未確定）

### セットアップ（Mac / Linux）

```bash
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py migrate
python manage.py runserver
```

### セットアップ（Windows）

PowerShellの場合：

```powershell
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py migrate
python manage.py runserver
```

コマンドプロンプトの場合：

```cmd
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py runserver
```

### トラブルシューティング（Windows）

**必要なPythonバージョン**：Python 3.10以上が必要です（`python --version` で確認できます）。インストールされていない場合は [python.org](https://www.python.org/downloads/) からダウンロードし、インストール時に「Add python.exe to PATH」に必ずチェックを入れてください。

**「このシステムではスクリプトの実行が無効になっています」と出る場合**：PowerShellで下記を実行してから、もう一度 `venv\Scripts\Activate.ps1` を試してください。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**「'python' は、内部コマンドまたは外部コマンド...として認識されていません」と出る場合**：Pythonがインストールされていないか、PATHが通っていません。上記のPythonインストール手順を確認してください。

---

## English

### Theme

Design a learning experience that lets students think, judge, and grow for themselves in an era where using AI is taken for granted.

### Tech Stack

- Python / Django
- More libraries may be added later as needed (not yet decided)

### Setup (Mac / Linux)

```bash
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py migrate
python manage.py runserver
```

### Setup (Windows)

PowerShell:

```powershell
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py migrate
python manage.py runserver
```

Command Prompt:

```cmd
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py runserver
```

### Troubleshooting (Windows)

**Required Python version**: Python 3.10 or later is required (check with `python --version`). If not installed, download it from [python.org](https://www.python.org/downloads/) and make sure to check "Add python.exe to PATH" during installation.

**If you see "running scripts is disabled on this system"**: Run the following in PowerShell, then try `venv\Scripts\Activate.ps1` again.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**If you see "'python' is not recognized as an internal or external command"**: Python is not installed, or not added to PATH. Follow the installation steps above.

### Local isolated Coding runner

The Coding workflow requires a separate Docker-backed HTTP runner before a revision can be verified as `PASSED`. See [`runner_service/README.md`](runner_service/README.md). Without that service, submissions safely remain `NOT_EXECUTED` and cannot unlock Teach-Back or Mastery.

### Coding exercise catalog and history

`python manage.py migrate` creates and seeds the initial database-backed Coding catalog. The
catalog currently contains `double-numbers`, `square-numbers`, `increment-numbers`, and
`lookup-dictionary-grade`, `safe-divide-function`, and `first-list-item`; prompts,
rubrics, public/hidden runner IDs, and Transfer Check configuration are selected per exercise.
Opening `/coding/` lists active exercises. Each browser can keep one active session per exercise,
while Reset closes the current session instead of deleting it. Previous code attempts, Teach-Back
evidence, misconceptions, Transfer Checks, and mastery decisions remain available under
`/progress/`.

### Use MySQL on Windows

Install MySQL Server 8 on Windows, create an `utf8mb4` database and a dedicated user, then set:

```env
DB_ENGINE=mysql
DB_NAME=ai_thinking
DB_USER=ai_thinking_user
DB_PASSWORD=replace_with_your_password
DB_HOST=127.0.0.1
DB_PORT=3306
```

Install dependencies and initialize the new database:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py check
```

The session uniqueness rule uses a nullable active slot instead of a conditional index, so it is
enforced by MySQL while still allowing any number of ended sessions to remain as history.

### Optional DeepSeek or Gemini AI Coach

DeepSeek is the preferred fallback when Gemini quota is unavailable. Add a DeepSeek API key to
`.env`; the adapter uses the OpenAI-compatible HTTP endpoint and requires no additional SDK:

```env
DEEPSEEK_API_KEY=your-key-here
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
AI_PROVIDER_CLASS=apps.ai_engine.providers.deepseek.DeepSeekProvider
```

Gemini remains available by configuration:

```env
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash
AI_PROVIDER_CLASS=apps.ai_engine.providers.gemini.GeminiProvider
```

To enable semantic AI grading for Teach-Back, put one provider key in the local `.env`, run
`venv\Scripts\python.exe -m pip install -r requirements.txt`, and restart Django. The Coding page
will then show `Live AI provider available`. Teach-Back sends the current exercise's rubric and the
learner's answers to the selected provider; the server validates the structured response and retains
control of progression. Without a key, it shows `Curated fallback ready` and remains usable.

Verify the configured provider with a data-free structured request before a demo:

```powershell
venv\Scripts\python.exe manage.py check_ai_provider
```

The command reports only a safe status code and latency; it never prints the API key.

Do not commit or paste either key into source code. When `AI_PROVIDER_CLASS` is omitted, Django
selects DeepSeek when `DEEPSEEK_API_KEY` is present, otherwise Gemini when `GEMINI_API_KEY` is
present. The Coding Diagnosis sends only privacy-minimized
signals: the target concept, confidence, execution category, aggregate test counts, and boolean
code-structure features. Raw learner source code and reasoning are not sent to the provider. Provider
failure or invalid structured output falls back to the curated diagnostic question.
The Coding page shows whether the session is using a live provider, a configured-but-workflow-locked
provider, or the always-available curated fallback. This status is local configuration only and does
not make a network health request.

---

## Tiếng Việt

### Chủ đề

Trong thời đại AI được sử dụng như một điều hiển nhiên, hãy thiết kế một trải nghiệm học tập giúp sinh viên tự suy nghĩ, tự phán đoán và tự trưởng thành.

*(Bản dịch tiếng Việt được tạo tự động, mong các bạn thành viên người Việt kiểm tra lại giúp.)*

### Công nghệ sử dụng

- Python / Django
- Có thể bổ sung thêm thư viện khác khi cần thiết (hiện tại chưa xác định)

### Cài đặt (Mac / Linux)

```bash
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py runserver
```

### Cài đặt (Windows)

PowerShell:

```powershell
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py runserver
```

Command Prompt:

```cmd
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python -c "from django.core.management.utils import get_random_secret_key; open('.env','w').write(f'SECRET_KEY={get_random_secret_key()}\n')"
python manage.py runserver
```

### Xử lý sự cố (Windows)

**Phiên bản Python cần thiết**: Cần Python 3.10 trở lên (kiểm tra bằng `python --version`). Nếu chưa cài đặt, hãy tải từ [python.org](https://www.python.org/downloads/) và nhớ tích vào "Add python.exe to PATH" khi cài đặt.

**Nếu gặp lỗi "running scripts is disabled on this system"**: Chạy lệnh sau trong PowerShell, sau đó thử lại `venv\Scripts\Activate.ps1`.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Nếu gặp lỗi "'python' is not recognized as an internal or external command"**: Python chưa được cài đặt, hoặc chưa được thêm vào PATH. Làm theo các bước cài đặt ở trên.

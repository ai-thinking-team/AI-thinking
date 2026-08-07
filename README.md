# AI-thinking

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
python manage.py runserver
```

コマンドプロンプトの場合：

```cmd
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
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
python manage.py runserver
```

Command Prompt:

```cmd
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python manage.py runserver
```

### Troubleshooting (Windows)

**Required Python version**: Python 3.10 or later is required (check with `python --version`). If not installed, download it from [python.org](https://www.python.org/downloads/) and make sure to check "Add python.exe to PATH" during installation.

**If you see "running scripts is disabled on this system"**: Run the following in PowerShell, then try `venv\Scripts\Activate.ps1` again.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**If you see "'python' is not recognized as an internal or external command"**: Python is not installed, or not added to PATH. Follow the installation steps above.

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
python manage.py runserver
```

Command Prompt:

```cmd
git clone https://github.com/ai-thinking-team/AI-thinking.git
cd AI-thinking
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python manage.py runserver
```

### Xử lý sự cố (Windows)

**Phiên bản Python cần thiết**: Cần Python 3.10 trở lên (kiểm tra bằng `python --version`). Nếu chưa cài đặt, hãy tải từ [python.org](https://www.python.org/downloads/) và nhớ tích vào "Add python.exe to PATH" khi cài đặt.

**Nếu gặp lỗi "running scripts is disabled on this system"**: Chạy lệnh sau trong PowerShell, sau đó thử lại `venv\Scripts\Activate.ps1`.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Nếu gặp lỗi "'python' is not recognized as an internal or external command"**: Python chưa được cài đặt, hoặc chưa được thêm vào PATH. Làm theo các bước cài đặt ở trên.

# Iris (Phase 1)

Windows용 로컬 우선 개인 AI 비서 Iris입니다. PyQt6 UI, Gemma 4 로컬 API(Ollama/LM Studio 호환), 승인 기반 자동화, Playwright 웹 검색을 포함합니다.

## 요구 사항

- Python 3.11+
- Windows

## 설치

PowerShell에서 앱 루트(`iris` 폴더)로 이동한 뒤:

```powershell
.\install.ps1
```

`.env.example`을 복사해 `.env`를 만들고 Ollama/LM Studio 주소와 모델명을 맞춥니다.

Chromium(Playwright):

```powershell
python -m playwright install chromium
```

## 실행

```powershell

cd "C:\Users\kwakm\OneDrive\Desktop\Cusor-Project\IRIS\iris"

.\.venv\Scripts\python.exe -m iris

python -m iris
```

또는 `run.bat` 더블클릭.

## 검증

```powershell
python -m compileall iris -q
```

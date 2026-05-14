# AGENTS.md

## Project Name

Iris

## Project Definition

Iris is a local-first personal AI assistant for Windows.

Iris is not just a chatbot.  
It is a Jarvis-like AI assistant that can talk with the user, launch applications, arrange windows, perform approved computer actions, search the web, generate reports, and monitor multiple ongoing tasks across apps, browser tabs, terminal logs, and the current screen.

Core concept:

"Iris does not only execute what the user commands. Iris watches the user's workflow, detects missed or stalled tasks, and helps continue them."

## Core Principles

1. The project name must always be Iris.
2. Do not use DEXTER as a project name.
3. Use Gemma 4 local LLM as the primary model direction.
4. Do not use Claude or Gemini API as the default model.
5. Claude/Gemini may only be optional fallback or testing tools if explicitly requested.
6. All computer control actions require user approval.
7. Never execute keyboard input, mouse clicks, shell commands, file operations, payments, or personal data submission without user confirmation.
8. Do not store raw screenshots by default.
9. Do not store full OCR text by default.
10. Store only summarized events, logs, and user-approved action records.
11. Keep AI assistant features and monitoring features separated by modules.
12. Build the system in phases. Do not implement everything in one file.

## Main Features

### Phase 1: Jarvis-like AI Assistant

- Text chat
- Voice input
- Voice response
- Barge-in while Iris is speaking
- Gemma 4 local LLM connection
- Fallback response when local LLM is unavailable
- App launching
- Window focusing
- Window arrangement
- Work mode
- Game mode
- Creative mode
- Web search through Playwright
- Report window
- Recent work suggestion
- User-approved computer control
- Safety guard
- SQLite logs

### Phase 2: Hybrid Monitoring

- Terminal command stdout/stderr monitoring
- Existing terminal window monitoring using UI Automation and OCR
- Cursor / VS Code window monitoring
- Chrome tab monitoring through Chrome Extension
- ChatGPT / Gemini / Discord / Midjourney tab status detection
- Current screen OCR
- Windows Event Log as supporting source
- VLM adapter for future visual understanding
- Event detection
- Alert generation
- Notification panel
- User-approved action after alerts

## Recommended Tech Stack

- Python 3.11+
- PyQt6
- SQLite
- Gemma 4 local LLM
- Ollama or LM Studio compatible local API
- faster-whisper or whisper for STT
- pyttsx3 or edge-tts for TTS
- Playwright for web agent
- pywinauto
- pygetwindow
- pyautogui
- pywin32
- psutil
- pytesseract or easyocr
- Chrome Extension Manifest V3
- Optional future VLM: SmolVLM2 or similar lightweight model

## Safety Rules

The following actions must be blocked or require explicit approval:

- File deletion
- Payment
- Password input
- Personal information submission
- System setting changes
- Shell commands that modify or delete user files
- Keyboard/mouse control without confirmation
- Browser actions involving login, payment, or private forms

## Coding Rules

- Keep modules small.
- Use clear responsibility separation.
- Add Korean comments for important logic.
- Use type hints where practical.
- Avoid hardcoding personal paths.
- Put app paths in config/app_paths.py.
- Put mode presets in config/preset_modes.py.
- Store logs in SQLite.
- Add fallback behavior for optional components.
- Never make the app crash just because STT, TTS, OCR, or LLM is unavailable.


---

# `AGENTS.md`에 추가할 내용

`AGENTS.md`에 아래 섹션을 추가하세요.

```md
## Code Convention

All code must follow `docs/code-convention.md`.

Important rules:
- Use Python 3.11+.
- Use snake_case for files, functions, and variables.
- Use PascalCase for classes.
- Use type hints for public functions.
- Keep UI, AI, automation, monitoring, storage, and safety layers separated.
- Do not put multiple unrelated responsibilities in one file.
- Do not execute computer actions without user approval.
- Do not store raw screenshots or full OCR text by default.
- Use Korean comments for important logic.

## Testing Rule

Before considering an implementation complete, check:

```bash
python -m compileall iris -q

The app should run with:

python -m iris
Definition of Done

A feature is done when:

It runs without crashing.
It has fallback behavior.
It respects user approval.
It logs important events.
It does not break existing assistant features.
It follows the local-first design.



---

# 8. `docs/safety-policy.md`

```md
# Iris Safety Policy

## 1. Core Rule

Iris must never control the user's computer without explicit user approval.

---

## 2. Actions Requiring Approval

The following always require approval:

- Launching an app
- Closing an app
- Moving or resizing windows
- Typing into a window
- Pressing keys
- Clicking buttons
- Opening websites
- Running shell commands
- Sending emails
- Submitting forms
- Starting work mode
- Starting game mode
- Starting creative mode

---

## 3. Blocked Actions

The following actions are blocked by default:

- File deletion
- Folder deletion
- Disk formatting
- Payment
- Purchase
- Password input
- Personal data submission
- Changing system settings
- Disabling security features
- Running destructive shell commands
- Sending messages without user confirmation
- Sending emails without user confirmation

---

## 4. Sensitive Monitoring Areas

Iris must not monitor or store content from:

- Password fields
- Payment pages
- Banking pages
- Private documents
- Personal identification forms
- Login forms
- Medical or legal private pages

If detected, Iris should say:

"민감한 화면으로 보입니다. 이 화면은 모니터링하지 않겠습니다."

---

## 5. Data Storage Policy

Default behavior:

- Do not store raw screenshots.
- Do not store full OCR text.
- Do not store full browser page text.
- Store summarized events only.
- Store action logs only after user approval flow.

---

## 6. Approval Flow

Before executing any action:

1. Create ActionRequest.
2. Classify risk.
3. Ask user for approval.
4. If approved, execute.
5. If denied, cancel.
6. Log result.

Example:

Iris:
"터미널이 y 입력을 기다리고 있습니다. 제가 입력할까요?"

User:
"응."

Iris:
"승인 확인. 터미널에 y를 입력합니다."

---

## 7. Dangerous Command Detection

Block commands containing:

- rm -rf
- del /s
- format
- shutdown
- registry modification
- password submission
- payment confirmation

---

## 8. Monitoring Alert Safety

When monitoring detects an issue, Iris should recommend actions but not execute automatically.

Example:

Allowed:
"터미널이 승인 대기 중입니다. y 입력이 필요합니다."

Not allowed:
Automatically typing "y" without approval.
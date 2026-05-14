# Iris Architecture

## 1. System Overview

Iris is a local-first AI assistant with two major capabilities:

1. Jarvis-like personal AI assistant
2. Hybrid multi-target workflow monitoring

---

## 2. Layered Architecture

```text
Iris
├── UI Layer
├── Assistant Layer
├── AI Layer
├── Audio Layer
├── Automation Layer
├── Mode Layer
├── Monitoring Layer
├── Safety Layer
└── Storage Layer

3. UI Layer

Path:

iris/ui/

Responsibilities:

Main window
Chat panel
Visualizer
Mode dialog
Monitoring dashboard
Notification panel
Report window
4. AI Layer

Path:

iris/ai/

Responsibilities:

Gemma 4 local LLM connection
Prompt building
Response parsing
Fallback response

Primary model:

Gemma 4 local

Optional:

Other APIs only if explicitly requested
5. Assistant Layer

Path:

iris/assistant/

Responsibilities:

Agent adapter
OpenCLO/OpenClaw adapter
Task planning
Safety guard connection
6. Automation Layer

Path:

iris/automation/

Responsibilities:

App launching
Window focusing
Window arrangement
Keyboard input
Mouse clicking
Action execution

Rule:
All actions require user approval.

7. Mode Layer

Path:

iris/modes/

Responsibilities:

Work mode
Game mode
Creative mode
Recent work suggestion
User confirmation before execution

Work mode flow:

User says: "작업 시작할게"
Iris asks what work to start.
Iris suggests recent work.
User selects or creates new work.
Iris asks for confirmation.
Iris launches apps and arranges windows.

Game mode flow:

User says: "게임할래"
Iris asks which game.
Iris suggests related apps.
User confirms.
Iris launches game environment.
8. Monitoring Layer

Path:

iris/monitoring/

Responsibilities:

Register monitoring targets
Collect status from each target
Detect stalled tasks
Generate alerts
Connect alert to user-approved action

Target-specific monitoring:

Target	Method
Iris-launched terminal command	stdout/stderr
Existing terminal window	UI Automation + OCR
Cursor / VS Code	UI Automation + OCR
Chrome tabs	Chrome Extension + DOM
Current screen	Screenshot + OCR
System errors	Windows Event Log
Complex visual state	Future VLM adapter
9. Safety Layer

Path:

iris/assistant/safety_guard.py

Responsibilities:

Risk classification
Approval enforcement
Dangerous action blocking
Log blocked actions
10. Storage Layer

Path:

iris/storage/

Database:

SQLite

Tables:

logs
actions
recent_work
targets
events
recent_target_states
11. Main Flow
User input
→ Command Router
→ Intent classification
→ Gemma 4 / rule-based decision
→ If action needed: ask confirmation
→ Safety Guard
→ Action Executor
→ Log result
→ Respond to user
12. Monitoring Flow
Monitoring target
→ Target-specific collector
→ State Detector
→ Monitoring Event
→ Alert Generator
→ Gemma 4 summary
→ Notification Panel
→ User approval if action needed
→ Action Executor
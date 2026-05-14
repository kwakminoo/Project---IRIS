# Iris Implementation Plan

## Phase 0: Project Setup

Goal:
Create project rules and design documents.

Tasks:
- Create AGENTS.md
- Create .cursor/rules/iris.mdc
- Create docs/domain-design.md
- Create docs/architecture.md
- Create docs/safety-policy.md
- Create docs/implementation-plan.md
- Create .env.example

---

## Phase 1: Jarvis-like AI Assistant

Goal:
Build the base assistant before monitoring.

Tasks:
1. PyQt6 main window
2. Chat panel
3. Visualizer
4. State machine
5. Gemma 4 local LLM client
6. Fallback response
7. STT interface
8. TTS interface
9. Barge-in structure
10. App launcher
11. Window controller
12. Layout engine
13. Action executor
14. Safety guard
15. SQLite logs
16. Recent work manager
17. Work mode
18. Game mode
19. Creative mode
20. Playwright web agent
21. Report window

Validation:
- `python -m iris` opens app.
- Text chat works.
- Local LLM or fallback works.
- Work mode asks what work to start.
- Game mode asks which game to start.
- Actions require approval.
- Logs are saved.

---

## Phase 2: Basic Monitoring

Goal:
Add monitoring foundation.

Tasks:
1. target_registry
2. monitor_manager
3. current screen OCR
4. selected window OCR
5. state_detector
6. alert_generator
7. notification_panel
8. monitoring dashboard

Validation:
- Can register targets.
- Can detect approval waiting.
- Can detect error text.
- Can show alerts.

---

## Phase 3: Hybrid Monitoring

Goal:
Use target-specific methods.

Tasks:
1. terminal_log_collector
2. desktop_window_monitor
3. browser_tab_monitor
4. Chrome Extension
5. windows_event_collector
6. vlm_adapter stub
7. event storage
8. cooldown
9. user-approved action after alert

Validation:
- Terminal stdout/stderr can be collected.
- Existing terminal window can be read through UI Automation or OCR.
- Chrome tab status can be sent from extension.
- Monitoring events are stored.
- Alerts do not repeat excessively.

---

## Phase 4: Integration

Goal:
Connect assistant and monitoring.

Tasks:
1. Monitoring event summary through Gemma 4
2. Alert-based confirmation flow
3. Action execution after approval
4. Log action result
5. Add dashboard controls

Validation:
- Iris detects terminal approval waiting.
- Iris asks user whether to act.
- User approves.
- Iris executes action.
- Result is logged.

---

## Phase 5: Polish

Goal:
Prepare for demo and competition.

Tasks:
1. UI polish
2. README
3. Demo scenarios
4. Error handling
5. Presentation script
6. Test data
7. Install script

Demo scenarios:
- Work mode start
- Game mode start
- Terminal approval waiting
- Midjourney generation failed
- GPT response ready
- Cursor build not started
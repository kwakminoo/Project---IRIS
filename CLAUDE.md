# CLAUDE.md

This project is Iris.

Iris is a local-first personal AI assistant for Windows.  
The main reference documents are:

1. AGENTS.md
2. .cursor/rules/iris.mdc
3. docs/domain-design.md
4. docs/architecture.md
5. docs/safety-policy.md
6. docs/implementation-plan.md

## Important Rules

- Do not rename the project.
- Do not use Dexter as the project name.
- Use Gemma 4 local LLM as the primary model direction.
- Do not make Claude API or Gemini API the default model.
- All computer control actions require user approval.
- Never bypass Safety Guard.
- Do not store raw screenshots or full OCR text by default.
- Keep assistant, automation, monitoring, UI, and storage layers separated.

## Implementation Style

Before editing code:
1. Read AGENTS.md.
2. Read docs/domain-design.md.
3. Read docs/architecture.md.
4. Read docs/safety-policy.md.
5. Explain the plan briefly.
6. Then modify code.

If a requested change conflicts with Safety Guard, refuse to implement it directly and suggest a safer approval-based alternative.
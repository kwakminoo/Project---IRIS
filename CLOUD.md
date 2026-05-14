# CLOUD.md

## Cloud Policy for Iris

Iris is designed as a local-first AI assistant.

The default architecture should not depend on cloud services for core functionality.

## Local-First Requirements

The following features should work locally whenever possible:

- LLM response through Gemma 4 local model
- Text chat
- App launching
- Window control
- User-approved keyboard and mouse control
- SQLite logging
- Basic monitoring
- OCR-based detection
- STT/TTS where possible

## Cloud Services

Cloud services are optional and must not be required for basic operation.

Examples of optional cloud use:

- External LLM API for testing
- Cloud TTS if local TTS is unavailable
- Cloud STT if local STT is unavailable
- Remote sync in future versions

## Restrictions

Do not send the following to cloud services by default:

- Raw screenshots
- Full OCR text
- Passwords
- Personal data
- Browser content from private pages
- Payment pages
- Login forms
- Sensitive documents

## Future Cloud Expansion

If Iris later supports cloud sync or user accounts, create a separate cloud architecture document.

For now, Iris must remain usable without cloud deployment.
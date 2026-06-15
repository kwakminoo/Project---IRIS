# IDE Context Bridge

## 프로토콜

- Schema: `protocol/ide-context.schema.json`, `protocol/ide-events.schema.json`
- Transport: localhost HTTP (`IdeBridgeClient`)

## Theia → Iris

`POST /context` — editor/workspace 변경 시

```json
{
  "type": "context.update",
  "workspace_path": "...",
  "active_file_uri": "file:///...",
  "active_file_language": "python",
  "selected_text": "...",
  "selection_range": {},
  "dirty_state": false
}
```

## Iris → Theia

`GET /commands` — polling  
명령 예: `{"type": "editor.open", "uri": "..."}`

## 차단 규칙

- `.env`, `id_rsa`, `.pem`, credentials
- binary 확장자

## 금지

- Theia → SQLite 직접 접근
- Safety 우회 파일 수정

# Theia Build and Runtime

## 최초 설정

```powershell
# IRIS 저장소 루트
.\scripts\setup-iris-ide.ps1
.\scripts\build-iris-ide.ps1
```

## 버전

- Eclipse Theia **1.55.0** (`iris-ide/package.json` resolutions)
- Node **20.18.1** (yarn `node-win-x64` 번들, native module ABI 일치)

## 빌드 산출물

| 경로 | 용도 |
|------|------|
| `iris-ide/applications/browser/lib/backend/main.js` | Backend entry |
| `iris-ide/applications/browser/lib/frontend/index.html` | Frontend |
| `iris-ide/applications/browser/lib/frontend/bundle.js` | JS bundle |

`IdeBackendManager._find_backend_entry()`는 위 경로를 우선 탐색합니다.

## Backend 실행

```powershell
.\scripts\start-iris-ide-backend.ps1 -Workspace "C:\path\to\project" -Port 3100
```

명령 구조:

```
node main.js <workspace> --hostname=127.0.0.1 --port=<port>
```

Working directory: `iris-ide/applications/browser`

브라우저에서 `http://127.0.0.1:3100` — Explorer·Editor·Terminal 확인.

## Clean build

1. Iris 및 IDE backend 프로세스 종료
2. `scripts\build-iris-ide.ps1` (내부에서 backend node 프로세스 정리)
3. `yarn.lock` 삭제 금지 — `yarn install --frozen-lockfile` 유지

`node_modules` 삭제는 ABI 오염이 확인된 경우에만.

## Health check (Iris)

- HTTP `/` — Theia HTML
- HTTP `/bundle.js` — frontend bundle
- 프로세스 45초 내 유지

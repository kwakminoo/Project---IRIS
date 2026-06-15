# Workspace 전환 UX

## Toggle

| 현재 | 버튼 | 동작 |
|------|------|------|
| Assistant | `IDE` | Backend 시작 → IDE page |
| IDE | `돌아가기` | Assistant page (Backend 유지) |

## 상태 보존

- Chat 기록·Task·Monitoring: Assistant page 인스턴스 유지
- Theia 열린 파일·터미널: Backend 유지
- Splitter 비율: workspace별 `saveState`/`restoreState`

## 오류

Theia 시작 실패 시 Iris는 계속 동작. 재시도·로그·복귀 버튼 제공.

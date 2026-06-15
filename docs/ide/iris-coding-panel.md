# Iris Coding Panel

## 구성

- **IrisOrbWidget** — `ParticleVisualizer` 재사용 (compact)
- **CodingChatView** — 대화 기록 + 텍스트/음성 입력
- **상태 라벨** — `AppState` 동기화

## 파이프라인

```
CodingChatView.send_clicked
  → MainWindow._on_coding_user_text
  → IDE context 첨부 (선택·활성 파일)
  → AgentWorker(TurnCoordinator) — 기존 IrisAssistant 재사용
```

## 이번 단계 한계

- 코드 자동 수정·Patch·Build/Test/Commit **미구현**
- 요청 시 설명·제안만 표시

## Context 표시

활성 파일·선택 영역은 입력창 위 summary 라벨에 표시됩니다.

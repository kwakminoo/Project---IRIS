# Iris Domain Design v2
## 아이리스 도메인 설계

- 문서 버전: `2.0-draft`
- 상태: Domain Modeling Draft
- 대상: Iris Core, Iris Workspace, Computer Use, Development, Monitoring, Automation, Evolution
- 기본 원칙: **Task 중심**, **도구 교체 가능**, **실행 전 정책 평가**, **실행 후 검증**, **복구 가능**, **사용자 통제 유지**

---

## 1. 문서 목적

이 문서는 아이리스가 단순한 대화형 비서가 아니라 다음 기능을 수행하는 **지속형 범용 작업 에이전트**로 발전하기 위한 핵심 도메인과 경계를 정의한다.

- 사용자의 자연어·음성 요청을 목표와 제약조건으로 해석
- 여러 단계의 작업 계획 수립 및 실행
- 컴퓨터 화면·애플리케이션·브라우저·터미널 조작
- 작업 진행 상태와 오류·승인 대기·완료 상태 모니터링
- 코드, 문서, 스프레드시트, 프레젠테이션, PDF, 이미지 처리
- 코드 작성·테스트·리팩터링·Git 변경 관리
- 아이리스 플러그인과 신규 기능 개발
- 후보 버전을 통한 제한적 자기 개선
- 위험 작업의 승인, 감사, 복구 및 롤백

아이리스의 핵심은 특정 IDE나 특정 AI 모델이 아니다.

> **아이리스의 핵심 도메인은 사용자의 목표를 Task로 관리하고, 적절한 Capability를 선택해 안전하게 실행하고, 결과를 검증·복구하는 Task Orchestration이다.**

Eclipse Theia, AI 모델, 데이터베이스, 운영체제 API, 외부 에이전트는 모두 교체 가능한 인프라 또는 어댑터로 취급한다.

---

## 2. 핵심 설계 원칙

### 2.1 Task-first

모든 실행 가능한 사용자 요청은 `UserUtterance`에서 직접 도구 호출로 이어지지 않는다.

```text
UserUtterance
→ IntentFrame
→ Task
→ Plan
→ PlanStep
→ ActionProposal
→ PolicyDecision
→ ActionAttempt
→ VerificationResult
→ TaskResult
```

단순 대화는 Task를 만들지 않을 수 있지만, 파일 수정·앱 실행·코딩·자동화·외부 전송 등 상태를 변경하는 요청은 원칙적으로 Task로 관리한다.

### 2.2 Capability-first

아이리스는 특정 앱이나 도구 이름이 아니라 필요한 기능을 요청한다.

```text
요구 기능: code.modify
가능한 Provider:
- Iris Native Coding Tool
- Theia Workspace Tool
- Cursor Adapter
- External Coding Agent
```

`CapabilityRouter`가 현재 환경, 정책, 정확성, 비용, 가용성에 따라 실제 Provider를 선택한다.

### 2.3 API before GUI

작업 방식 우선순위는 다음과 같다.

```text
1. 전용 API / 구조화된 파일 조작
2. 애플리케이션 공식 Automation API
3. LSP / DOM / UI Automation
4. 키보드 단축키
5. OCR / VLM 기반 GUI 조작
6. 좌표 기반 마우스 조작
```

화면 클릭은 범용 폴백이며 기본 수단이 아니다.

### 2.4 Verify every meaningful effect

도구가 성공을 반환한 것과 사용자의 목표가 달성된 것은 다르다.

```text
파일 저장 성공
≠
요구 기능 구현 성공
```

의미 있는 상태 변경 뒤에는 `VerificationResult`가 필요하다.

### 2.5 Safe self-improvement

아이리스는 실행 중인 자신의 원본 코드를 직접 덮어쓰지 않는다. 자기 개선은 별도 작업공간과 후보 버전에서 수행한다.

```text
현재 버전
→ Candidate Workspace
→ Build
→ Validation
→ Approval
→ Deployment
→ Health Check
→ Rollback 가능
```

### 2.6 User remains in control

아이리스는 사용자의 실제 입력, 포커스, 민감정보, 외부 전송, 비용 발생 작업을 임의로 빼앗거나 수행하지 않는다. 위험도와 승인 여부는 분리하여 평가한다.

---

## 3. 전략적 도메인 구조

### 3.1 Core Domain

아이리스의 경쟁력과 정체성을 만드는 핵심 도메인이다.

1. **Task Orchestration**
2. **Capability Routing**
3. **Safety-aware Execution**
4. **Contextual Monitoring**

### 3.2 Supporting Domains

1. Interaction
2. Workspace & Artifact
3. Computer Control
4. Development
5. Automation
6. Monitoring
7. Safety & Authorization
8. Context & Memory
9. Evolution
10. Integration

### 3.3 Infrastructure

다음은 도메인이 아니라 교체 가능한 구현 요소다.

- Eclipse Theia
- Electron
- Database
- File Storage
- Git executable/library
- Language Server
- OCR/VLM model
- GPT/Claude/local model
- Windows UI Automation
- Browser driver
- Hancom Automation
- Document parser
- External Agent
- Update server

---

## 4. Context Map

```text
Interaction
     │ creates
     ▼
Task Orchestration ──────────────┐
     │ requests                  │ reads
     ▼                           ▼
Capability & Tool          Context & Memory
     │ selects                  ▲
     ▼                          │ records
Safety & Authorization          │
     │ allows / blocks          │
     ▼                          │
Execution Lifecycle ────────────┘
     │
     ├─ Computer Control
     ├─ Development
     ├─ Automation
     ├─ Workspace & Artifact
     └─ Integration

Monitoring
     ├─ observes Task
     ├─ observes Tool/Process/App
     ├─ raises Incident
     └─ resumes/replans through Task Orchestration

Evolution
     ├─ uses Development
     ├─ creates ReleaseCandidate
     ├─ requires Safety approval
     └─ deploys through immutable Updater
```

---

# 5. Interaction Context

사용자와 아이리스 간 입력·응답·알림을 담당한다.

## 5.1 UserUtterance

텍스트 또는 음성으로 입력된 원본 사용자 요청이다.

```yaml
UserUtterance:
  id: string
  source: text | voice | shortcut | notification_action
  raw_text: string
  normalized_text: string
  language: string
  conversation_id: string
  created_at: datetime
```

## 5.2 IntentFrame

문장 하나를 단순 분류하는 `CommandIntent`보다 풍부한 의미 구조다.

```yaml
IntentFrame:
  id: string
  utterance_id: string
  intent_type: chat | execute | monitor | automate | create | modify | inspect | approve | cancel
  goal_text: string
  targets: TargetRef[]
  constraints: Constraint[]
  requested_output: OutputExpectation
  confidence: number
  ambiguity: string[]
```

## 5.3 AssistantMessage

```yaml
AssistantMessage:
  id: string
  conversation_id: string
  related_task_id: string?
  message_type: chat | progress | confirmation | approval_request | alert | result | error
  text: string
  should_speak: boolean
  created_at: datetime
```

## 5.4 Notification

```yaml
Notification:
  id: string
  severity: info | warning | error | critical
  category: task | monitoring | approval | system | update
  related_entity_ref: EntityRef?
  title: string
  body: string
  action_options: NotificationAction[]
  deduplication_key: string?
  created_at: datetime
  acknowledged_at: datetime?
```

---

# 6. Task Orchestration Context

아이리스의 최상위 핵심 도메인이다.

## 6.1 Task

사용자가 달성하려는 하나의 추적 가능한 목표다.

```yaml
Task:
  id: string
  task_type: chat | computer_use | code | document | automation | monitoring | evolution | composite
  title: string
  goal: Goal
  constraints: Constraint[]
  acceptance_criteria: AcceptanceCriterion[]
  priority: low | normal | high | urgent
  status: TaskStatus
  parent_task_id: string?
  child_task_ids: string[]
  workspace_id: string?
  active_plan_id: string?
  created_by: user | iris | automation
  created_at: datetime
  started_at: datetime?
  ended_at: datetime?
```

### TaskStatus

```text
draft
queued
planning
running
waiting_approval
waiting_user
waiting_resource
suspended
interrupted
cancelling
compensating
partially_completed
completed
failed
timed_out
cancelled
```

## 6.2 Goal

```yaml
Goal:
  statement: string
  desired_state: StateDescriptor?
  forbidden_outcomes: string[]
```

## 6.3 Constraint

```yaml
Constraint:
  type: time | scope | safety | cost | privacy | application | file | quality | user_preference
  description: string
  hard: boolean
```

## 6.4 AcceptanceCriterion

작업 완료를 판단할 수 있는 검증 가능한 조건이다.

```yaml
AcceptanceCriterion:
  id: string
  description: string
  verifier_type: deterministic | structured | visual | user_confirmation
  required: boolean
```

## 6.5 Plan

```yaml
Plan:
  id: string
  task_id: string
  version: integer
  steps: PlanStep[]
  rationale_summary: string
  revision_reason: string?
  created_at: datetime
```

## 6.6 PlanStep

```yaml
PlanStep:
  id: string
  plan_id: string
  index: integer
  title: string
  capability_required: string
  target_ref: EntityRef?
  expected_result: StateDescriptor
  dependencies: string[]
  retry_policy: RetryPolicy
  compensation_policy: CompensationPolicy?
  status: StepStatus
```

### StepStatus

```text
pending
ready
running
waiting_approval
waiting_resource
succeeded
partially_succeeded
failed
skipped
cancelled
compensated
```

## 6.7 TaskCheckpoint

중단·재시작·복구를 위한 저장 지점이다.

```yaml
TaskCheckpoint:
  id: string
  task_id: string
  plan_version: integer
  completed_step_ids: string[]
  active_step_id: string?
  relevant_state_refs: EntityRef[]
  resumable: boolean
  created_at: datetime
```

## 6.8 TaskResult

```yaml
TaskResult:
  task_id: string
  status: completed | partially_completed | failed | cancelled
  summary: string
  output_artifact_refs: EntityRef[]
  verification_summary: string
  unresolved_issues: string[]
  completed_at: datetime
```

---

# 7. Capability & Tool Context

## 7.1 CapabilityDefinition

아이리스가 할 수 있는 추상 기능이다.

```yaml
CapabilityDefinition:
  id: string
  name: string
  category: code | document | computer | browser | system | communication | media | monitoring
  description: string
  input_schema: object
  output_schema: object
  supported_target_types: string[]
  default_risk_profile: string
  required_permissions: string[]
```

예시:

```text
code.read
code.search
code.modify
code.build
code.test
document.read
document.modify
spreadsheet.calculate
presentation.modify
pdf.render
computer.launch_app
computer.focus_window
browser.navigate
communication.send
system.run_process
```

## 7.2 ToolProvider

```yaml
ToolProvider:
  id: string
  type: native | theia | os | app_api | external_agent | model_provider
  display_name: string
  health_status: available | degraded | unavailable
  supported_capabilities: string[]
  priority: integer
  trust_level: trusted | constrained | external
```

## 7.3 ToolBinding

```yaml
ToolBinding:
  id: string
  capability_id: string
  provider_id: string
  tool_name: string
  execution_tier: 1 | 2 | 3 | 4
  conditions: BindingCondition[]
```

### Execution Tier

```text
Tier 1: 전용 API, 파일 조작, 앱 공식 도구
Tier 2: LSP, DOM, UIA 등 구조화 자동화
Tier 3: OCR/VLM, 단축키, 좌표 기반 GUI
Tier 4: 외부 자율 에이전트 위임
```

## 7.4 CapabilityRoute

```yaml
CapabilityRoute:
  capability_id: string
  selected_binding_id: string
  selection_reason: string
  alternatives: string[]
  fallback_order: string[]
```

---

# 8. 공통 실행 수명주기

기존의 `ActionRequest`와 `ActionStep` 중복을 없애고 다음 모델로 통일한다.

```text
ActionProposal
→ PolicyDecision
→ ApprovalRequest / CapabilityGrant
→ ResourceLease
→ ActionAttempt
→ ActionResult
→ VerificationResult
```

## 8.1 ActionProposal

```yaml
ActionProposal:
  id: string
  task_id: string
  plan_step_id: string
  capability_id: string
  tool_binding_id: string
  target_ref: EntityRef?
  arguments: object
  expected_effect: StateDescriptor
  estimated_risk: RiskAssessment
  created_at: datetime
```

## 8.2 ActionAttempt

정책을 통과한 후 실제로 수행된 한 번의 실행이다.

```yaml
ActionAttempt:
  id: string
  proposal_id: string
  attempt_number: integer
  idempotency_key: string?
  started_at: datetime
  ended_at: datetime?
  status: running | succeeded | failed | blocked | timed_out | cancelled
```

## 8.3 ActionResult

```yaml
ActionResult:
  attempt_id: string
  tool_success: boolean
  exit_code: integer?
  output_summary: string
  error_summary: string?
  produced_entity_refs: EntityRef[]
  observed_side_effects: string[]
```

## 8.4 VerificationResult

```yaml
VerificationResult:
  id: string
  attempt_id: string
  verifier_type: process | filesystem | lsp | dom | uia | structured | visual | user
  expected_state: StateDescriptor
  actual_state: StateDescriptor
  evidence_refs: EvidenceRef[]
  status: success | partial | failed | unknown
  confidence: number
  retryable: boolean
  compensation_required: boolean
  failure_reason: string?
  suggested_next: continue | retry | replan | compensate | ask_user | delegate
  verified_at: datetime
```

---

# 9. Workspace & Artifact Context

코드와 일반 문서를 공통 모델로 관리한다.

## 9.1 Workspace

```yaml
Workspace:
  id: string
  type: general | development | document | automation | evolution
  title: string
  root_path: string?
  active_task_ids: string[]
  artifact_ids: string[]
  editor_session_ids: string[]
  snapshot_ids: string[]
  created_at: datetime
```

## 9.2 Artifact

```yaml
Artifact:
  id: string
  workspace_id: string
  type: code | document | spreadsheet | presentation | pdf | image | audio | archive | config
  format: string
  path: string?
  display_name: string
  current_revision_id: string?
  sensitivity: public | internal | personal | confidential | secret
  metadata: object
```

## 9.3 ArtifactRevision

```yaml
ArtifactRevision:
  id: string
  artifact_id: string
  base_revision_id: string?
  change_set_id: string?
  checksum: string
  created_by: user | iris | external_tool
  created_at: datetime
```

## 9.4 ChangeSet

코드뿐 아니라 문서 수정에도 사용할 수 있는 공통 변경 단위다.

```yaml
ChangeSet:
  id: string
  workspace_id: string
  task_id: string
  target_artifact_ids: string[]
  changes: ChangeOperation[]
  summary: string
  status: proposed | applied | validated | approved | rejected | reverted
  created_at: datetime
```

## 9.5 EditorSession

```yaml
EditorSession:
  id: string
  artifact_id: string
  editor_type: theia | document_editor | spreadsheet_editor | presentation_editor | pdf_viewer | image_editor
  owner: user | iris | shared
  state: open | active | suspended | closed
  opened_at: datetime
```

---

# 10. Computer Control Context

컴퓨터 화면과 애플리케이션을 직접 제어하는 PAV 도메인이다.

## 10.1 PerceptionObservation

```yaml
PerceptionObservation:
  id: string
  task_id: string
  active_process_name: string?
  active_window_ref: WindowRef?
  open_windows: WindowSummary[]
  uia_summary: object?
  dom_summary: object?
  ocr_summary: string?
  vlm_scene_summary: string?
  source: api | dom | uia | ocr | vlm | hybrid
  evidence_refs: EvidenceRef[]
  captured_at: datetime
```

## 10.2 ComputerUseSession

기존 `AgentLoop`는 Computer Use에만 한정된 하위 세션으로 재정의한다.

```yaml
ComputerUseSession:
  id: string
  task_id: string
  status: running | waiting_approval | waiting_user | suspended | completed | failed
  max_actions: integer
  current_action_count: integer
  observation_ids: string[]
  action_attempt_ids: string[]
  verification_ids: string[]
  started_at: datetime
  ended_at: datetime?
```

## 10.3 TargetLocator

창 제목 하나에 의존하지 않고 안정적으로 대상을 식별한다.

```yaml
TargetLocator:
  process_name: string?
  executable_path: string?
  window_class: string?
  automation_id: string?
  browser_profile_id: string?
  browser_tab_id: string?
  terminal_session_id: string?
  url_pattern: string?
  fallback_visual_signature: string?
```

## 10.4 ResourceLease

사용자와 아이리스의 입력 충돌을 방지한다.

```yaml
ResourceLease:
  id: string
  resource_type: foreground_focus | keyboard | pointer | clipboard | terminal | file | repository
  resource_ref: EntityRef?
  owner_task_id: string
  access_mode: shared | exclusive
  acquired_at: datetime
  expires_at: datetime
  heartbeat_at: datetime
  release_reason: completed | user_override | expired | error | cancelled
```

### 규칙

- 사용자 실제 입력이 감지되면 GUI 자동화를 일시 정지한다.
- API·LSP·DOM·UIA를 포커스 기반 입력보다 우선한다.
- 키보드·포인터는 짧은 시간 동안만 독점 임대한다.
- 파일·Git 저장소 변경은 작업공간 단위 잠금을 사용할 수 있다.

---

# 11. Development Context

코딩은 Computer Use가 아니라 별도 도메인으로 관리한다.

## 11.1 DevelopmentProject

```yaml
DevelopmentProject:
  id: string
  workspace_id: string
  repository_path: string
  project_type: string
  languages: string[]
  default_branch: string
  build_commands: string[]
  test_commands: string[]
  runtime_profile_id: string?
```

## 11.2 CodeTask

```yaml
CodeTask:
  id: string
  task_id: string
  project_id: string
  base_commit: string?
  requested_change: string
  acceptance_criteria: string[]
  status: analyzing | planning | modifying | validating | review_ready | completed | failed
```

## 11.3 DevelopmentWorkspace

사용자 작업공간과 아이리스 작업공간을 분리한다.

```yaml
DevelopmentWorkspace:
  id: string
  code_task_id: string
  branch_name: string
  worktree_path: string
  base_commit: string
  runtime_profile_id: string
  language_server_ids: string[]
  active_process_ids: string[]
  status: preparing | ready | active | validating | archived
```

## 11.4 CodeChangeSet

```yaml
CodeChangeSet:
  id: string
  development_workspace_id: string
  changed_files: string[]
  patches: Patch[]
  generated_files: string[]
  deleted_files: string[]
  summary: string
  base_commit: string
  resulting_commit: string?
```

## 11.5 ValidationRun

```yaml
ValidationRun:
  id: string
  code_change_set_id: string
  lint_result: CheckResult?
  typecheck_result: CheckResult?
  build_result: CheckResult?
  unit_test_result: CheckResult?
  integration_test_result: CheckResult?
  runtime_result: CheckResult?
  preview_evidence_refs: EvidenceRef[]
  status: passed | failed | partially_passed
  executed_at: datetime
```

## 11.6 Coding Tool Capabilities

```text
project.list_files
project.read_file
project.search_text
code.find_symbol
code.find_references
code.get_definition
code.get_diagnostics
code.apply_patch
code.create_file
code.rename_symbol
code.format
code.run_lint
code.run_typecheck
code.run_build
code.run_tests
git.create_worktree
git.diff
git.commit
git.revert
preview.start
preview.capture
```

## 11.7 Theia의 역할

Eclipse Theia는 `Development Context` 자체가 아니라 **Workspace UI 및 Tool Provider**다.

### Theia가 담당

- 코드 편집 화면
- 파일 탐색기
- 터미널 화면
- Git Diff
- LSP 진단 표시
- 테스트 결과 표시
- Iris Chat/Task/Approval/Monitoring 패널
- 커스텀 Artifact Editor 호스팅

### Iris Core가 담당

- 요구사항 해석
- Task와 Plan 생성
- Tool 선택
- 위험 평가
- 승인
- 코드 변경 계획
- 검증과 복구
- 자기 개선 정책

Theia를 다른 IDE로 교체해도 Iris Core가 동작해야 한다.

---

# 12. Automation Context

자동화는 모드 프리셋과 구분한다.

## 12.1 WorkflowDefinition

```yaml
WorkflowDefinition:
  id: string
  title: string
  trigger: TriggerDefinition
  conditions: ConditionDefinition[]
  steps: WorkflowStep[]
  concurrency_policy: allow | queue | skip | replace
  retry_policy: RetryPolicy
  enabled: boolean
```

## 12.2 WorkflowRun

```yaml
WorkflowRun:
  id: string
  workflow_id: string
  task_id: string
  trigger_event_ref: EntityRef
  status: queued | running | waiting_approval | completed | failed | cancelled
  started_at: datetime
  ended_at: datetime?
```

## 12.3 PresetMode

PresetMode는 도메인이 아니라 Workflow Template의 한 종류다.

```yaml
PresetMode:
  id: string
  mode_type: work | game | creative | custom
  title: string
  workflow_definition_id: string
  desired_layout: object
  restore_previous_state: boolean
```

프리셋 전체를 일괄 허용하지 않고, 확장된 각 ActionProposal을 개별 정책 평가한다.

---

# 13. Monitoring Context

## 13.1 MonitorDefinition

```yaml
MonitorDefinition:
  id: string
  target: MonitoredTarget
  detector_ids: string[]
  interval_policy: event_driven | adaptive | polling
  alert_rules: AlertRule[]
  enabled: boolean
```

## 13.2 MonitoredTarget

```yaml
MonitoredTarget:
  id: string
  type: task | process | window | browser_tab | terminal | file | system_log | external_service
  locator: TargetLocator?
  related_task_id: string?
  status: active | unavailable | completed | disabled
  last_checked_at: datetime?
```

## 13.3 MonitoringEvent

```yaml
MonitoringEvent:
  id: string
  target_id: string
  category: normal | approval_waiting | error_detected | generation_failed | task_stalled | response_ready | build_not_started | user_action_required | unknown
  severity: info | warning | error | critical
  confidence: number
  evidence_refs: EvidenceRef[]
  detector_id: string
  detector_version: string
  deduplication_key: string?
  occurrence_count: integer
  first_detected_at: datetime
  last_detected_at: datetime
```

## 13.4 Incident

```yaml
Incident:
  id: string
  related_task_id: string?
  source_event_ids: string[]
  category: stalled | repeated_failure | resource_conflict | unsafe_state | external_dependency
  status: open | acknowledged | mitigating | resolved | ignored
  recommended_actions: string[]
  resolved_at: datetime?
```

### TASK_STALLED 판단에 필요한 정보

- 현재 PlanStep
- 최근 heartbeat
- 정상 예상 시간
- 프로세스 CPU/출력 변화
- 동일 화면 반복 여부
- 사용자 입력 대기 여부

---

# 14. Safety & Authorization Context

## 14.1 RiskAssessment

```yaml
RiskAssessment:
  level: R0 | R1 | R2 | R3 | R4
  dimensions:
    reversibility: low | medium | high
    external_effect: none | limited | significant
    data_sensitivity: none | personal | confidential | secret
    financial_effect: none | possible | direct
    privilege_change: none | local | elevated
  rationale: string
```

### 위험 등급

| 등급 | 의미 | 예시 |
|---|---|---|
| R0 | 관찰만 수행 | 화면 읽기, 파일 목록 조회 |
| R1 | 쉽게 복구 가능한 로컬 조작 | 창 이동, 앱 실행 |
| R2 | 제한적인 상태 변경 | 파일 생성, 일반 코드 수정 |
| R3 | 민감 또는 외부 효과 | 메시지 전송, 코드 실행, 설정 변경 |
| R4 | 중대한 외부 효과 | 결제, 개인정보 제출, 영구 삭제, 관리자 권한 |

위험도와 승인 여부는 동일하지 않다.

## 14.2 PolicyDecision

```yaml
PolicyDecision:
  id: string
  proposal_id: string
  decision: allow | require_approval | require_isolation | deny
  matched_policy_ids: string[]
  reason: string
  valid_until: datetime?
  decided_at: datetime
```

## 14.3 ApprovalRequest

```yaml
ApprovalRequest:
  id: string
  proposal_id: string
  summary: string
  tool_name: string
  arguments_hash: string
  target_summary: string
  expected_effect: string
  risk_assessment: RiskAssessment
  scope: once | task | time_limited
  expires_at: datetime
  status: pending | approved | denied | expired | revoked
```

## 14.4 CapabilityGrant

```yaml
CapabilityGrant:
  id: string
  capability_id: string
  scope_constraints: object
  max_uses: integer?
  valid_from: datetime
  valid_until: datetime
  granted_by: user | policy
  revoked_at: datetime?
```

## 14.5 SecretReference

비밀번호와 토큰은 일반 문자열로 모델에 전달하지 않는다.

```yaml
SecretReference:
  id: string
  provider: credential_manager | secure_vault | user_input
  purpose: string
  accessible_to_model: false
```

## 14.6 Immutable Safety Kernel

다음 영역은 아이리스 자기 수정 대상에서 제외한다.

- Policy Engine
- Approval Validator
- Secret Broker
- Audit Logger
- Updater
- Signature Validator
- Rollback Manager
- 권한 상한 설정

---

# 15. Context & Memory Context

## 15.1 WorkingContext

현재 Task에 필요한 단기 문맥이다.

```yaml
WorkingContext:
  id: string
  task_id: string
  facts: ContextFact[]
  active_entity_refs: EntityRef[]
  expires_at: datetime?
```

## 15.2 MemoryItem

```yaml
MemoryItem:
  id: string
  category: preference | project | application | workflow | correction | relationship
  content: string
  source_ref: EntityRef?
  confidence: number
  retention_policy_id: string
  consent_required: boolean
  created_at: datetime
  last_used_at: datetime?
```

## 15.3 RetentionPolicy

```yaml
RetentionPolicy:
  id: string
  duration: session | short | long | permanent
  sensitive: boolean
  user_deletable: boolean
  auto_expire_days: integer?
```

### 규칙

- 작업에 필요한 문맥과 장기 기억을 분리한다.
- 원본 스크린샷과 전체 OCR은 기본 영구 저장하지 않는다.
- 필요 시 짧은 TTL과 암호화를 적용한다.
- 민감정보는 요약·마스킹·해시 기반 증거를 우선한다.

---

# 16. Evolution Context

아이리스가 자신을 개선하거나 기능을 추가하는 도메인이다.

## 16.1 SelfModificationRequest

```yaml
SelfModificationRequest:
  id: string
  task_id: string
  requested_feature: string
  target_scope: prompt | ui | plugin | module | core
  affected_components: string[]
  required_permissions: string[]
  risk_level: R1 | R2 | R3 | R4
  approval_required: boolean
```

## 16.2 EvolutionPlan

```yaml
EvolutionPlan:
  id: string
  request_id: string
  implementation_steps: string[]
  validation_suite_ids: string[]
  migration_plan: string?
  rollback_plan: string
```

## 16.3 IrisPlugin

기능 추가는 가능한 한 코어가 아니라 플러그인으로 구현한다.

```yaml
IrisPlugin:
  id: string
  version: string
  entry_point: string
  capabilities: string[]
  permissions: string[]
  dependencies: string[]
  test_manifest: string
  status: candidate | installed | disabled | removed
```

## 16.4 ReleaseCandidate

```yaml
ReleaseCandidate:
  id: string
  version: string
  source_commit: string
  candidate_workspace_id: string
  affected_components: string[]
  validation_run_ids: string[]
  migration_plan: string?
  rollback_point_id: string
  status: building | testing | review_ready | approved | rejected | deployed | rolled_back
```

## 16.5 DeploymentDecision

```yaml
DeploymentDecision:
  id: string
  release_candidate_id: string
  decision: approve | reject
  approved_by: user
  approved_at: datetime
  approval_scope: exact_candidate
```

## 16.6 RollbackPoint

```yaml
RollbackPoint:
  id: string
  application_version: string
  source_commit: string
  configuration_snapshot_ref: EntityRef
  database_snapshot_ref: EntityRef?
  created_at: datetime
```

### 자기 개선 규칙

| 변경 대상 | 자동 적용 |
|---|---|
| 프롬프트·UI 개인 설정 | 가능, 즉시 롤백 지원 |
| 플러그인 | 검증 후 제한적 가능 |
| 일반 기능 모듈 | 사용자 승인 필수 |
| Task Orchestrator | 강한 회귀 테스트와 승인 |
| Safety Kernel | 자동 수정 금지 |
| Updater·Rollback | 자동 수정 금지 |

---

# 17. Integration Context

외부 앱·모델·에이전트와의 연결을 담당한다.

## 17.1 IntegrationAdapter

```yaml
IntegrationAdapter:
  id: string
  adapter_type: app | model | browser | os | document | external_agent | cloud
  provider_name: string
  supported_capabilities: string[]
  permission_requirements: string[]
  health_status: available | degraded | unavailable
```

## 17.2 ExternalAgentDelegation

```yaml
ExternalAgentDelegation:
  id: string
  task_id: string
  delegated_plan_step_ids: string[]
  agent_type: cursor | claude_code | openclaw | hermes | custom
  reason: specialized | long_tail | user_requested | repeated_failure
  capability_scope: string[]
  permission_scope: string[]
  result_summary: string?
  verification_required: true
  delegated_at: datetime
```

### 규칙

- 외부 에이전트는 아이리스의 몸체가 아니다.
- 아이리스가 목표·권한·대상 범위를 지정한다.
- 외부 에이전트 결과도 Iris Verification을 통과해야 한다.
- 외부 에이전트는 Safety Kernel을 우회할 수 없다.

---

# 18. Domain Events

주요 상태 변화는 도메인 이벤트로 발행한다.

```text
UserUtteranceReceived
IntentFrameCreated
TaskCreated
TaskPlanningStarted
PlanCreated
PlanRevised
PlanStepReady
ActionProposed
PolicyDecisionMade
ApprovalRequested
ApprovalGranted
ApprovalDenied
ResourceLeaseAcquired
ActionAttemptStarted
ActionAttemptCompleted
VerificationCompleted
PlanStepSucceeded
PlanStepFailed
TaskCheckpointCreated
TaskCompleted
TaskFailed
MonitoringEventDetected
IncidentOpened
CodeChangeSetCreated
ValidationRunCompleted
ReleaseCandidateCreated
DeploymentApproved
ReleaseDeployed
RollbackTriggered
```

이벤트는 Monitoring, Audit, UI Progress, Retry, Recovery에서 공통으로 사용한다.

---

# 19. Evidence & Audit

## 19.1 EvidenceRef

```yaml
EvidenceRef:
  id: string
  type: screenshot_region | process_output | file_hash | diff | dom_snapshot | uia_snapshot | test_report | user_confirmation
  storage_ref: string?
  summary: string
  sensitive: boolean
  expires_at: datetime?
```

## 19.2 AuditEvent

```yaml
AuditEvent:
  id: string
  actor: user | iris | policy | external_agent
  action: string
  target_ref: EntityRef?
  related_task_id: string?
  risk_level: string?
  policy_decision_id: string?
  timestamp: datetime
```

---

# 20. Repository Interfaces

도메인 모델은 특정 데이터베이스에 의존하지 않는다.

```text
TaskRepository
PlanRepository
WorkspaceRepository
ArtifactRepository
CapabilityRepository
PolicyRepository
MonitoringRepository
MemoryRepository
DevelopmentRepository
EvolutionRepository
AuditRepository
```

각 Repository 구현은 SQLite, PostgreSQL, 파일 기반 저장소 등으로 교체 가능해야 한다.

---

# 21. 권장 애플리케이션 서비스

```text
TaskApplicationService
PlanningService
CapabilityRouter
ExecutionCoordinator
VerificationService
WorkspaceService
ComputerUseService
DevelopmentService
AutomationService
MonitoringService
SafetyService
ApprovalService
MemoryService
EvolutionService
IntegrationService
```

애플리케이션 서비스는 도메인 객체와 인프라 어댑터를 연결하되, 정책의 핵심 판단은 도메인 계층에 둔다.

---

# 22. 권장 패키지 구조

```text
src/
├─ domain/
│  ├─ interaction/
│  ├─ task/
│  ├─ capability/
│  ├─ execution/
│  ├─ workspace/
│  ├─ computer-control/
│  ├─ development/
│  ├─ automation/
│  ├─ monitoring/
│  ├─ safety/
│  ├─ memory/
│  ├─ evolution/
│  └─ integration/
│
├─ application/
│  ├─ services/
│  ├─ commands/
│  ├─ queries/
│  └─ event-handlers/
│
├─ infrastructure/
│  ├─ persistence/
│  ├─ theia/
│  ├─ os/
│  ├─ browser/
│  ├─ document/
│  ├─ model-providers/
│  ├─ external-agents/
│  └─ updater/
│
└─ interfaces/
   ├─ desktop/
   ├─ api/
   ├─ voice/
   └─ cli/
```

---

# 23. Eclipse Theia 통합 경계

```text
Iris Desktop
├─ Theia Frontend
│  ├─ Code Editor
│  ├─ File Explorer
│  ├─ Terminal
│  ├─ Git Diff
│  ├─ Iris Chat Panel
│  ├─ Task Panel
│  ├─ Approval Panel
│  ├─ Monitoring Panel
│  └─ Artifact Editors
│
├─ Theia Backend
│  ├─ Workspace/File Service
│  ├─ Terminal Service
│  ├─ Language Server Manager
│  └─ Git Provider
│
└─ Iris Core
   ├─ Task Orchestrator
   ├─ Capability Router
   ├─ Safety Engine
   ├─ Development Agent
   ├─ Monitoring Engine
   ├─ Context Manager
   └─ Evolution Manager
```

통신은 Local IPC 또는 JSON-RPC를 사용한다.

### 원칙

- Theia UI가 종료되어도 Iris Core의 Task 상태는 보존되어야 한다.
- Theia Extension은 Iris Core의 명령을 UI에 표시하고 사용자 입력을 전달한다.
- Theia가 Safety Decision을 직접 내리지 않는다.
- Theia Extension은 `CapabilityProvider` 역할을 할 수 있지만 Orchestrator 역할을 갖지 않는다.

---

# 24. 대표 실행 시나리오

## 24.1 코드 기능 추가

```text
“아이리스 로그인 기능을 추가하고 테스트해줘”
→ Task(code)
→ AcceptanceCriteria 작성
→ DevelopmentWorkspace/Git Worktree 생성
→ 코드베이스 분석
→ Plan 생성
→ CodeChangeSet 생성
→ Build/Test
→ ValidationRun
→ Theia에서 Diff 표시
→ 사용자 승인
→ 병합
→ TaskResult
```

## 24.2 DOCX 문서 수정

```text
“이 기획서의 개발계획 표가 잘리지 않게 수정해줘”
→ Task(document)
→ Artifact(docx) 등록
→ document.modify Capability 선택
→ 구조 분석
→ ChangeSet 생성
→ 렌더링 검증
→ 결과 파일 생성
→ TaskResult
```

## 24.3 터미널 승인 대기 감지

```text
Monitor detects “Proceed? (y/n)”
→ MonitoringEvent(APPROVAL_WAITING)
→ 관련 Task/Terminal 식별
→ 입력 예정 ActionProposal 생성
→ PolicyDecision
→ 필요 시 ApprovalRequest
→ ResourceLease(keyboard/focus)
→ 입력 실행
→ 터미널 상태 Verification
```

## 24.4 아이리스 플러그인 추가

```text
“PDF 분석 기능을 아이리스에 추가해줘”
→ Task(evolution)
→ SelfModificationRequest(plugin)
→ Candidate Workspace 생성
→ 플러그인 구현
→ 권한 검토
→ 테스트 및 회귀 검증
→ ReleaseCandidate
→ 사용자 승인
→ 설치
→ Health Check
→ 실패 시 Rollback
```

---

# 25. MVP 우선순위

## Phase 1 — Core Task Model

필수 구현:

- UserUtterance
- IntentFrame
- Task
- Plan
- PlanStep
- ActionProposal
- PolicyDecision
- ActionAttempt
- VerificationResult
- TaskResult

## Phase 2 — Computer Use & Monitoring

- PerceptionObservation
- ComputerUseSession
- TargetLocator
- ResourceLease
- MonitorDefinition
- MonitoringEvent
- Incident

## Phase 3 — Theia & Development

- Theia Desktop 통합
- DevelopmentProject
- DevelopmentWorkspace
- CodeTask
- CodeChangeSet
- ValidationRun
- Git Worktree
- LSP/Build/Test Tool Provider

## Phase 4 — Universal Artifact

- Artifact
- ArtifactRevision
- ChangeSet
- DOCX/PDF/XLSX/PPTX Adapter
- HWP/HWPX Adapter
- Renderer/Preview Verification

## Phase 5 — Evolution

- IrisPlugin
- SelfModificationRequest
- ReleaseCandidate
- DeploymentDecision
- RollbackPoint
- Immutable Safety Kernel

---

# 26. 초기 구현에서 제외할 항목

다음은 도메인에는 정의하되 초기 MVP 구현 범위에서는 제외할 수 있다.

- 완전 자동 코어 업데이트
- 무제한 외부 에이전트 위임
- 모든 언어 런타임 번들
- 결제·금융 작업 자동화
- 관리자 권한 자동 상승
- 민감정보 자동 입력
- 다중 사용자 협업
- 원격 분산 실행
- 완전한 VM 수준 샌드박스

---

# 27. 미결정 사항

구현 전 다음 항목은 ADR(Architecture Decision Record)로 별도 결정한다.

1. Iris Core 주 언어 및 프로세스 구조
2. Theia Backend와 Iris Core의 IPC 방식
3. 기본 저장소: SQLite 또는 다른 DB
4. Git CLI 사용 여부와 라이브러리 사용 여부
5. Windows 제한 프로세스 실행 방식
6. Artifact 변환·렌더링 엔진
7. 장기 기억 저장 정책
8. 모델 Provider 라우팅 기준
9. 자동 승인 가능한 작업의 기본 범위
10. ReleaseCandidate 서명 및 배포 방식

---

# 28. 최종 도메인 정의

아이리스는 IDE, 챗봇 또는 Computer Use 도구 중 하나로 정의되지 않는다.

> **아이리스는 사용자의 목표를 Task로 구조화하고, 현재 문맥과 정책에 따라 적절한 Capability를 선택하며, 코드·문서·애플리케이션·컴퓨터를 안전하게 조작하고, 결과를 검증·복구·기억하는 범용 작업 오케스트레이터다.**

Eclipse Theia는 아이리스가 코딩과 다양한 Artifact를 사용자에게 보여주고 함께 편집하기 위한 내장 Workspace Shell이다. 아이리스의 핵심 판단과 작업 상태는 Theia와 분리된 Iris Core에 존재한다.

이 경계를 유지하면 향후 IDE, AI 모델, 문서 편집기, 외부 에이전트가 바뀌어도 아이리스의 핵심 도메인을 유지할 수 있다.

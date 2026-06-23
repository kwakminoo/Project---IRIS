"""IDE 뒤로가기 네비게이션 — PyQt·Theia bridge·단축키 단일 진입점.

현재(1단계): PyQt `IdeActivityBackButton` + Theia 에러 패널의 복귀 버튼이
`back_requested`로 모여 `IdeWorkspacePage.theia_back`에 연결됨.

향후(2단계) Theia extension 이전 경로:
- `iris-bridge` extension에 Activity Bar 하단 `iris.navigateBack` 커맨드 추가
- bridge HTTP `/commands` 또는 `postMessage({type:'iris.ide.navigateBack'})` 수신
- `IdeBackNavigationController.connect_theia_bridge(client)` 에서 동일 signal 연결
- PyQt 오버레이 버튼은 feature flag로 숨긴 뒤 제거 가능

즉시 이전하지 않는 이유: Theia 빌드·배포 사이클이 PyQt 오버레이보다 무겁고,
이번 작업 목표는 마우스 이벤트 경계 정리이므로 안전한 PyQt 레이어 수정을 우선함.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from iris.ui.ide.embedded_theia_view import EmbeddedTheiaView
from iris.ui.ide.ide_activity_back_button import IdeActivityBackButton


class IdeBackNavigationController(QObject):
  """IDE → Iris Assistant 복귀 액션 단일 허브."""

  back_requested = pyqtSignal()

  def request_back(self) -> None:
    self.back_requested.emit()

  def connect_pyqt_button(self, button: IdeActivityBackButton) -> None:
    button.back_clicked.connect(self.request_back)

  def connect_theia_view(self, view: EmbeddedTheiaView) -> None:
    view.back_to_assistant_requested.connect(self.request_back)

  def connect_theia_bridge(self, callback) -> None:
    """향후 iris-bridge navigateBack 이벤트 — callback은 request_back 바인딩용."""
    callback.connect(self.request_back)

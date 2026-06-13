"""인메모리 도메인 이벤트 디스패처."""

from __future__ import annotations

from iris.domain.task.events import DomainEvent, DomainEventHandler


class InMemoryEventDispatcher:
    """간단한 이벤트 버스 — Handler 목록에 순차 전달."""

    def __init__(self) -> None:
        self._handlers: list[DomainEventHandler] = []

    def subscribe(self, handler: DomainEventHandler) -> None:
        self._handlers.append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers:
            handler.on_event(event)

    def clear(self) -> None:
        self._handlers.clear()

"""도메인 결과 타입."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class DomainError:
    """도메인 규칙 위반."""

    code: str
    message: str


@dataclass(frozen=True)
class Result(Generic[T]):
    """성공 또는 도메인 오류."""

    value: T | None = None
    error: DomainError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def failure(cls, code: str, message: str) -> "Result[T]":
        return cls(error=DomainError(code=code, message=message))

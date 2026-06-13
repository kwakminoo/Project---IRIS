"""도메인 공통 유틸."""

from iris.domain.shared.id_generator import new_id
from iris.domain.shared.time import utc_now_iso

__all__ = ["new_id", "utc_now_iso"]

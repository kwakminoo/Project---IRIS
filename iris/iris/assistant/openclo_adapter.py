"""호환용 별칭 — OpenClawActionBackend."""

from __future__ import annotations

from iris.assistant.openclaw_adapter import OpenClawActionBackend as OpenCloAdapter
from iris.assistant.openclaw_adapter import OpenClawResult

__all__ = ["OpenCloAdapter", "OpenClawResult"]

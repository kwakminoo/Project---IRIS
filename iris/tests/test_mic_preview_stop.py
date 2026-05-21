"""MicLevelPreview — stop() 후 emit 차단."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iris.audio.mic_preview import MicLevelPreview


def test_stop_clears_emit_ok_before_active() -> None:
    preview = MicLevelPreview(16000)
    preview._emit_ok.set()
    preview._active.set()
    preview.stop()
    assert not preview._emit_ok.is_set()
    assert not preview._active.is_set()


def test_safe_emit_level_blocked_after_stop() -> None:
    preview = MicLevelPreview(16000)
    preview._generation = 1
    preview._emit_ok.set()
    preview._active.set()
    slot = MagicMock()
    preview.level.connect(slot)
    preview.stop()
    preview._safe_emit_level(1, 0.5)
    slot.assert_not_called()


def test_safe_emit_level_ignores_stale_generation() -> None:
    preview = MicLevelPreview(16000)
    preview._generation = 2
    preview._emit_ok.set()
    preview._active.set()
    slot = MagicMock()
    preview.level.connect(slot)
    preview._safe_emit_level(1, 0.5)
    slot.assert_not_called()

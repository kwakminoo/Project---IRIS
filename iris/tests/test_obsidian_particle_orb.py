"""Obsidian 지식 구체 — 노트 → 파티클 매핑 스모크 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.ui.knowledge.obsidian_particle_orb import (
    ObsidianOrbNode,
    ObsidianParticleOrb,
    display_title_for_source,
    is_obsidian_note_path,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_is_obsidian_note_path_filters_code() -> None:
    assert is_obsidian_note_path(r"C:\docs\AGENTS.md")
    assert is_obsidian_note_path(r"C:\rules\iris.mdc")
    assert not is_obsidian_note_path(r"C:\iris\main_window.py")
    assert not is_obsidian_note_path(r"C:\config\settings.json")


def test_display_title_falls_back_to_filename() -> None:
    assert display_title_for_source(title="AGENTS", path="x/AGENTS.md") == "AGENTS"
    assert display_title_for_source(title="", path="docs/architecture.md") == "architecture.md"


def test_orb_rebuilds_particle_count_from_notes(qapp) -> None:
    orb = ObsidianParticleOrb()
    notes = [
        ObsidianOrbNode(source_id=1, title="A", path="a.md"),
        ObsidianOrbNode(source_id=2, title="B", path="b.md"),
        ObsidianOrbNode(source_id=3, title="C", path="c.md"),
    ]
    orb.set_notes(notes)
    assert orb.note_count() == 3
    assert len(orb._pts) == 3  # noqa: SLF001
    orb.set_notes([])
    assert orb.note_count() == 0
    assert len(orb._pts) == 12  # empty placeholder sphere


def test_orb_view_mode_switches_to_flat_disk(qapp) -> None:
    from iris.ui.knowledge.obsidian_particle_orb import _flat_disk

    orb = ObsidianParticleOrb()
    notes = [
        ObsidianOrbNode(source_id=1, title="A", path="a.md"),
        ObsidianOrbNode(source_id=2, title="B", path="b.md"),
    ]
    orb.set_notes(notes)
    assert orb.view_mode() == "3d"
    orb.set_view_mode("2d")
    assert orb.view_mode() == "2d"
    assert len(orb._pts) == 2  # noqa: SLF001
    assert all(abs(pz) < 1e-9 for _, _, pz in orb._pts)  # noqa: SLF001
    flat = _flat_disk(2)
    assert len(flat) == 2
    orb.set_view_mode("3d")
    assert orb.view_mode() == "3d"

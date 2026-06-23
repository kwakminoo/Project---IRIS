"""사용자 프로필 저장 테스트."""

from __future__ import annotations

from pathlib import Path

from iris.storage.database import Database
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile


def test_user_profile_round_trip(tmp_path: Path) -> None:
    db = Database(tmp_path / "iris.db")
    profile = UserProfile(
        name="테스트",
        occupation="개발자",
        hobbies="코딩",
        interests="AI",
        work_tasks="자동화",
        age="30",
        gender="비공개",
        residence="서울",
        contact="010-0000-0000",
        email="test@example.com",
    )
    save_user_profile(db, profile)
    loaded = load_user_profile(db)
    assert loaded == profile


def test_user_profile_empty_default(tmp_path: Path) -> None:
    db = Database(tmp_path / "iris.db")
    assert load_user_profile(db) == UserProfile()

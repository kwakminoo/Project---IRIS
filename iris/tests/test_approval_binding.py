"""Approval arguments_hash 바인딩 테스트."""

from iris.application.approval_hash import hash_arguments


def test_arguments_hash_stable():
    h1 = hash_arguments({"command": "npm test", "cwd": "C:/proj"})
    h2 = hash_arguments({"cwd": "C:/proj", "command": "npm test"})
    assert h1 == h2


def test_arguments_hash_differs_for_different_commands():
    h1 = hash_arguments({"command": "npm test"})
    h2 = hash_arguments({"command": "npm run build"})
    assert h1 != h2

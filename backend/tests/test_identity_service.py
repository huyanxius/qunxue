from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from qunxue_api.modules.identity import (
    IdentityRepository,
    IdentityService,
    InvalidCredentials,
)


class MissingUserRepository:
    def get_user_by_email(self, _email: str) -> None:
        return None


class RecordingHasher:
    def __init__(self) -> None:
        self.verified_hashes: list[str] = []

    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password_hash: str, _password: str) -> bool:
        self.verified_hashes.append(password_hash)
        return False


def test_unknown_email_still_performs_the_password_verification_path() -> None:
    hasher = RecordingHasher()
    service = IdentityService(
        cast(IdentityRepository, MissingUserRepository()),
        hasher,
        invalid_password_hash="hash:dummy",
        session_ttl=timedelta(days=7),
        clock=lambda: datetime(2026, 8, 7, tzinfo=UTC),
    )

    with pytest.raises(InvalidCredentials):
        service.login(email="missing@example.com", password="wrong-password")

    assert hasher.verified_hashes == ["hash:dummy"]

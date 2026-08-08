from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from qunxue_api.modules.identity import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    """Argon2id 具体实现留在 adapter，业务模块只依赖密码哈希端口。"""

    def __init__(self) -> None:
        self._hasher = Argon2()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

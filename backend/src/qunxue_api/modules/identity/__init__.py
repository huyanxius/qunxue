"""用户身份、密码验证与服务端会话边界。"""

from qunxue_api.modules.identity.domain import (
    AuthenticatedSession,
    SessionGrant,
    User,
    UserSession,
)
from qunxue_api.modules.identity.errors import (
    EmailAlreadyRegistered,
    IdentityError,
    InvalidCredentials,
    InvalidEmail,
    Unauthenticated,
)
from qunxue_api.modules.identity.ports import IdentityRepository, PasswordHasher
from qunxue_api.modules.identity.service import IdentityService

__all__ = [
    "AuthenticatedSession",
    "EmailAlreadyRegistered",
    "IdentityError",
    "IdentityRepository",
    "IdentityService",
    "InvalidCredentials",
    "InvalidEmail",
    "PasswordHasher",
    "SessionGrant",
    "Unauthenticated",
    "User",
    "UserSession",
]

from typing import Self
from uuid import UUID


class AccountManagementError(Exception):
    code = "account_management_error"

    audit_action: str | None = None
    audit_actor_user_id: UUID | None = None
    audit_target_user_id: UUID | None = None
    audit_details: dict[str, object] | None = None

    def with_denied_audit(
        self,
        *,
        action: str,
        actor_user_id: UUID | None,
        target_user_id: UUID | None,
        details: dict[str, object],
    ) -> Self:
        self.audit_action = action
        self.audit_actor_user_id = actor_user_id
        self.audit_target_user_id = target_user_id
        self.audit_details = details
        return self


class AccountNotFound(AccountManagementError):
    code = "not_found"

    def __init__(self) -> None:
        super().__init__("账户不存在或无权访问。")


class AccountForbidden(AccountManagementError):
    code = "forbidden"

    def __init__(self) -> None:
        super().__init__("你没有执行此操作的权限。")


class AccountConflict(AccountManagementError):
    code = "conflict"


class StaleAccountVersion(AccountConflict):
    def __init__(self) -> None:
        super().__init__("账户已在其他位置更新，请刷新后重试。")


class IdempotencyConflict(AccountConflict):
    code = "idempotency_conflict"

    def __init__(self) -> None:
        super().__init__("该请求标识已用于另一项操作，请重新提交。")


class LastAdministratorProtected(AccountConflict):
    def __init__(self) -> None:
        super().__init__("必须至少保留一位可用的管理员。")


class ProvisionedAdministratorProtected(AccountConflict):
    code = "provisioned_administrator_protected"

    def __init__(self) -> None:
        super().__init__("部署管理员账户必须保持启用，不能降级、停用或删除。")


class AccountCapabilityUnavailable(AccountManagementError):
    code = "capability_unavailable"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidCurrentPassword(AccountManagementError):
    code = "reauthentication_required"

    def __init__(self) -> None:
        super().__init__("当前密码不正确，请重新验证身份。")


class InvalidPasswordReset(AccountManagementError):
    code = "password_reset_invalid"

    def __init__(self) -> None:
        super().__init__("密码重置链接无效或已使用。")


class ExpiredAccountToken(AccountManagementError):
    code = "token_expired"

    def __init__(self) -> None:
        super().__init__("链接已过期，请申请新的链接。")


class InvalidConfirmation(AccountManagementError):
    code = "validation_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)

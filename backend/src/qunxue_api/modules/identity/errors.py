class IdentityError(Exception):
    code = "identity_error"


class InvalidCredentials(IdentityError):
    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("邮箱或密码不正确。")


class Unauthenticated(IdentityError):
    code = "unauthenticated"

    def __init__(self) -> None:
        super().__init__("请先登录。")


class EmailAlreadyRegistered(IdentityError):
    code = "email_already_registered"

    def __init__(self) -> None:
        super().__init__("该邮箱无法用于注册。")


class InvalidEmail(IdentityError):
    code = "invalid_email"

    def __init__(self) -> None:
        super().__init__("请输入有效的邮箱地址。")


class InvalidVerificationCode(IdentityError):
    code = "invalid_verification_code"

    def __init__(self) -> None:
        super().__init__("验证码无效或已过期，请重新获取。")


class VerificationCodeRateLimited(IdentityError):
    code = "verification_code_rate_limited"

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("验证码发送过于频繁，请稍后再试。")


class EmailDeliveryUnavailable(IdentityError):
    code = "email_delivery_unavailable"

    def __init__(self) -> None:
        super().__init__("验证码暂时无法发送，请稍后再试。")

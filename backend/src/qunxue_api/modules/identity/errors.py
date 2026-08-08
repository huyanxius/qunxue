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

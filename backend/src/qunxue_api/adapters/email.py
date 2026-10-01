import logging
from html import escape

import resend

from qunxue_api.modules.identity import EmailDeliveryUnavailable

logger = logging.getLogger("qunxue.email")


class ResendEmailProvider:
    def __init__(self, *, api_key: str, from_email: str) -> None:
        self._api_key = api_key
        self._from_email = from_email

    def send_password_reset(self, email: str, reset_url: str) -> None:
        try:
            resend.api_key = self._api_key
            resend.Emails.send({
                "from": self._from_email,
                "to": [email],
                "subject": "【群学致知】重置登录密码",
                "text": (
                    "你申请了重置群学致知登录密码。\n"
                    f"请在 15 分钟内打开以下链接：\n{reset_url}\n"
                    "链接仅可使用一次，新密码生效后所有旧会话将退出。\n"
                    "如非本人操作，请忽略此邮件，你的密码不会改变。"
                ),
                "html": (
                    "<p>你申请了重置群学致知登录密码。</p>"
                    f'<p><a href="{escape(reset_url, quote=True)}">设置新密码</a></p>'
                    "<p>链接 15 分钟内有效，仅可使用一次。新密码生效后所有旧会话将退出。</p>"
                    "<p>如非本人操作，请忽略此邮件，你的密码不会改变。</p>"
                ),
            })
        except Exception:
            # Provider errors can contain recipient addresses and request bodies.
            raise EmailDeliveryUnavailable from None

    def send_verification_code(self, email: str, code: str) -> None:
        try:
            resend.api_key = self._api_key
            resend.Emails.send(
                {
                    "from": self._from_email,
                    "to": [email],
                    "subject": "【群学致知】注册验证码",
                    "html": (
                        "<p>你正在注册群学致知账号。</p>"
                        f"<p>验证码是 <strong>{code}</strong>，5 分钟内有效。</p>"
                        "<p>如非本人操作，请忽略此邮件。</p>"
                    ),
                }
            )
        except Exception as error:
            logger.exception("Registration verification email delivery failed")
            raise EmailDeliveryUnavailable from error

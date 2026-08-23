import logging

import resend

from qunxue_api.modules.identity import EmailDeliveryUnavailable

logger = logging.getLogger("qunxue.email")


class ResendEmailProvider:
    def __init__(self, *, api_key: str, from_email: str) -> None:
        self._api_key = api_key
        self._from_email = from_email

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

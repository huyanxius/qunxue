import pytest
from pydantic import ValidationError

from qunxue_api.api.contracts.account_management import (
    ChangePasswordRequest,
    PasswordResetConsumeRequest,
)


@pytest.mark.parametrize("model,extra", [
    (ChangePasswordRequest, {"current_password": "old-password"}),
    (PasswordResetConsumeRequest, {"token": "t" * 32}),
])
@pytest.mark.parametrize("length,accepted", [(7, False), (8, True), (128, True), (129, False)])
def test_new_password_length_boundaries(model, extra, length, accepted):
    payload = {**extra, "new_password": "p" * length}
    if accepted:
        assert model(**payload).new_password == payload["new_password"]
    else:
        with pytest.raises(ValidationError):
            model(**payload)

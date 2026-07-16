import pytest

from backend.services.content_safety.detectors import (
    detect_structures,
    redact_personal_data,
)
from backend.services.content_safety.models import RiskCategory


def test_private_key_and_bearer_tokens_are_critical_secrets():
    private_key = detect_structures("-----BEGIN PRIVATE KEY-----\nabc")
    bearer = detect_structures("Authorization: Bearer abc.def.ghi")

    assert private_key.has(RiskCategory.SECRET_OR_CREDENTIAL)
    assert bearer.has(RiskCategory.SECRET_OR_CREDENTIAL)
    assert private_key.blocking is True
    assert bearer.blocking is True


def test_common_api_key_shape_is_detected_without_echoing_secret():
    secret = "sk-live-abcdefghijklmnopqrstuvwxyz123456"
    result = detect_structures(f"我的密钥是 {secret}")

    assert result.has(RiskCategory.SECRET_OR_CREDENTIAL)
    assert secret not in result.model_dump_json()


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_11AA0abcdefghijklmnopqrstuvwxyz_0123456789ABCDEFGH",
        "xoxb-123456789012-123456789012-abcdefghijklmnopqrstuvwx",
        "AIzaSyA1234567890abcdefghijklmnopqrstuv",
        "sk_live_abcdefghijklmnopqrstuvwxyz123456",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123456",
        'api_key="abcdefghijklmnopqrstuvwxyz123456"',
    ],
)
def test_known_high_confidence_credentials_are_detected(secret):
    result = detect_structures(secret)

    assert result.has(RiskCategory.SECRET_OR_CREDENTIAL)
    assert result.blocking is True


def test_phone_email_and_identity_number_are_redacted():
    result = redact_personal_data(
        "联系 13800138000 或 user@example.com，身份证 11010519491231002X"
    )

    assert result.text == "联系 [手机号已隐藏] 或 [邮箱已隐藏]，身份证 [身份证号已隐藏]"
    assert result.changed is True
    assert set(result.reason_codes) == {
        "PERSONAL_PHONE_REDACTED",
        "PERSONAL_EMAIL_REDACTED",
        "PERSONAL_ID_REDACTED",
    }


def test_active_html_and_dangerous_url_are_structural_render_risks():
    result = detect_structures('<img src="x" onerror="alert(1)"><a href="javascript:x">x</a>')

    assert result.has(RiskCategory.ACTIVE_CONTENT_OR_UNSAFE_RENDERING)
    assert result.blocking is True


def test_educational_sql_phrase_is_not_a_structural_block():
    result = detect_structures("解释 DROP TABLE 的危害与防御")

    assert result.blocking is False
    assert not result.has(RiskCategory.CYBER_ABUSE)

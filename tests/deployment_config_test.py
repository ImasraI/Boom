from app.config import Settings
from app.utils.deployment_checks import configuration_issues


def production(**overrides):
    values = dict(APP_ENV='production', SECRET_KEY='a' * 64,
                  CORS_ORIGINS='https://boomedu.ir', SMS_API_KEY='private-key',
                  SMS_VERIFY_TEMPLATE_ID='123', SMS_VERIFY_PARAMETER_NAME='OTP',
                  LLM_API_KEY='private-chat-key', DISABLE_AUTH=False,
                  SMS_DEBUG_ECHO=False, SIGNUP_BYPASS_CODE='')
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_production_config_does_not_require_raw_books():
    errors, _ = configuration_issues(production(RAW_DIR='does-not-exist'))
    assert errors == []


def test_preflight_rejects_development_auth_flags_and_wildcard_cors():
    errors, _ = configuration_issues(production(DISABLE_AUTH=True, CORS_ORIGINS='*'))
    assert any('DISABLE_AUTH' in error for error in errors)
    assert any('CORS_ORIGINS' in error for error in errors)
    assert 'private-key' not in ' '.join(errors)

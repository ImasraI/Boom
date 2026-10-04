from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
import requests
from app.auth import sms


@pytest.fixture
def sender(monkeypatch):
    settings = SimpleNamespace(SMS_API_KEY='private-key', SMS_VERIFY_TEMPLATE_ID='123',
        SMS_VERIFY_PARAMETER_NAME='CODE', SMS_BASE_URL='https://api.sms.ir',
        SMS_PROXY='', GEMINI_PROXY='http://wrong-ai-proxy:10809', SMS_TRUST_ENV=False)
    monkeypatch.setattr(sms, 'get_settings', lambda: settings)
    session = MagicMock()
    session.__enter__.return_value = session
    response = MagicMock(status_code=200)
    response.json.return_value = {'status': 1, 'data': {'messageId': 456}}
    session.post.return_value = response
    monkeypatch.setattr(sms, '_sms_session', lambda: session)
    monkeypatch.setattr(sms.time, 'sleep', lambda _: None)
    return settings, session, response


def test_verify_is_immediate_and_uses_template_parameter_without_ai_proxy(sender, caplog):
    settings, session, _ = sender
    assert sms.send_verification_code('۰۹۱۲۱۱۱۲۲۳۳', '654321') == '456'
    kwargs = session.post.call_args.kwargs
    assert kwargs['json'] == {'mobile': '9121112233', 'templateId': 123, 'parameters': [{'name': 'CODE', 'value': '654321'}]}
    assert kwargs['proxies'] is None
    assert '654321' not in caplog.text and '9121112233' not in caplog.text and 'private-key' not in caplog.text
    assert 'message_id=456' in caplog.text


def test_explicit_sms_proxy_is_used(sender):
    settings, session, _ = sender
    settings.SMS_PROXY = 'http://sms-proxy:8080'
    sms.send_verification_code('9121112233', '123456')
    assert session.post.call_args.kwargs['proxies']['https'] == settings.SMS_PROXY


@pytest.mark.parametrize('body', [{'status': 10, 'message': 'secret-code=123456'}, [], None])
def test_http_success_does_not_hide_provider_rejection(sender, body, caplog):
    _, _, response = sender
    response.json.return_value = body
    with pytest.raises(RuntimeError): sms.send_verification_code('9121112233', '123456')
    assert '123456' not in caplog.text


def test_read_timeout_does_not_send_duplicate_sms(sender):
    _, session, _ = sender
    session.post.side_effect = requests.ReadTimeout('ambiguous')
    with pytest.raises(RuntimeError): sms.send_verification_code('9121112233', '123456')
    assert session.post.call_count == 1


def test_connect_timeout_can_retry_before_transmission(sender):
    _, session, response = sender
    session.post.side_effect = [requests.ConnectTimeout(), response]
    assert sms.send_verification_code('9121112233', '123456') == '456'
    assert session.post.call_count == 2


def test_arabic_indic_mobile_digits_are_supported():
    assert sms.normalize_ir_mobile('+٩٨٩١٢١١١٢٢٣٣') == '9121112233'


def test_delivery_report_returns_timing_without_otp_or_mobile(sender):
    _, session, response = sender
    session.get.return_value = response
    response.json.return_value = {'status': 1, 'data': {'sendDateTime': 1000,
        'deliveryDateTime': 2000, 'deliveryState': 1, 'mobile': '9121112233',
        'messageText': 'OTP 123456', 'messageId': 456}}
    assert sms.sms_delivery_report(456) == {'message_id': 456, 'send_at': 1000, 'delivery_at': 2000, 'delivery_state': 1}
    assert session.get.call_args.args[0].endswith('/v1/send/456')


def test_credit_handles_malformed_provider_body(sender):
    _, session, response = sender
    session.get.return_value = response
    response.json.return_value = []
    assert sms.sms_credit()['credit'] == 0

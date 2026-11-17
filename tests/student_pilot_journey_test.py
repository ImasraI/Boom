"""Offline HTTP journey: real auth/JWT and pilot persistence, simulated SMS only."""
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.auth import router as auth
from app.routers import student_pilot


def test_signup_login_answer_feedback_journey(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        APP_ENV='production', DISABLE_AUTH=False, SMS_DEBUG_ECHO=False,
        SMS_API_KEY='synthetic', SMS_VERIFY_TEMPLATE_ID='synthetic', SIGNUP_BYPASS_CODE=''))
    sent = []
    monkeypatch.setattr(auth, 'send_verification_code', lambda phone, code: sent.append((phone, code)))
    monkeypatch.setattr(auth, 'rate_limit', lambda *args, **kwargs: None)
    path = tmp_path / 'packet.json'
    path.write_text(json.dumps({'revision': 'synthetic-v1',
        'questions': [{'id': 'Q1', 'text': '2+2?', 'options': ['1','2','3','4'],
                       'answer': 3, 'explanation': '2+2=4'}]}), encoding='utf8')
    monkeypatch.setenv('BOOM_STUDENT_PILOT_PACKET', str(path))
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(student_pilot.router)
    client = TestClient(app)
    headers = {}
    assert client.get('/api/student-pilot', headers=headers).status_code == 401
    phone = '9125550198'
    result = client.post('/api/auth/request-code', json={'phone': phone})
    assert result.status_code == 200 and result.json()['debug_code'] is None
    body = {'phone': phone, 'code': 'incorrect', 'password': 'synthetic-password'}
    assert client.post('/api/auth/register/complete', json=body).status_code == 400
    body['code'] = sent[0][1]
    assert client.post('/api/auth/register/complete', json=body).status_code == 200
    login = client.post('/api/auth/login', data={'username': phone, 'password': body['password']})
    assert login.status_code == 200
    headers['Authorization'] = 'Bearer ' + login.json()['access_token']
    opened = client.get('/api/student-pilot', headers=headers)
    assert opened.status_code == 200 and opened.headers['cache-control'] == 'private, no-store'
    assert 'answer' not in opened.json()['questions'][0]
    assert 'explanation' not in opened.json()['questions'][0]
    feedback = {'revision': 'synthetic-v1', 'comments': {'Q1': 'synthetic feedback'}}
    assert client.post('/api/student-pilot/feedback', headers=headers, json=feedback).status_code == 409
    attempt = {'revision':'stale', 'answers':{'Q1':3}, 'confidence':{'Q1':4}}
    assert client.post('/api/student-pilot/submit', headers=headers, json=attempt).status_code == 409
    attempt['revision'] = 'synthetic-v1'
    assert client.post('/api/student-pilot/submit', headers=headers, json={**attempt, 'answers':{'Q1':True}}).status_code == 422
    submitted = client.post('/api/student-pilot/submit', headers=headers, json=attempt)
    assert submitted.status_code == 200 and submitted.json()['questions'][0]['answer'] == 3
    attempt['answers']['Q1'] = 0
    assert client.post('/api/student-pilot/submit', headers=headers, json=attempt).json()['answers']['Q1'] == 3
    assert client.post('/api/student-pilot/feedback', headers=headers, json=feedback).status_code == 200
    assert client.get('/api/student-pilot', headers=headers).json()['feedback'] == feedback['comments']
    # Another real JWT/account must not see the first participant's answers.
    other_phone = '9125550199'
    assert client.post('/api/auth/request-code', json={'phone': other_phone}).status_code == 200
    assert client.post('/api/auth/register/complete', json={
        **body, 'phone': other_phone, 'code': sent[-1][1],
    }).status_code == 200
    other_login = client.post('/api/auth/login', data={'username': other_phone, 'password': body['password']})
    assert other_login.status_code == 200
    other_token = other_login.json()['access_token']
    other = client.get('/api/student-pilot', headers={'Authorization': 'Bearer ' + other_token})
    assert other.status_code == 200 and other.json()['answers'] is None

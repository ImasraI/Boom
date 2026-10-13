"""Real proxy middleware and auth budgets; no SMS or provider requests."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.auth import limits


@pytest.fixture(autouse=True)
def isolated_limiter(monkeypatch):
    monkeypatch.setattr(limits, "_limiter", limits._RateLimiter())


def request(path, host="203.0.113.1"):
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={},
                           url=SimpleNamespace(path=path))


def test_login_attempts_do_not_exhaust_first_sms_request():
    login = request("/api/auth/login")
    for _ in range(10):
        limits.rate_limit(login, 10, 300)
    limits.rate_limit(request("/api/auth/request-code"), 5, 600)
    with pytest.raises(HTTPException) as error:
        limits.rate_limit(login, 10, 300)
    assert error.value.status_code == 429


def test_sms_window_not_pruned_by_shorter_login_window(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(limits.time, "monotonic", lambda: now[0])
    sms = request("/api/auth/request-code")
    for _ in range(5):
        limits.rate_limit(sms, 5, 600)
    now[0] += 400
    limits.rate_limit(request("/api/auth/login"), 10, 300)
    with pytest.raises(HTTPException) as error:
        limits.rate_limit(sms, 5, 600)
    assert error.value.headers["Retry-After"] == "200"
    assert "200" in error.value.detail
    now[0] += 201
    limits.rate_limit(sms, 5, 600)


def proxy_app(peer):
    app = FastAPI()
    @app.get("/limited")
    def limited(req: Request):
        limits.rate_limit(req, 1, 600)
        return {"ip": limits.client_ip(req)}
    return TestClient(ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"]), client=(peer, 12345))


def test_trusted_proxy_keeps_clients_independent():
    with proxy_app("127.0.0.1") as client:
        assert client.get("/limited", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
        assert client.get("/limited", headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 200
        response = client.get("/limited", headers={"X-Forwarded-For": "203.0.113.1"})
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0


def test_untrusted_client_cannot_bypass_limit_by_spoofing_forwarded_ip():
    with proxy_app("198.51.100.1") as client:
        response = client.get("/limited", headers={"X-Forwarded-For": "203.0.113.1"})
        assert response.json()["ip"] == "198.51.100.1"
        assert client.get("/limited", headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 429


def test_ipv6_clients_remain_separate():
    limits.rate_limit(request("/api/auth/login", "2001:db8::1"), 1, 60)
    limits.rate_limit(request("/api/auth/login", "2001:db8::2"), 1, 60)

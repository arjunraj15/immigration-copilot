import anthropic
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.errors import AppError, install_error_handlers
from app.db.session import engine
from app.main import app
from tests.conftest import TEST_DATABASE

client = TestClient(app)


def test_missing_actor_is_rejected() -> None:
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ACTOR_REQUIRED"


def test_unknown_actor_label_is_rejected() -> None:
    response = client.get("/api/me", headers={"X-Actor": "ADMIN-01"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ACTOR_INVALID"


def test_role_comes_from_the_label() -> None:
    ops = client.get("/api/me", headers={"X-Actor": "OPS-03"}).json()
    assert (ops["label"], ops["role"]) == ("OPS-03", "OPS")
    assert client.get("/api/me", headers={"X-Actor": "LEGAL-01"}).json()["role"] == "LEGAL"


def test_unknown_route_uses_error_shape() -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def _probe_app() -> TestClient:
    probe = FastAPI()
    install_error_handlers(probe)

    @probe.get("/app-error")
    def app_error() -> None:
        raise AppError("APPROVAL_REQUIRED", "Legal reviewer approval required first", 409)

    @probe.get("/crash")
    def crash() -> None:
        raise RuntimeError("boom")

    @probe.get("/needs-int")
    def needs_int(n: int) -> int:
        return n

    return TestClient(probe, raise_server_exceptions=False)


def test_app_error_keeps_code_and_status() -> None:
    response = _probe_app().get("/app-error")
    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "APPROVAL_REQUIRED", "message": "Legal reviewer approval required first"}
    }


def test_validation_and_crash_use_error_shape() -> None:
    probe = _probe_app()
    assert probe.get("/needs-int?n=x").json()["error"]["code"] == "VALIDATION_ERROR"
    crash = probe.get("/crash")
    assert crash.status_code == 500
    assert crash.json()["error"]["code"] == "INTERNAL_ERROR"


def test_tests_use_the_test_database() -> None:
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar() == TEST_DATABASE


def test_claude_client_is_faked(fake_claude) -> None:
    fake_claude.reply({"category": "PASSPORT"})
    response = anthropic.Anthropic(api_key="unused").messages.create(model="x", max_tokens=10, messages=[])
    assert response.content[0].text == '{"category": "PASSPORT"}'
    assert len(fake_claude.messages.calls) == 1

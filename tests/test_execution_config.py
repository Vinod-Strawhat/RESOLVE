"""Phase 7A-1 execution channel configuration and API tests."""

import pytest
from fastapi.testclient import TestClient

from backend.channels.base import ChannelConfigError
from backend.channels.factory import build_channel, get_configured_channel_name
from backend.main import app

from backend.services.action_executor import ActionExecutor
from backend.services.action_store import ActionStore
from backend.services.case_store import CaseStore


def test_default_channel_is_simulated(monkeypatch):
    monkeypatch.delenv("EXECUTION_CHANNEL", raising=False)
    assert get_configured_channel_name() == "simulated"
    assert build_channel().name == "simulated"


def test_explicit_simulated_channel(monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "simulated")
    assert build_channel().name == "simulated"


def test_smtp_channel_is_real(monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "smtp")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_FROM", "resolve@example.test")
    monkeypatch.setenv("SMTP_TO", "operator@example.test")
    channel = build_channel()
    assert channel.name == "smtp"


def test_unknown_channel_fails_closed(monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "aws-ses")
    with pytest.raises(ChannelConfigError, match="unknown EXECUTION_CHANNEL"):
        build_channel()


def test_case_sensitivity_normalized(monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "SMTP")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_FROM", "resolve@example.test")
    monkeypatch.setenv("SMTP_TO", "operator@example.test")
    assert build_channel().name == "smtp"


def test_smtp_without_config_fails_closed(monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "smtp")
    for name in ("SMTP_HOST", "SMTP_FROM", "SMTP_TO"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ChannelConfigError, match="SMTP"):
        build_channel()


# --- Config API ---


@pytest.fixture
def client():
    return TestClient(app)


def test_config_api_default_simulated(client, monkeypatch):
    monkeypatch.delenv("EXECUTION_CHANNEL", raising=False)
    response = client.get("/api/config/execution")
    assert response.status_code == 200
    body = response.json()
    assert body == {"channel": "simulated", "real_sending_enabled": False}


def test_config_api_reports_smtp(client, monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "smtp")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_FROM", "resolve@example.test")
    monkeypatch.setenv("SMTP_TO", "operator@example.test")
    response = client.get("/api/config/execution")
    assert response.status_code == 200
    assert response.json() == {"channel": "smtp", "real_sending_enabled": True}


def test_config_api_unknown_channel_500(client, monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "bogus-channel")
    response = client.get("/api/config/execution")
    assert response.status_code == 500


def test_config_api_does_not_expose_secrets(client, monkeypatch):
    monkeypatch.setenv("EXECUTION_CHANNEL", "smtp")
    monkeypatch.setenv("SMTP_HOST", "secret-host.internal")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("SMTP_FROM", "resolve@example.test")
    monkeypatch.setenv("SMTP_TO", "operator@example.test")
    monkeypatch.setenv("SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "supersecret-pw")
    response = client.get("/api/config/execution")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"channel", "real_sending_enabled"}
    raw = response.text.lower()
    assert "secret-host" not in raw
    assert "supersecret-pw" not in raw
    assert "smtp-user" not in raw
    assert "operator@example.test" not in raw


# --- Executor-level configuration integration ---


def test_executor_default_channel_is_simulated(monkeypatch, tmp_path):
    monkeypatch.delenv("EXECUTION_CHANNEL", raising=False)
    case_store = CaseStore(tmp_path / "resolve.db")
    action_store = ActionStore(tmp_path / "resolve.db")
    executor = ActionExecutor(action_store, case_store)
    assert executor.channel_name == "simulated"
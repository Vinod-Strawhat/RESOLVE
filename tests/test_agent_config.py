import pytest

from backend.agent.model import AgentConfigError, build_model


def test_build_model_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/test-model")
    with pytest.raises(AgentConfigError, match="OPENROUTER_API_KEY"):
        build_model()


def test_build_model_missing_model_id(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    with pytest.raises(AgentConfigError, match="OPENROUTER_MODEL"):
        build_model()
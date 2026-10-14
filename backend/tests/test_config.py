"""Unit tests for configuration loading, Cognee env mapping, and secret masking."""

import os

from pydantic import SecretStr

from app.config import Settings, export_cognee_env


def test_settings_initialization(monkeypatch):
    """Test that settings load properly and mask secrets."""
    monkeypatch.setenv("FALKORDB_HOST", "test.falkordb.cloud")
    monkeypatch.setenv("FALKORDB_PASSWORD", "super-secret-password")
    monkeypatch.setenv("LLM_API_KEY", "gsk_test_api_key")
    monkeypatch.setenv("FALKORDB_PORT", "62360")

    settings = Settings()

    assert settings.FALKORDB_HOST == "test.falkordb.cloud"
    assert settings.FALKORDB_PORT == 62360
    assert isinstance(settings.FALKORDB_PASSWORD, SecretStr)
    assert settings.FALKORDB_PASSWORD.get_secret_value() == "super-secret-password"
    # Ensure raw secret string is not in repr
    assert "super-secret-password" not in repr(settings)
    assert "gsk_test_api_key" not in repr(settings)


def test_export_cognee_env(monkeypatch):
    """Test that export_cognee_env correctly sets all required environment variables."""
    monkeypatch.setenv("FALKORDB_HOST", "cloud.falkor.test")
    monkeypatch.setenv("FALKORDB_PASSWORD", "secret123")
    monkeypatch.setenv("LLM_API_KEY", "gsk_llm_key")

    settings = Settings(
        FALKORDB_HOST="cloud.falkor.test",
        FALKORDB_PORT=62360,
        FALKORDB_PASSWORD=SecretStr("secret123"),
        LLM_API_KEY=SecretStr("gsk_llm_key"),
        LLM_MODEL="groq/qwen/qwen3.8-27b",
        LLM_BASE_URL="https://api.groq.com/openai/v1",
    )

    export_cognee_env(settings)

    assert os.environ["LLM_PROVIDER"] == "custom"
    assert os.environ["LLM_MODEL"] == "groq/qwen/qwen3.8-27b"
    assert os.environ["GRAPH_DATABASE_PROVIDER"] == "falkor"
    assert os.environ["GRAPH_DATABASE_URL"] == "cloud.falkor.test"
    assert os.environ["GRAPH_DATABASE_PORT"] == "62360"
    assert os.environ["GROQ_API_KEY"] == "gsk_llm_key"
    assert os.environ["VECTOR_DB_PROVIDER"] == "lancedb"

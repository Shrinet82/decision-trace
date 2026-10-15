"""Application configuration and environment variable loading.

Uses pydantic-settings to validate all environment variables, masks secrets in
logs/representations, and exports Cognee-specific environment mappings before
Cognee modules are loaded.
"""

import os
from functools import lru_cache
from pathlib import Path

from typing import Optional

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and .env."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # FalkorDB Cloud Settings
    FALKORDB_HOST: str = Field(..., description="FalkorDB host address")
    FALKORDB_PORT: int = Field(default=6379, description="FalkorDB port number")
    FALKORDB_USERNAME: str = Field(default="falkordb", description="FalkorDB username")
    FALKORDB_PASSWORD: SecretStr = Field(..., description="FalkorDB password")
    FALKORDB_GRAPH_NAME: str = Field(
        default="company_brain", description="Target graph database name"
    )

    # LLM & Embedding Settings
    LLM_API_KEY: SecretStr = Field(..., description="API key for LLM provider")
    LLM_BASE_URL: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Base URL for OpenAI-compatible LLM endpoint",
    )
    LLM_MODEL: str = Field(
        default=os.getenv("LLM_MODEL", "bedrock/amazon.nova-lite-v1:0"),
        description="Target model identifier with provider prefix for LiteLLM routing",
    )
    BEDROCK_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="Amazon Bedrock API Key",
    )
    AWS_REGION_NAME: str = Field(
        default=os.getenv("AWS_REGION_NAME", "us-east-1"),
        description="AWS Region for Bedrock models",
    )
    EMBEDDING_PROVIDER: str = Field(
        default="fastembed", description="Embedding provider (fastembed for local embeddings)"
    )
    EMBEDDING_MODEL: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Local embedding model identifier",
    )

    # Vector Storage Settings
    VECTOR_DB_PROVIDER: str = Field(
        default="lancedb",
        description="Vector database provider (lancedb saves cloud memory)",
    )
    LANCEDB_PATH: str = Field(
        default=".lancedb",
        description="Local directory path for LanceDB vector files",
    )

    SYSTEM_ROOT_DIRECTORY: str = Field(
        default=os.getenv("SYSTEM_ROOT_DIRECTORY", str(Path.home() / ".cognee_system")),
        description="Path for Cognee system database and metadata",
    )
    DATA_ROOT_DIRECTORY: str = Field(
        default=os.getenv("DATA_ROOT_DIRECTORY", str(Path.home() / ".cognee_data")),
        description="Path for Cognee data storage",
    )

    # Application & Security Settings
    FRONTEND_ORIGIN: str = Field(
        default="http://localhost:5173",
        description="Allowed frontend CORS origin",
    )
    ADMIN_TOKEN: SecretStr = Field(
        default=SecretStr("dev-secret-token-change-in-production"),
        description="Token required for administrative endpoints",
    )
    DATASET_NAME: str = Field(
        default="company_brain",
        description="Unified dataset name to ensure entities land in a single graph",
    )
    HOST: str = Field(default="0.0.0.0", description="FastAPI host binding")
    PORT: int = Field(default=8000, description="FastAPI port binding")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    @model_validator(mode="after")
    def resolve_bedrock(self) -> "Settings":
        env_model = os.getenv("LLM_MODEL")
        if env_model:
            self.LLM_MODEL = env_model
            return self
        if "LLM_MODEL" not in self.model_fields_set and os.getenv("USE_GROQ") != "1" and self.BEDROCK_API_KEY:
            target_model = os.getenv("BEDROCK_MODEL", "bedrock/amazon.nova-lite-v1:0")
            if not self.LLM_MODEL.startswith("bedrock/"):
                self.LLM_MODEL = target_model
        return self


def export_cognee_env(settings: Settings) -> None:
    """Export the environment variables required by Cognee before it is imported.

    Cognee evaluates its LLMConfig, GraphConfig, and VectorConfig during module
    import time. These settings must be exported into os.environ beforehand.
    """
    os.environ["SYSTEM_ROOT_DIRECTORY"] = settings.SYSTEM_ROOT_DIRECTORY
    os.environ["DATA_ROOT_DIRECTORY"] = settings.DATA_ROOT_DIRECTORY
    os.environ["LLM_TEMPERATURE"] = "0.0"

    if settings.LLM_MODEL.startswith("bedrock/"):
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_MODEL"] = settings.LLM_MODEL
        os.environ.pop("LLM_ENDPOINT", None)
        active_key = (
            settings.BEDROCK_API_KEY.get_secret_value()
            if settings.BEDROCK_API_KEY
            else settings.LLM_API_KEY.get_secret_value()
        )
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = active_key
        os.environ["LLM_API_KEY"] = active_key
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ["AWS_REGION_NAME"] = settings.AWS_REGION_NAME
        os.environ["AWS_DEFAULT_REGION"] = settings.AWS_REGION_NAME
    else:
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_MODEL"] = settings.LLM_MODEL
        os.environ["LLM_ENDPOINT"] = settings.LLM_BASE_URL
        os.environ["GROQ_API_KEY"] = settings.LLM_API_KEY.get_secret_value()
        os.environ["OPENAI_API_KEY"] = settings.LLM_API_KEY.get_secret_value()

    os.environ["EMBEDDING_PROVIDER"] = settings.EMBEDDING_PROVIDER
    os.environ["EMBEDDING_MODEL"] = settings.EMBEDDING_MODEL

    # Graph database configuration
    os.environ["GRAPH_DATABASE_PROVIDER"] = "falkor"
    os.environ["GRAPH_DATABASE_URL"] = settings.FALKORDB_HOST
    os.environ["GRAPH_DATABASE_PORT"] = str(settings.FALKORDB_PORT)
    os.environ["GRAPH_DATABASE_USERNAME"] = settings.FALKORDB_USERNAME
    os.environ["GRAPH_DATABASE_PASSWORD"] = settings.FALKORDB_PASSWORD.get_secret_value()
    os.environ["GRAPH_DATABASE_NAME"] = settings.FALKORDB_GRAPH_NAME
    os.environ["GRAPH_DATASET_DATABASE_HANDLER"] = "falkor_graph_local"

    # Vector storage configuration
    os.environ["VECTOR_DB_PROVIDER"] = settings.VECTOR_DB_PROVIDER
    os.environ["VECTOR_DB_URL"] = settings.LANCEDB_PATH


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    settings = Settings()
    export_cognee_env(settings)
    return settings

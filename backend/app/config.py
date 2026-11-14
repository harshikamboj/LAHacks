"""Load the repository .env regardless of the process working directory."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    mongodb_uri: SecretStr = SecretStr("")
    mongodb_setup_uri: SecretStr = SecretStr("")
    mongodb_db: str = "tradeops"
    mongodb_timeout_ms: int = Field(default=10000, ge=1000, le=60000)
    mongodb_vector_index: str = "incident_vector_index"
    voyage_api_key: SecretStr = SecretStr("")
    voyage_model: str = "voyage-3.5-lite"
    memory_enabled: bool = True
    atlas_project_id: str = ""
    atlas_cluster_name: str = ""
    atlas_sandbox_confirmed: bool = False
    demo_mode: bool = True
    demo_reviewer_id: str = "demo-reviewer"
    demo_reviewer_token: SecretStr = SecretStr("")
    demo_case_id: str = "SI-2041"
    demo_trade_id: str = "TR-2041"
    market_data_file: str = ""
    worker_offline_seconds: float = 5.0

    @property
    def worker_record_id(self) -> str:
        return (
            "workflow-worker" if self.demo_case_id == "SI-2041" else f"worker-{self.demo_case_id}"
        )

    # Simulated external systems (app lane). Each is its own process with its own SQLite file.
    broker_url: str = "http://127.0.0.1:8101"
    directory_url: str = "http://127.0.0.1:8102"
    custodian_url: str = "http://127.0.0.1:8103"
    sim_admin_token: SecretStr = SecretStr("")

    # Workflow worker
    custodian_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    worker_poll_seconds: float = Field(default=1.0, gt=0, le=10)

    @field_validator("mongodb_db")
    @classmethod
    def database_is_scoped(cls, value: str) -> str:
        if value != "tradeops" and not value.startswith("tradeops_test_"):
            raise ValueError("Use tradeops or an explicitly isolated tradeops_test_ database")
        return value

    def connection_uri(self, *, setup: bool = False) -> str:
        secret = self.mongodb_setup_uri if setup else self.mongodb_uri
        uri = secret.get_secret_value()
        if not uri or "<" in uri or not uri.startswith(("mongodb://", "mongodb+srv://")):
            name = "MONGODB_SETUP_URI" if setup else "MONGODB_URI"
            raise ValueError(f"Configure {name} in the gitignored repository .env")
        return uri


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings for the API and worker (tests construct Settings directly)."""
    return Settings()

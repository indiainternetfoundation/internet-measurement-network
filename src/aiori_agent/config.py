from typing import List
import uuid
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings, cli_parse_args=True, cli_exit_on_error=False):
    agent_id: str = Field(default=str(uuid.uuid4()), env="AGENT_ID")
    agent_name: str = Field(default="AGENT-1", env="AGENT_NAME")
    SERVERS: List[str] = Field(default_factory=lambda: ["nats://127.0.0.1:4222"], env="SERVERS")
    modules_path: Path = Field(default=Path("modules"))
    error_log_dir: Path = Field(default=Path(".errors"))
    message_log_dir: Path = Field(default=Path(".messages"))
    crash_state_file: Path = Field(default=Path(".errors/crash_state.json"))
    max_crash_retries: int = 3

    # class Config:
    #     env_file = ".env"
    #     env_nested_delimiter = "_"
    #     case_sensitive = False
    #     extra = "forbid"

    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="_", case_sensitive=False, extra="ignore"
    )


settings = Settings()

settings.modules_path.mkdir(parents=True, exist_ok=True)
settings.error_log_dir.mkdir(parents=True, exist_ok=True)
settings.message_log_dir.mkdir(parents=True, exist_ok=True)
settings.crash_state_file.touch()

"""Configuration management for Unraid MCP server using pydantic-settings."""

from __future__ import annotations

import enum
import logging

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class UnraidMode(enum.StrEnum):
    """Server operation mode."""

    READONLY = "readonly"
    READWRITE = "readwrite"


class UnraidConfig(BaseSettings):
    """Configuration loaded from environment variables and .env file."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Mode
    unraid_mode: UnraidMode = UnraidMode.READONLY

    # Connection
    unraid_host: str = "tower.local"
    unraid_port: int = Field(default=443, ge=1, le=65535)
    unraid_use_https: bool = True
    unraid_api_key: str | None = None
    unraid_verify_ssl: bool = False

    # General
    unraid_request_timeout: int = Field(default=30, gt=0)
    unraid_max_retries: int = Field(default=3, ge=0)

    # Feature gates
    # Secondary switch on top of `unraid_mode`. When False (default), the
    # `unraid_create_user` and `unraid_delete_user` tools stay hidden even
    # in readwrite mode — useful for operators who want container/VM writes
    # but not account mutation.
    unraid_allow_user_mutations: bool = False

    @property
    def is_readwrite(self) -> bool:
        """Whether server is in read-write mode."""
        return self.unraid_mode == UnraidMode.READWRITE

    @property
    def api_enabled(self) -> bool:
        """Whether the Unraid API is configured (host + key set)."""
        return self.unraid_api_key is not None

    @property
    def base_url(self) -> str:
        """Base URL for the Unraid GraphQL endpoint."""
        scheme = "https" if self.unraid_use_https else "http"
        return f"{scheme}://{self.unraid_host}:{self.unraid_port}"

    @property
    def graphql_url(self) -> str:
        """Full GraphQL endpoint URL."""
        return f"{self.base_url}/graphql"

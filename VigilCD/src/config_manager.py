"""Config Manager."""

import logging
import os
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SchedulingConfig(BaseModel):
    """Sheduling related configuration."""

    check_interval_minutes: int = 1

    git_retry_count: int = 3  # VIGILCD_GIT_RETRY_COUNT
    retry_backoff_factor: float = 2.0  # VIGILCD_RETRY_BACKOFF_FACTOR


class DeploymentConfig(BaseModel):
    """Deployment related configuration."""

    docker_compose_timeout_seconds: int = 300
    git_operation_timeout_seconds: int = 60
    docker_daemon_timeout_seconds: int = 10


class LoggingConfig(BaseModel):
    """Logging related configuration."""

    level: str = "INFO"
    format: str = "json"  # "json" oder "text"


class ConfigManager:
    """Configuration Manager"""

    def __init__(self, config_file: str = "./config/config.yaml"):
        self.config_file = config_file
        self.raw_config = {}
        self.scheduling: SchedulingConfig
        self.deployment: DeploymentConfig
        self.logging_config: LoggingConfig
        self.repos_config = []

        self._load_and_parse()
        self._apply_env_overrides()
        self._validate()

    def _load_and_parse(self) -> None:
        """Loads and parses the YAML config file."""
        try:
            with open(self.config_file, encoding="utf-8") as f:
                self.raw_config = yaml.safe_load(f)
            logger.info(f"Config geladen: {self.config_file}")
        except FileNotFoundError:
            logger.error(f"Config-Datei nicht gefunden: {self.config_file}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"YAML-Parse-Fehler: {e}")
            raise

        self.scheduling = SchedulingConfig()  # Keine YAML Params
        self.deployment = DeploymentConfig()  # Keine YAML Params
        self.logging_config = LoggingConfig()  # Keine YAML Params
        self.repos_config = self.raw_config.get("repos", [])

    def _apply_env_overrides(self) -> None:
        """Loads Overrides from Environment Variables."""
        if env_val := os.getenv("VIGILCD_CHECK_INTERVAL_MINUTES"):
            self.scheduling.check_interval_minutes = int(env_val)
        if env_val := os.getenv("VIGILCD_GIT_RETRY_COUNT"):
            self.scheduling.git_retry_count = int(env_val)
        if env_val := os.getenv("VIGILCD_RETRY_BACKOFF_FACTOR"):
            self.scheduling.retry_backoff_factor = float(env_val)

        if env_val := os.getenv("VIGILCD_DOCKER_TIMEOUT"):
            self.deployment.docker_compose_timeout_seconds = int(env_val)
        if env_val := os.getenv("VIGILCD_GIT_TIMEOUT"):
            self.deployment.git_operation_timeout_seconds = int(env_val)
        if env_val := os.getenv("VIGILCD_DOCKER_DAEMON_TIMEOUT"):
            self.deployment.docker_daemon_timeout_seconds = int(env_val)

        if env_val := os.getenv("VIGILCD_LOG_LEVEL"):
            self.logging_config.level = env_val.upper()
        if env_val := os.getenv("VIGILCD_LOG_FORMAT"):
            self.logging_config.format = env_val.lower()

    def _validate(self) -> None:
        """Valdiates the loaded configuration."""
        if self.scheduling.check_interval_minutes < 1:
            raise ValueError("check_interval_minutes muss >= 1 sein")
        if self.deployment.docker_compose_timeout_seconds < 10:
            raise ValueError("docker_compose_timeout_seconds muss >= 10 sein")
        logger.info("Config-Validierung erfolgreich")

    def get_ssh_key_path(self) -> str | None:
        """Gets global SSH Key Path from Env-Var.

        Returns:
            path to SSH key or None

        """
        return os.getenv("VIGILCD_SSH_KEY_PATH")

    def get_github_token(self) -> str | None:
        """Gets GitHub Token from Env-Var.

        Returns:
            GitHub Token or None

        """
        return os.getenv("VIGILCD_GITHUB_TOKEN")

    def get_webhook_secret(self) -> str | None:
        """Gets GitHub Webhook Secret from Env-Var.

        Returns:
            Webhook Secret or None

        """
        return os.getenv("VIGILCD_GITHUB_WEBHOOK_SECRET")

    def get_all_settings(self) -> dict[str, Any]:
        """Gets non-sensitive settings for API.

        Returns:
            dict with non-sensitive settings

        """
        return {
            "scheduling": self.scheduling.dict(),
            "deployment": self.deployment.dict(),
            "logging": self.logging_config.dict(),
            "repos_count": len(self.repos_config),
        }

    def to_dict(self) -> dict[str, Any]:
        """Gets the full configuration as a dictionary.

        Returns:
            dict with full configuration

        """
        return {
            "scheduling": self.scheduling.dict(),
            "deployment": self.deployment.dict(),
            "logging": self.logging_config.dict(),
            "repos": self.repos_config,
        }

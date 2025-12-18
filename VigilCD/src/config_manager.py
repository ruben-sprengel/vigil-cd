"""Config Manager."""

import logging
import os
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

from src.models import RepoConfig

logger = logging.getLogger(__name__)


class SchedulingConfig(BaseModel):
    """Sheduling related configuration."""

    check_interval_minutes: int = 1

    git_retry_count: int = 3  # VIGILCD_GIT_RETRY_COUNT
    retry_backoff_factor: float = 2.0  # VIGILCD_RETRY_BACKOFF_FACTOR


class DeploymentConfig(BaseModel):
    """Deployment related configuration.

    Timeout values can be:
    - float: Timeout in seconds (e.g., 30.0, 300.5)
    - None: No timeout (wait indefinitely - use with caution!)
    """

    docker_compose_timeout_seconds: float | None = 300.0
    git_operation_timeout_seconds: float | None = 60.0
    docker_daemon_timeout_seconds: float | None = 10.0

    @field_validator(
        "docker_compose_timeout_seconds",
        "git_operation_timeout_seconds",
        "docker_daemon_timeout_seconds",
    )
    @classmethod
    def validate_timeout_positive(cls, v: float | None) -> float | None:
        """Validates that timeout values are positive or None.

        Args:
            v: Timeout value

        Returns:
            Validated timeout value

        Raises:
            ValueError: If timeout is not positive (when not None)

        """
        if v is not None and v <= 0:
            raise ValueError("Timeout must be positive (> 0) or None")
        return v


class LoggingConfig(BaseModel):
    """Logging related configuration."""

    level: str = "INFO"
    format: str = "json"  # "json" oder "text"


class ConfigManager:
    """Configuration Manager."""

    def __init__(self, config_file: str) -> None:
        """Init the ConfigManager."""
        self.config_file: str = config_file
        self.raw_config: dict[str, Any] = {}
        self.scheduling: SchedulingConfig
        self.deployment: DeploymentConfig
        self.logging_config: LoggingConfig
        self.repos_config: list[RepoConfig] = []

        self._load_and_parse()
        self._apply_env_overrides()
        self._validate()

    def _load_and_parse(self) -> None:
        """Loads and parses the YAML config file."""
        try:
            with open(self.config_file, encoding="utf-8") as f:
                self.raw_config = yaml.safe_load(f) or {}
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

        repos_raw = self.raw_config.get("repos")
        if isinstance(repos_raw, list):
            valid_repos = []
            for idx, r_data in enumerate(repos_raw):
                try:
                    # Pydantic Model Validierung pro Eintrag
                    repo_obj = RepoConfig.model_validate(r_data)
                    valid_repos.append(repo_obj)
                except Exception as e:
                    logger.error(f"Fehler in Repo-Konfiguration (Index {idx}): {e}")

            self.repos_config = valid_repos
        else:
            self.repos_config = []
            if repos_raw is not None:
                logger.error("'repos' must be a list in config.yaml")
            else:
                logger.warning("No 'repos' key found in config.yaml")

    def _apply_env_overrides(self) -> None:
        """Loads Overrides from Environment Variables.

        For timeout values, use "none" or "null" to disable timeouts.
        """
        if env_val := os.getenv("VIGILCD_CHECK_INTERVAL_MINUTES"):
            self.scheduling.check_interval_minutes = int(env_val)
        if env_val := os.getenv("VIGILCD_GIT_RETRY_COUNT"):
            self.scheduling.git_retry_count = int(env_val)
        if env_val := os.getenv("VIGILCD_RETRY_BACKOFF_FACTOR"):
            self.scheduling.retry_backoff_factor = float(env_val)

        env_val = os.getenv("VIGILCD_DOCKER_TIMEOUT")
        if env_val is not None:
            self.deployment.docker_compose_timeout_seconds = self._parse_timeout(env_val)

        env_val = os.getenv("VIGILCD_GIT_TIMEOUT")
        if env_val is not None:
            self.deployment.git_operation_timeout_seconds = self._parse_timeout(env_val)

        env_val = os.getenv("VIGILCD_DOCKER_DAEMON_TIMEOUT")
        if env_val is not None:
            self.deployment.docker_daemon_timeout_seconds = self._parse_timeout(env_val)

        if env_val := os.getenv("VIGILCD_LOG_LEVEL"):
            self.logging_config.level = env_val.upper()
        if env_val := os.getenv("VIGILCD_LOG_FORMAT"):
            self.logging_config.format = env_val.lower()

    def _parse_timeout(self, value: str) -> float | None:
        """Parses a timeout value from environment variable.

        Args:
            value: String value ("30", "30.5", "none", "null")

        Returns:
            float or None

        """
        value_lower = value.lower().strip()
        if value_lower in ("none", "null", ""):
            return None
        try:
            return float(value)
        except ValueError as e:
            logger.warning(f"Invalid timeout value '{value}', using default")
            raise ValueError(f"Invalid timeout value: {value}") from e

    def _validate(self) -> None:
        """Valdiates the loaded configuration."""
        if self.scheduling.check_interval_minutes < 1:
            raise ValueError("check_interval_minutes muss >= 1 sein")

        # Timeout validation is now handled by Pydantic field_validator in DeploymentConfig

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
            "scheduling": self.scheduling.model_dump(),
            "deployment": self.deployment.model_dump(),
            "logging": self.logging_config.model_dump(),
            "repos_count": len(self.repos_config),
        }

    def to_dict(self) -> dict[str, Any]:
        """Gets the full configuration as a dictionary.

        Returns:
            dict with full configuration

        """
        return {
            "scheduling": self.scheduling.model_dump(),
            "deployment": self.deployment.model_dump(),
            "logging": self.logging_config.model_dump(),
            "repos": [r.model_dump() for r in self.repos_config],
        }

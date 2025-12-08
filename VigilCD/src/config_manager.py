"""
Config Manager mit Umgebungsvariablen-Support und Validierung.
"""
import os
import logging
from typing import Optional, Dict, Any
import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SchedulingConfig(BaseModel):
    check_interval_minutes: int = 1
    # Retry-Werte kommen NUR aus Umgebungsvariablen, nicht aus YAML!
    # Defaults sind hier definiert wenn keine Env-Var gesetzt ist
    git_retry_count: int = 3  # VIGILCD_GIT_RETRY_COUNT
    retry_backoff_factor: float = 2.0  # VIGILCD_RETRY_BACKOFF_FACTOR


class DeploymentConfig(BaseModel):
    docker_compose_timeout_seconds: int = 300
    git_operation_timeout_seconds: int = 60
    docker_daemon_timeout_seconds: int = 10


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"  # "json" oder "text"



class ConfigManager:
    """
    Zentrale Verwaltung aller Konfigurationen.
    Unterstützt YAML-Dateien und Umgebungsvariablen-Overrides.
    """

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

    def _load_and_parse(self):
        """Lädt YAML-Config-Datei (nur repos und self_update)."""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                self.raw_config = yaml.safe_load(f)
            logger.info(f"Config geladen: {self.config_file}")
        except FileNotFoundError:
            logger.error(f"Config-Datei nicht gefunden: {self.config_file}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"YAML-Parse-Fehler: {e}")
            raise

        # Parse Subsections
        self.scheduling = SchedulingConfig()  # Keine YAML Params
        self.deployment = DeploymentConfig()  # Keine YAML Params
        self.logging_config = LoggingConfig()  # Keine YAML Params
        self.repos_config = self.raw_config.get("repos", [])

    def _apply_env_overrides(self):
        """Lädt ALLE Settings aus Umgebungsvariablen (nicht nur Overrides)."""
        # Scheduling Settings
        if env_val := os.getenv("VIGILCD_CHECK_INTERVAL_MINUTES"):
            self.scheduling.check_interval_minutes = int(env_val)
        if env_val := os.getenv("VIGILCD_GIT_RETRY_COUNT"):
            self.scheduling.git_retry_count = int(env_val)
        if env_val := os.getenv("VIGILCD_RETRY_BACKOFF_FACTOR"):
            self.scheduling.retry_backoff_factor = float(env_val)

        # Deployment Settings
        if env_val := os.getenv("VIGILCD_DOCKER_TIMEOUT"):
            self.deployment.docker_compose_timeout_seconds = int(env_val)
        if env_val := os.getenv("VIGILCD_GIT_TIMEOUT"):
            self.deployment.git_operation_timeout_seconds = int(env_val)
        if env_val := os.getenv("VIGILCD_DOCKER_DAEMON_TIMEOUT"):
            self.deployment.docker_daemon_timeout_seconds = int(env_val)

        # Logging Settings
        if env_val := os.getenv("VIGILCD_LOG_LEVEL"):
            self.logging_config.level = env_val.upper()
        if env_val := os.getenv("VIGILCD_LOG_FORMAT"):
            self.logging_config.format = env_val.lower()

    def _validate(self):
        """Validiert Config-Werte."""
        if self.scheduling.check_interval_minutes < 1:
            raise ValueError("check_interval_minutes muss >= 1 sein")
        if self.deployment.docker_compose_timeout_seconds < 10:
            raise ValueError("docker_compose_timeout_seconds muss >= 10 sein")
        logger.info("Config-Validierung erfolgreich")

    def get_ssh_key_path(self) -> Optional[str]:
        """Gibt SSH-Key-Pfad aus Env-Var oder Config."""
        return os.getenv("VIGILCD_SSH_KEY_PATH")

    def get_github_token(self) -> Optional[str]:
        """Gibt GitHub API Token aus Env-Var."""
        return os.getenv("VIGILCD_GITHUB_TOKEN")

    def get_webhook_secret(self) -> Optional[str]:
        """Gibt GitHub Webhook Secret aus Env-Var."""
        return os.getenv("VIGILCD_GITHUB_WEBHOOK_SECRET")

    def get_all_settings(self) -> Dict[str, Any]:
        """Gibt alle Settings als Dict zurück (für API/Logging)."""
        return {
            "scheduling": self.scheduling.dict(),
            "deployment": self.deployment.dict(),
            "logging": self.logging_config.dict(),
            "repos_count": len(self.repos_config),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Export to dict für externe Nutzung."""
        return {
            "scheduling": self.scheduling.dict(),
            "deployment": self.deployment.dict(),
            "logging": self.logging_config.dict(),
            "repos": self.repos_config,
        }


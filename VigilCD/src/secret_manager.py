"""
Secret Management für VigilCD.
Unterstützt verschiedene Storage-Backend:
- Environment Variables
- Docker Secrets
- .env Dateien
- Externe Provider (z.B. Vault)
"""
import os
import logging
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretManager:
    """
    Zentrale Verwaltung von Secrets für Git-Auth und Docker-Credentials.
    """

    def __init__(self, backend: str = "env"):
        """
        Initialisiere Secret Manager.

        Args:
            backend: Storage-Backend ("env", "docker", "file")
        """
        self.backend = backend
        self._cache: Dict[str, str] = {}
        logger.info(f"SecretManager initialized with backend: {backend}")

        if backend == "file":
            self._load_env_file()

    def _load_env_file(self, env_file: str = ".env.secrets"):
        """Lädt Secrets aus einer .env.secrets Datei."""
        env_path = Path(env_file)
        if not env_path.exists():
            logger.warning(f"Secret file not found: {env_file}")
            return

        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        key, _, value = line.partition("=")
                        self._cache[key.strip()] = value.strip()
            logger.info(f"Loaded {len(self._cache)} secrets from {env_file}")
        except Exception as e:
            logger.error(f"Failed to load secret file: {e}")

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Ruft ein Secret ab.

        Args:
            key: Secret-Schlüssel (z.B. "GITHUB_TOKEN")
            default: Standardwert wenn nicht gefunden

        Returns:
            Secret-Wert oder default
        """
        if self.backend == "env":
            return os.getenv(key, default)
        elif self.backend == "docker":
            # Docker Secrets liegen unter /run/secrets/{key}
            secret_path = Path(f"/run/secrets/{key}")
            if secret_path.exists():
                try:
                    return secret_path.read_text().strip()
                except Exception as e:
                    logger.error(f"Failed to read Docker secret {key}: {e}")
            return default
        elif self.backend == "file":
            return self._cache.get(key, default)

        return default

    def get_git_credentials(self, repo_url: str) -> Optional[Dict[str, str]]:
        """
        Gibt Git-Credentials für eine Repository URL.
        Unterstützt HTTPS (Token) und SSH (Key).

        Returns:
            {"type": "token", "value": "..."} oder {"type": "ssh_key", "path": "..."}
        """
        if "github.com" in repo_url.lower():
            token = self.get_secret("GITHUB_TOKEN")
            if token:
                return {"type": "token", "value": token}

        # SSH Key
        ssh_key_path = self.get_secret("SSH_KEY_PATH")
        if ssh_key_path and Path(ssh_key_path).exists():
            return {"type": "ssh_key", "path": ssh_key_path}

        return None

    def get_docker_credentials(self, registry: str = "default") -> Optional[Dict[str, str]]:
        """
        Gibt Docker Registry Credentials.

        Args:
            registry: Registry-Name (z.B. "docker", "ghcr", "private")

        Returns:
            {"username": "...", "password": "..."} oder None
        """
        username = self.get_secret(f"DOCKER_{registry.upper()}_USERNAME")
        password = self.get_secret(f"DOCKER_{registry.upper()}_PASSWORD")

        if username and password:
            return {"username": username, "password": password}

        return None

    def get_webhook_secret(self) -> Optional[str]:
        """Gibt GitHub Webhook Secret."""
        return self.get_secret("GITHUB_WEBHOOK_SECRET")

    def store_secret(self, key: str, value: str, ttl_seconds: Optional[int] = None):
        """
        Speichert ein Secret (nur für 'file' backend).

        WARNUNG: Für Production sollte ein echter Secrets-Manager (Vault, AWS Secrets Manager) verwendet werden.

        Args:
            key: Secret-Schlüssel
            value: Secret-Wert
            ttl_seconds: TTL in Sekunden (optional, nicht implementiert)
        """
        if self.backend == "file":
            self._cache[key] = value
            logger.warning(f"Secret stored in memory only (not persisted): {key}")
        else:
            logger.warning(f"Secret storage not supported for backend: {self.backend}")


# Singleton-Instanz
_secret_manager: Optional[SecretManager] = None


def get_secret_manager(backend: str = None) -> SecretManager:
    """Gibt die globale SecretManager-Instanz."""
    global _secret_manager
    if _secret_manager is None:
        _backend = backend or os.getenv("VIGILCD_SECRET_BACKEND", "env")
        _secret_manager = SecretManager(backend=_backend)
    return _secret_manager


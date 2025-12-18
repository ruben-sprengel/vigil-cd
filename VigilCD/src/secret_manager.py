"""Secret Management for VigilCD."""

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SecretManager:
    """Central management of secrets for Git auth and Docker credentials."""

    TRUSTED_GIT_HOSTS = {
        "github.com",
        "gitlab.com",
        "bitbucket.org",
    }

    def __init__(self, backend: str = "env") -> None:
        """Initialize Secret Manager.

        Args:
            backend: Storage backend ("env", "docker", "file")

        """
        self.backend = backend
        self._cache: dict[str, str] = {}
        logger.info(f"SecretManager initialized with backend: {backend}")

        if backend == "file":
            self._load_env_file()

    def _load_env_file(self, env_file: str = ".env.secrets") -> None:
        """Loads secrets from a .env.secrets file.

        Args:
            env_file: Path to the .env file

        """
        env_path = Path(env_file)
        if not env_path.exists():
            logger.warning(f"Secret file not found: {env_file}")
            return

        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()  # noqa: PLW2901
                    if line and not line.startswith("#"):
                        key, _, value = line.partition("=")
                        self._cache[key.strip()] = value.strip()
            logger.info(f"Loaded {len(self._cache)} secrets from {env_file}")
        except Exception as e:
            logger.error(f"Failed to load secret file: {e}")

    def get_secret(self, key: str, default: str | None = None) -> str | None:
        """Retrieves a secret.

        Args:
            key: Secret key (e.g., "GITHUB_TOKEN")
            default: Default value if not found

        Returns:
            Secret value or default

        """
        if self.backend == "env":
            return os.getenv(key, default)
        elif self.backend == "docker":
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

    def parse_git_url(self, repo_url: str) -> dict[str, str] | None:
        """Securely parses a Git repository URL.

        Args:
            repo_url: Git repository URL (HTTPS or SSH)

        Returns:
            {
                "scheme": "https" or "ssh",
                "hostname": "github.com",
                "path": "/user/repo.git",
                "url": original URL
            }
            or None if parsing fails

        Security:
            - Properly extracts hostname from URL
            - Handles both HTTPS and SSH formats
            - No substring matching vulnerability
        """
        try:
            # Handle SSH URLs: git@github.com:user/repo.git
            if repo_url.startswith("git@"):
                # Parse SSH-style URL
                parts = repo_url.replace("git@", "").split(":", 1)
                if len(parts) != 2:  # noqa: PLR2004
                    logger.warning(f"Invalid SSH URL format: {repo_url}")
                    return None

                hostname = parts[0]
                path = "/" + parts[1]

                return {
                    "scheme": "ssh",
                    "hostname": hostname.lower(),
                    "path": path,
                    "url": repo_url,
                }

            # Handle HTTPS URLs: https://github.com/user/repo.git
            parsed = urlparse(repo_url)

            if not parsed.scheme or not parsed.hostname:
                logger.warning(f"Invalid URL format: {repo_url}")
                return None

            return {
                "scheme": parsed.scheme.lower(),
                "hostname": parsed.hostname.lower(),
                "path": parsed.path,
                "url": repo_url,
            }

        except Exception as e:
            logger.error(f"Failed to parse Git URL: {repo_url}, error: {e}")
            return None

    def is_trusted_git_host(self, hostname: str) -> bool:
        """Checks if a hostname is a trusted Git hosting provider.

        Args:
            hostname: Hostname to check (e.g., "github.com")

        Returns:
            True if hostname is trusted, False otherwise

        Security:
            - Exact hostname match only (no substring matching)
            - Case-insensitive comparison
            - No wildcard subdomains (github.com != foo.github.com)
        """
        hostname_lower = hostname.lower()
        return hostname_lower in self.TRUSTED_GIT_HOSTS

    def get_git_credentials(self, repo_url: str) -> dict[str, str] | None:  # noqa: PLR0911
        """Returns Git credentials for a repository URL.

        Supports HTTPS (token) and SSH (key).

        Args:
            repo_url: Git repository URL

        Returns:
            {"type": "token", "value": "...", "host": "github.com"} or
            {"type": "ssh_key", "path": "...", "host": "..."} or
            None if URL is untrusted or credentials not available

        Security:
            - Uses secure URL parsing (no substring matching)
            - Only returns credentials for trusted hosts
            - Prevents credential leakage to malicious domains
        """
        parsed = self.parse_git_url(repo_url)
        if not parsed:
            logger.warning(f"Could not parse repository URL: {repo_url}")
            return None

        hostname = parsed["hostname"]

        # Security check: Only return credentials for trusted hosts
        if not self.is_trusted_git_host(hostname):
            logger.warning(f"Refusing to provide credentials for untrusted host: {hostname}")
            return None

        # Return appropriate credentials based on host
        if hostname == "github.com":
            token = self.get_secret("GITHUB_TOKEN")
            if token:
                return {"type": "token", "value": token, "host": hostname}

        elif hostname == "gitlab.com":
            token = self.get_secret("GITLAB_TOKEN")
            if token:
                return {"type": "token", "value": token, "host": hostname}

        elif hostname == "bitbucket.org":
            token = self.get_secret("BITBUCKET_TOKEN")
            if token:
                return {"type": "token", "value": token, "host": hostname}

        # Fallback: Try SSH key if no token available
        ssh_key_path = self.get_secret("SSH_KEY_PATH")
        if ssh_key_path and Path(ssh_key_path).exists():
            return {"type": "ssh_key", "path": ssh_key_path, "host": hostname}

        # No credentials available for this host
        logger.debug(f"No credentials configured for {hostname}")
        return None

    def get_docker_credentials(self, registry: str = "default") -> dict[str, str] | None:
        """Returns Docker registry credentials.

        Args:
            registry: Registry name (e.g., "docker", "ghcr", "private")

        Returns:
            {"username": "...", "password": "..."} or None

        """
        username = self.get_secret(f"DOCKER_{registry.upper()}_USERNAME")
        password = self.get_secret(f"DOCKER_{registry.upper()}_PASSWORD")

        if username and password:
            return {"username": username, "password": password}

        return None

    def get_webhook_secret(self) -> str | None:
        """Returns GitHub webhook secret."""
        return self.get_secret("GITHUB_WEBHOOK_SECRET")

    def store_secret(self, key: str, value: str, ttl_seconds: int | None = None):
        """Stores a secret (only for 'file' backend).

        WARNING: For production, use a real secrets manager (Vault, AWS Secrets Manager).

        Args:
            key: Secret key
            value: Secret value
            ttl_seconds: TTL in seconds (optional, not implemented)

        """
        if self.backend == "file":
            self._cache[key] = value
            logger.warning(f"Secret stored in memory only (not persisted): {key}")
        else:
            logger.warning(f"Secret storage not supported for backend: {self.backend}")

    def add_trusted_host(self, hostname: str):
        """Adds a trusted Git host to the whitelist.

        Use with caution - only add hosts you fully control.

        Args:
            hostname: Exact hostname (e.g., "gitlab.company.com")

        Security:
            - Only add exact hostnames, no wildcards
            - Validate hostname format before adding

        """
        hostname_lower = hostname.lower()

        # Basic validation
        if not hostname_lower or "." not in hostname_lower:
            logger.error(f"Invalid hostname format: {hostname}")
            return

        self.TRUSTED_GIT_HOSTS.add(hostname_lower)
        logger.info(f"Added trusted Git host: {hostname_lower}")


_secret_manager: SecretManager | None = None


def get_secret_manager(backend: str | None = None) -> SecretManager:
    """Returns the global SecretManager instance."""
    global _secret_manager  # noqa: PLW0603
    if _secret_manager is None:
        _backend = backend or os.getenv("VIGILCD_SECRET_BACKEND", "env")  # type: ignore[assignment]
        _secret_manager = SecretManager(backend=_backend)  # type: ignore[arg-type]
    return _secret_manager

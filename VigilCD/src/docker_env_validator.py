"""Docker Compose Environment Validation Module."""

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class EnvValidationError(Exception):
    """Exception for environment validation errors."""

    pass


class DockerComposeEnvValidator:
    """Validates environment requirements for Docker Compose files."""

    # Regex patterns für verschiedene Env-Variable Syntaxen
    # Pattern für ${VAR:-default} - Variablen MIT Default (optional)
    ENV_VAR_WITH_DEFAULT = re.compile(r"\$\{([A-Z0-9_]+):-[^}]+\}")

    # Patterns für ${VAR} und $VAR - Variablen OHNE Default (required)
    ENV_VAR_PATTERNS = [
        re.compile(r"\$\{([A-Z0-9_]+)\}"),  # ${VAR} (ohne Default)
        re.compile(r"\$([A-Z0-9_]+)"),  # $VAR
    ]

    def __init__(self, compose_file_path: str, working_dir: str):
        """Initialize validator.

        Args:
            compose_file_path: Path to docker-compose.yml (relative or absolute)
            working_dir: Working directory (repo path)
        """
        self.working_dir = Path(working_dir)
        self.compose_file = self.working_dir / compose_file_path

        if not self.compose_file.exists():
            raise EnvValidationError(f"Compose file not found: {self.compose_file}")

    def validate(self) -> tuple[bool, list[str]]:
        """Validate environment configuration.

        Returns:
            (is_valid, warnings): True if valid, list of warning messages
        """
        warnings = []

        try:
            # 1. Parse docker-compose.yml
            compose_config = self._load_compose_file()

            # 2. Check for env_file references
            env_file_warnings = self._check_env_files(compose_config)
            warnings.extend(env_file_warnings)

            # 3. Extract required environment variables
            required_vars = self._extract_required_env_vars(compose_config)

            # 4. Check if required vars are available
            missing_vars = self._check_missing_vars(required_vars)

            if missing_vars:
                warnings.append(f"Missing environment variables: {', '.join(sorted(missing_vars))}")

            # Validation fails if we have warnings
            is_valid = len(warnings) == 0

            return is_valid, warnings

        except Exception as e:
            logger.exception(f"Error during env validation: {e}")
            return False, [f"Validation error: {str(e)}"]

    def _load_compose_file(self) -> dict[str, Any]:
        """Load and parse docker-compose.yml.

        Returns:
            Parsed YAML content
        """
        try:
            with open(self.compose_file) as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise EnvValidationError(f"Invalid YAML in compose file: {e}") from e
        except Exception as e:
            raise EnvValidationError(f"Failed to load compose file: {e}") from e

    def _check_env_files(self, compose_config: dict) -> list[str]:
        """Check if referenced .env files exist.

        Args:
            compose_config: Parsed docker-compose.yml

        Returns:
            List of warning messages
        """
        warnings = []
        env_files = set()

        # Global env_file (top-level, rare but possible with some compose versions)
        if "env_file" in compose_config:
            env_files.update(self._normalize_env_file_list(compose_config["env_file"]))

        # Service-level env_file
        services = compose_config.get("services", {})
        for _service_name, service_config in services.items():
            if isinstance(service_config, dict) and "env_file" in service_config:
                service_env_files = self._normalize_env_file_list(service_config["env_file"])
                env_files.update(service_env_files)

        # Check if files exist
        for env_file in env_files:
            env_file_path = self.working_dir / env_file
            if not env_file_path.exists():
                warnings.append(
                    f"Referenced env_file not found: {env_file} (expected at: {env_file_path})"
                )
                logger.warning(f"Missing env_file: {env_file_path}")

        return warnings

    @staticmethod
    def _normalize_env_file_list(env_file_value: Any) -> list[str]:
        """Normalize env_file value to list of strings.

        env_file can be:
        - string: "path/to/.env"
        - list: ["path/to/.env", "another.env"]

        Args:
            env_file_value: Value from docker-compose.yml

        Returns:
            List of env file paths
        """
        if isinstance(env_file_value, str):
            return [env_file_value]
        if isinstance(env_file_value, list):
            return [str(f) for f in env_file_value]
        return []

    def _extract_required_env_vars(self, compose_config: dict) -> set[str]:
        """Extract all environment variables referenced in compose file.

        Searches for variables in:
        - environment: sections
        - command: fields
        - Other string fields that might contain ${VAR}

        Args:
            compose_config: Parsed docker-compose.yml

        Returns:
            Set of required environment variable names
        """
        required_vars: set[str] = set()

        # Recursive search through entire config
        self._search_env_vars_recursive(compose_config, required_vars)

        return required_vars

    def _search_env_vars_recursive(self, obj: Any, required_vars: set[str]) -> None:
        """Recursively search for environment variables in config.

        Args:
            obj: Current object to search (dict, list, str, etc.)
            required_vars: Set to collect found variables
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                # Check environment section specially
                if key == "environment" and isinstance(value, dict):
                    for env_value in value.values():
                        if isinstance(env_value, str):
                            self._extract_vars_from_string(env_value, required_vars)
                else:
                    self._search_env_vars_recursive(value, required_vars)

        elif isinstance(obj, list):
            for item in obj:
                self._search_env_vars_recursive(item, required_vars)

        elif isinstance(obj, str):
            self._extract_vars_from_string(obj, required_vars)

    def _extract_vars_from_string(self, text: str, required_vars: set[str]) -> None:
        """Extract variable names from a string using regex patterns.

        Args:
            text: String to search
            required_vars: Set to add found variables to
        """
        for pattern in self.ENV_VAR_PATTERNS:
            matches = pattern.findall(text)
            required_vars.update(matches)

    def _check_missing_vars(self, required_vars: set[str]) -> set[str]:
        """Check which required variables are missing.

        Checks against:
        1. System environment variables
        2. .env file in working directory (if exists)

        Args:
            required_vars: Set of required variable names

        Returns:
            Set of missing variable names
        """
        available_vars = set(os.environ.keys())

        # Load .env file if it exists (Docker Compose default behavior)
        default_env_file = self.working_dir / ".env"
        if default_env_file.exists():
            env_file_vars = self._load_env_file(default_env_file)
            available_vars.update(env_file_vars.keys())

        missing = required_vars - available_vars

        # Filter out variables with defaults (${VAR:-default})
        # These won't cause errors even if missing
        # Note: Our regex already strips the default part, so we detect them differently
        return missing

    @staticmethod
    def _load_env_file(env_file_path: Path) -> dict[str, str]:
        """Load variables from .env file.

        Args:
            env_file_path: Path to .env file

        Returns:
            Dict of variable name -> value
        """
        env_vars = {}

        try:
            with open(env_file_path) as f:
                for raw_line in f:
                    line = raw_line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Parse KEY=VALUE
                    if "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()

        except Exception as e:
            logger.warning(f"Failed to load .env file {env_file_path}: {e}")

        return env_vars


def validate_docker_compose_env(compose_file: str, working_dir: str) -> tuple[bool, list[str]]:
    """Convenience function to validate Docker Compose environment.

    Args:
        compose_file: Path to docker-compose.yml (relative to working_dir)
        working_dir: Working directory (repo path)

    Returns:
        (is_valid, warnings): Validation result and warning messages
    """
    try:
        validator = DockerComposeEnvValidator(compose_file, working_dir)
        return validator.validate()
    except EnvValidationError as e:
        logger.error(f"Environment validation failed: {e}")
        return False, [str(e)]

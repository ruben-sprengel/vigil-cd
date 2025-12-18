"""Unit tests for Docker Compose Environment Validator."""

import pytest

from src.docker_env_validator import DockerComposeEnvValidator, EnvValidationError

# temp_repo fixture is now in conftest.py (module-scoped with per-test subdirs)


def test_missing_compose_file(temp_repo):
    """Test validation fails if compose file doesn't exist."""
    with pytest.raises(EnvValidationError, match="Compose file not found"):
        DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))


def test_valid_simple_compose(temp_repo):
    """Test validation passes for simple compose without env requirements."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx:latest
    ports:
      - "80:80"
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert is_valid
    assert len(warnings) == 0


def test_missing_env_file_reference(temp_repo):
    """Test validation fails when referenced .env file doesn't exist."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    env_file: .env
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert not is_valid
    assert len(warnings) == 1
    assert ".env" in warnings[0]
    assert "not found" in warnings[0]


def test_env_file_exists(temp_repo):
    """Test validation passes when referenced .env file exists."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    env_file: .env
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    # Create .env file
    env_file = temp_repo / ".env"
    env_file.write_text("MY_VAR=value\n")

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert is_valid
    assert len(warnings) == 0


def test_multiple_env_files(temp_repo):
    """Test validation with multiple env_file references."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    env_file:
      - .env
      - .env.local
      - config/.env.prod
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    # Create only one of three files
    env_file = temp_repo / ".env"
    env_file.write_text("VAR=value\n")

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert not is_valid
    assert len(warnings) == 2  # Two missing files
    assert any(".env.local" in w for w in warnings)
    assert any("config/.env.prod" in w for w in warnings)


def test_missing_environment_variable(temp_repo):
    """Test validation fails for missing environment variables."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - API_KEY=${API_KEY}
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert not is_valid
    assert len(warnings) == 1
    assert "DATABASE_URL" in warnings[0]
    assert "API_KEY" in warnings[0]


def test_environment_variable_from_env_file(temp_repo):
    """Test validation passes when variables are in .env file."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    environment:
      - DATABASE_URL=${DATABASE_URL}
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    # Variable defined in .env
    env_file = temp_repo / ".env"
    env_file.write_text("DATABASE_URL=postgres://localhost/db\n")

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert is_valid
    assert len(warnings) == 0


def test_environment_variable_from_system(temp_repo, monkeypatch):
    """Test validation passes when variables are in system environment."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    environment:
      - API_KEY=${API_KEY}
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    # Set in system environment
    monkeypatch.setenv("API_KEY", "test-key")

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert is_valid
    assert len(warnings) == 0


def test_variable_with_default_value(temp_repo):
    """Test validation passes for variables with default values."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    environment:
      - LOG_LEVEL=${LOG_LEVEL:-info}
      - DEBUG=${DEBUG:-false}
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    # Variables with defaults should NOT be required
    assert is_valid
    assert len(warnings) == 0


def test_mixed_required_and_optional_variables(temp_repo):
    """Test validation with both required and optional (with default) variables."""
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx
    environment:
      - DATABASE_URL=${DATABASE_URL}           # Required (no default)
      - LOG_LEVEL=${LOG_LEVEL:-info}           # Optional (has default)
      - API_KEY=${API_KEY}                     # Required (no default)
      - DEBUG=${DEBUG:-false}                  # Optional (has default)
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    # Should fail because of required variables
    assert not is_valid
    assert len(warnings) == 1

    # Check only required variables are reported
    assert "DATABASE_URL" in warnings[0]
    assert "API_KEY" in warnings[0]

    # Optional variables with defaults should NOT be reported
    assert "LOG_LEVEL" not in warnings[0]
    assert "DEBUG" not in warnings[0]


@pytest.mark.parametrize(
    "compose_content,expected_vars",
    [
        # Variables in command
        (
            """
version: '3.8'
services:
  app:
    image: nginx
    command: python manage.py --host ${DB_HOST} --port ${DB_PORT}
""",
            ["DB_HOST", "DB_PORT"],
        ),
        # Variables in image tag
        (
            """
version: '3.8'
services:
  app:
    image: myapp:${VERSION}
""",
            ["VERSION"],
        ),
        # Variables in environment dict format
        (
            """
version: '3.8'
services:
  app:
    image: nginx
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
""",
            ["DATABASE_URL", "REDIS_URL"],
        ),
        # Variables in volumes
        (
            """
version: '3.8'
services:
  app:
    image: nginx
    volumes:
      - ${DATA_DIR}:/data
""",
            ["DATA_DIR"],
        ),
    ],
    ids=["command", "image_tag", "env_dict", "volumes"],
)
def test_variable_detection_locations(temp_repo, compose_content, expected_vars):
    """Test detection of variables in different locations using parametrize."""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert not is_valid
    for var in expected_vars:
        assert var in warnings[0]


@pytest.mark.parametrize(
    "env_files,create_files,expected_missing",
    [
        # Single missing file
        ([".env"], [], [".env"]),
        # Multiple files, all missing
        ([".env", ".env.local"], [], [".env", ".env.local"]),
        # Multiple files, one exists
        ([".env", ".env.local"], [".env"], [".env.local"]),
        # Multiple files, all exist
        ([".env", ".env.local"], [".env", ".env.local"], []),
        # Nested path
        (["config/.env.prod"], [], ["config/.env.prod"]),
    ],
    ids=["single_missing", "all_missing", "one_exists", "all_exist", "nested_path"],
)
def test_env_file_validation_parametrized(temp_repo, env_files, create_files, expected_missing):
    """Test env_file validation with various configurations."""
    env_file_list = "\n".join(f"      - {f}" for f in env_files)
    compose_content = f"""
version: '3.8'
services:
  app:
    image: nginx
    env_file:
{env_file_list}
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    # Create specified files
    for file_path in create_files:
        file_obj = temp_repo / file_path
        file_obj.parent.mkdir(parents=True, exist_ok=True)
        file_obj.write_text("VAR=value\n")

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    if expected_missing:
        assert not is_valid
        for missing_file in expected_missing:
            assert any(missing_file in w for w in warnings)
    else:
        assert is_valid
        assert len(warnings) == 0


def test_complex_scenario(temp_repo, monkeypatch):
    """Test complex scenario with multiple validation aspects."""
    compose_content = """
version: '3.8'
services:
  web:
    image: webapp:${VERSION}
    env_file:
      - .env
      - .env.prod
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - API_KEY=${API_KEY}
      - LOG_LEVEL=${LOG_LEVEL:-info}
  worker:
    image: worker:latest
    environment:
      - REDIS_URL=${REDIS_URL}
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    # Create .env with some variables
    env_file = temp_repo / ".env"
    env_file.write_text("DATABASE_URL=postgres://localhost/db\n")

    # Set some in system
    monkeypatch.setenv("VERSION", "1.0.0")
    monkeypatch.setenv("API_KEY", "key")

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert not is_valid
    # Should have warnings for:
    # - Missing .env.prod file
    # - Missing REDIS_URL variable
    assert len(warnings) >= 2
    assert any(".env.prod" in w for w in warnings)
    assert any("REDIS_URL" in w for w in warnings)


def test_invalid_yaml(temp_repo):
    """Test handling of invalid YAML."""
    compose_content = """
this is not: valid: yaml: content
  - broken
    indentation
"""
    compose_file = temp_repo / "docker-compose.yml"
    compose_file.write_text(compose_content)

    validator = DockerComposeEnvValidator("docker-compose.yml", str(temp_repo))
    is_valid, warnings = validator.validate()

    assert not is_valid
    assert any("YAML" in w or "parse" in w.lower() for w in warnings)

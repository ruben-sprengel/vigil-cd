"""Unit tests for Config Manager."""

import pytest
import yaml

from src.config_manager import ConfigManager, DeploymentConfig, LoggingConfig, SchedulingConfig


def test_load_valid_config(temp_config_dir, basic_config_content):
    """Test loading a valid configuration file."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    config_manager = ConfigManager(str(config_file))

    assert len(config_manager.repos_config) == 1
    assert config_manager.repos_config[0].name == "test-repo"
    assert config_manager.scheduling.check_interval_minutes == 1
    assert config_manager.deployment.docker_compose_timeout_seconds == 300.0


def test_config_file_not_found(temp_config_dir):
    """Test error handling when config file doesn't exist."""
    config_file = temp_config_dir / "nonexistent.yaml"

    with pytest.raises(FileNotFoundError):
        ConfigManager(str(config_file))


def test_invalid_yaml(temp_config_dir):
    """Test error handling for invalid YAML syntax."""
    config_file = temp_config_dir / "config.yaml"
    config_file.write_text("invalid: yaml: syntax:\n  - broken\n    indentation")

    with pytest.raises(yaml.YAMLError):
        ConfigManager(str(config_file))


def test_empty_config_file(temp_config_dir):
    """Test handling of empty config file."""
    config_file = temp_config_dir / "config.yaml"
    config_file.write_text("")

    config_manager = ConfigManager(str(config_file))

    assert config_manager.repos_config == []
    assert config_manager.scheduling.check_interval_minutes == 1


def test_missing_repos_key(temp_config_dir):
    """Test handling of config without 'repos' key."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump({"other_key": "value"}, f)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.repos_config == []


def test_repos_not_a_list(temp_config_dir):
    """Test handling of invalid 'repos' type (not a list)."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump({"repos": "not-a-list"}, f)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.repos_config == []


@pytest.mark.parametrize(
    "env_var,value,expected_attr,expected_value",
    [
        ("VIGILCD_CHECK_INTERVAL_MINUTES", "5", "scheduling.check_interval_minutes", 5),
        ("VIGILCD_GIT_RETRY_COUNT", "10", "scheduling.git_retry_count", 10),
        ("VIGILCD_RETRY_BACKOFF_FACTOR", "3.5", "scheduling.retry_backoff_factor", 3.5),
        ("VIGILCD_DOCKER_TIMEOUT", "600.0", "deployment.docker_compose_timeout_seconds", 600.0),
        ("VIGILCD_GIT_TIMEOUT", "120.5", "deployment.git_operation_timeout_seconds", 120.5),
        (
            "VIGILCD_DOCKER_DAEMON_TIMEOUT",
            "20",
            "deployment.docker_daemon_timeout_seconds",
            20.0,
        ),
        ("VIGILCD_LOG_LEVEL", "debug", "logging_config.level", "DEBUG"),
        ("VIGILCD_LOG_FORMAT", "TEXT", "logging_config.format", "text"),
    ],
    ids=[
        "check_interval",
        "git_retry_count",
        "backoff_factor",
        "docker_timeout",
        "git_timeout",
        "daemon_timeout",
        "log_level",
        "log_format",
    ],
)
def test_env_overrides(
    temp_config_dir,
    basic_config_content,
    monkeypatch,
    env_var,
    value,
    expected_attr,
    expected_value,
):
    """Test environment variable overrides using parametrize."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    monkeypatch.setenv(env_var, value)

    config_manager = ConfigManager(str(config_file))

    # Navigate nested attributes (e.g., "scheduling.check_interval_minutes")
    obj = config_manager
    attrs = expected_attr.split(".")
    for attr in attrs:
        obj = getattr(obj, attr)

    assert obj == expected_value


@pytest.mark.parametrize(
    "timeout_value,expected",
    [
        ("none", None),
        ("null", None),
        ("None", None),
        ("NULL", None),
        ("", None),
        ("30", 30.0),
        ("30.5", 30.5),
        ("0.1", 0.1),
        ("1000", 1000.0),
    ],
    ids=["none", "null", "None", "NULL", "empty", "int", "float", "small", "large"],
)
def test_timeout_parsing(
    temp_config_dir, basic_config_content, monkeypatch, timeout_value, expected
):
    """Test timeout value parsing from environment variables."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    monkeypatch.setenv("VIGILCD_DOCKER_TIMEOUT", timeout_value)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.deployment.docker_compose_timeout_seconds == expected


def test_invalid_timeout_value(temp_config_dir, basic_config_content, monkeypatch):
    """Test error handling for invalid timeout values."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    monkeypatch.setenv("VIGILCD_DOCKER_TIMEOUT", "invalid")

    with pytest.raises(ValueError, match="Invalid timeout value"):
        ConfigManager(str(config_file))


def test_negative_timeout_validation():
    """Test validation rejects negative timeout values."""
    with pytest.raises(ValueError, match="Timeout must be positive"):
        DeploymentConfig(docker_compose_timeout_seconds=-10.0)


def test_zero_timeout_validation():
    """Test validation rejects zero timeout values."""
    with pytest.raises(ValueError, match="Timeout must be positive"):
        DeploymentConfig(docker_daemon_timeout_seconds=0)


def test_none_timeout_allowed():
    """Test that None is allowed as timeout value (no timeout)."""
    config = DeploymentConfig(
        docker_compose_timeout_seconds=None,
        git_operation_timeout_seconds=None,
        docker_daemon_timeout_seconds=None,
    )

    assert config.docker_compose_timeout_seconds is None
    assert config.git_operation_timeout_seconds is None
    assert config.docker_daemon_timeout_seconds is None


def test_invalid_check_interval(temp_config_dir, basic_config_content, monkeypatch):
    """Test validation rejects check_interval < 1."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    monkeypatch.setenv("VIGILCD_CHECK_INTERVAL_MINUTES", "0")

    with pytest.raises(ValueError, match="check_interval_minutes muss >= 1 sein"):
        ConfigManager(str(config_file))


def test_get_ssh_key_path(temp_config_dir, basic_config_content, monkeypatch):
    """Test retrieving SSH key path from environment."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    ssh_key_path = "/path/to/ssh/key"
    monkeypatch.setenv("VIGILCD_SSH_KEY_PATH", ssh_key_path)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.get_ssh_key_path() == ssh_key_path


def test_get_ssh_key_path_not_set(temp_config_dir, basic_config_content):
    """Test retrieving SSH key path when not set."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.get_ssh_key_path() is None


def test_get_github_token(temp_config_dir, basic_config_content, monkeypatch):
    """Test retrieving GitHub token from environment."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    token = "ghp_test_token_123456"
    monkeypatch.setenv("VIGILCD_GITHUB_TOKEN", token)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.get_github_token() == token


def test_get_github_token_not_set(temp_config_dir, basic_config_content):
    """Test retrieving GitHub token when not set."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.get_github_token() is None


def test_get_webhook_secret(temp_config_dir, basic_config_content, monkeypatch):
    """Test retrieving webhook secret from environment."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    secret = "my-webhook-secret-123"
    monkeypatch.setenv("VIGILCD_GITHUB_WEBHOOK_SECRET", secret)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.get_webhook_secret() == secret


def test_get_webhook_secret_not_set(temp_config_dir, basic_config_content):
    """Test retrieving webhook secret when not set."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    config_manager = ConfigManager(str(config_file))

    assert config_manager.get_webhook_secret() is None


def test_get_all_settings(temp_config_dir, basic_config_content):
    """Test get_all_settings returns non-sensitive configuration."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    config_manager = ConfigManager(str(config_file))
    settings = config_manager.get_all_settings()

    assert "scheduling" in settings
    assert "deployment" in settings
    assert "logging" in settings
    assert "repos_count" in settings
    assert settings["repos_count"] == 1

    # Check structure
    assert settings["scheduling"]["check_interval_minutes"] == 1
    assert settings["deployment"]["docker_compose_timeout_seconds"] == 300.0
    assert settings["logging"]["level"] == "INFO"


def test_to_dict(temp_config_dir, basic_config_content):
    """Test to_dict returns full configuration."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    config_manager = ConfigManager(str(config_file))
    config_dict = config_manager.to_dict()

    assert "scheduling" in config_dict
    assert "deployment" in config_dict
    assert "logging" in config_dict
    assert "repos" in config_dict
    assert len(config_dict["repos"]) == 1


def test_scheduling_config_defaults():
    """Test SchedulingConfig default values."""
    config = SchedulingConfig()

    assert config.check_interval_minutes == 1
    assert config.git_retry_count == 3
    assert config.retry_backoff_factor == 2.0


def test_deployment_config_defaults():
    """Test DeploymentConfig default values."""
    config = DeploymentConfig()

    assert config.docker_compose_timeout_seconds == 300.0
    assert config.git_operation_timeout_seconds == 60.0
    assert config.docker_daemon_timeout_seconds == 10.0


def test_logging_config_defaults():
    """Test LoggingConfig default values."""
    config = LoggingConfig()

    assert config.level == "INFO"
    assert config.format == "json"


def test_multiple_repos(temp_config_dir):
    """Test configuration with multiple repositories."""
    config_content = {
        "repos": [
            {
                "name": "repo1",
                "url": "https://github.com/user/repo1",
                "auth_method": "https",
                "branches": [{"name": "main", "sync_enabled": True, "targets": []}],
            },
            {
                "name": "repo2",
                "url": "git@//github.com/user/repo2",
                "auth_method": "ssh",
                "branches": [{"name": "develop", "sync_enabled": True, "targets": []}],
            },
            {
                "name": "repo3",
                "url": "https://github.com/user/repo3",
                "auth_method": "https",
                "branches": [{"name": "staging", "sync_enabled": False, "targets": []}],
            },
        ]
    }

    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    config_manager = ConfigManager(str(config_file))

    assert len(config_manager.repos_config) == 3
    assert config_manager.repos_config[0].name == "repo1"
    assert config_manager.repos_config[1].name == "repo2"
    assert config_manager.repos_config[2].name == "repo3"


def test_complex_env_overrides(temp_config_dir, basic_config_content, monkeypatch):
    """Test multiple environment variable overrides simultaneously."""
    config_file = temp_config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(basic_config_content, f)

    # Set multiple env vars
    monkeypatch.setenv("VIGILCD_CHECK_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("VIGILCD_GIT_RETRY_COUNT", "5")
    monkeypatch.setenv("VIGILCD_DOCKER_TIMEOUT", "none")
    monkeypatch.setenv("VIGILCD_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("VIGILCD_SSH_KEY_PATH", "/custom/path/id_rsa")

    config_manager = ConfigManager(str(config_file))

    assert config_manager.scheduling.check_interval_minutes == 10
    assert config_manager.scheduling.git_retry_count == 5
    assert config_manager.deployment.docker_compose_timeout_seconds is None
    assert config_manager.logging_config.level == "WARNING"
    assert config_manager.get_ssh_key_path() == "/custom/path/id_rsa"

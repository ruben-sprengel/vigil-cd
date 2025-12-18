"""Unit tests for Deployment Service."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from git import GitCommandError

from src.config_manager import ConfigManager
from src.models import BranchConfig, ComposeTarget, RegistryConfig, RepoConfig
from src.service import (
    DeploymentError,
    DeploymentService,
    DockerConfig,
    GitOperationError,
)


@pytest.fixture
def temp_config_file():
    """Create a temporary config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_path.write_text("""
repos:
  - name: test-repo
    url: https://github.com/user/test-repo
    auth_method: https
    branches:
      - name: main
        sync_enabled: true
        targets:
          - name: srv
            file: docker-compose.yml
            deploy: true
""")
        yield str(config_path)


@pytest.fixture
def config_manager(temp_config_file):
    """Create ConfigManager with test config."""
    return ConfigManager(config_file=temp_config_file)


@pytest.fixture
def deployment_service(config_manager):
    """Create DeploymentService instance."""
    return DeploymentService(config_manager=config_manager)


@pytest.fixture
def sample_repo_config():
    """Create sample RepoConfig."""
    return RepoConfig(
        name="test-repo",
        url="https://github.com/user/test-repo",
        auth_method="https",
        branches=[
            BranchConfig(
                name="main",
                sync_enabled=True,
                targets=[ComposeTarget(name="srv", file="docker-compose.yml", deploy=True)],
            )
        ],
    )


@pytest.fixture
def sample_branch_config():
    """Create sample BranchConfig."""
    return BranchConfig(
        name="main",
        sync_enabled=True,
        targets=[ComposeTarget(name="srv", file="docker-compose.yml", deploy=True)],
    )


@pytest.fixture
def sample_target():
    """Create sample ComposeTarget."""
    return ComposeTarget(name="srv", file="docker-compose.yml", deploy=True)


# ==================== DockerConfig Tests ====================


@patch.dict(os.environ, {}, clear=True)
@patch("os.path.exists")
@patch("platform.system")
def test_docker_config_linux_with_socket(mock_system, mock_exists):
    """Test DockerConfig detects Linux with socket."""
    mock_system.return_value = "Linux"
    mock_exists.return_value = True

    result = DockerConfig.get_docker_host()

    assert result == "unix:///var/run/docker.sock"


@patch.dict(os.environ, {}, clear=True)
@patch("os.path.exists")
@patch("platform.system")
def test_docker_config_linux_without_socket(mock_system, mock_exists):
    """Test DockerConfig falls back when socket missing."""
    mock_system.return_value = "Linux"
    mock_exists.return_value = False

    result = DockerConfig.get_docker_host()

    assert result == "unix:///var/run/docker.sock"


@patch.dict(os.environ, {}, clear=True)
@patch("platform.system")
def test_docker_config_windows_named_pipe(mock_system):
    """Test DockerConfig uses named pipe on Windows."""
    mock_system.return_value = "Windows"

    result = DockerConfig.get_docker_host()

    assert result == "npipe://./pipe/docker_engine"


@patch.dict(os.environ, {"VIGILCD_LOCAL_WINDOWS_TCP": "1"}, clear=True)
@patch("platform.system")
def test_docker_config_windows_tcp(mock_system):
    """Test DockerConfig uses TCP on Windows when env var set."""
    mock_system.return_value = "Windows"

    result = DockerConfig.get_docker_host()

    assert result == "tcp://127.0.0.1:2375"


@patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote-host:2376"}, clear=True)
def test_docker_config_from_env():
    """Test DockerConfig uses DOCKER_HOST from environment."""
    result = DockerConfig.get_docker_host()

    assert result == "tcp://remote-host:2376"


# ==================== DeploymentService Init Tests ====================


def test_deployment_service_init_with_config_manager(config_manager):
    """Test DeploymentService initialization with ConfigManager."""
    service = DeploymentService(config_manager=config_manager)

    assert service.config is config_manager
    assert service.docker_host is not None


def test_deployment_service_init_without_config_manager(temp_config_file, monkeypatch):
    """Test DeploymentService initialization without ConfigManager."""
    monkeypatch.setenv("CONFIG_PATH", temp_config_file)

    service = DeploymentService(config_manager=None)

    assert service.config is not None
    assert isinstance(service.config, ConfigManager)


# ==================== _get_executable_path Tests ====================


def test_get_executable_path_found():
    """Test finding executable that exists."""
    path = DeploymentService._get_executable_path("python")

    assert path is not None
    assert "python" in path.lower()


def test_get_executable_path_not_found():
    """Test error when executable not found."""
    with pytest.raises(DeploymentError, match="not found in PATH"):
        DeploymentService._get_executable_path("nonexistent-command-12345")


@pytest.mark.parametrize(
    "command",
    ["python", "git", "docker"],
    ids=["python", "git", "docker"],
)
def test_get_executable_path_various_commands(command):
    """Test finding various common executables."""
    try:
        path = DeploymentService._get_executable_path(command)
        assert path is not None
        assert command in path.lower()
    except DeploymentError:
        # Command might not be installed in test environment
        pytest.skip(f"{command} not available in test environment")


# ==================== _get_git_env Tests ====================


def test_get_git_env_https(deployment_service, sample_repo_config):
    """Test Git environment for HTTPS auth."""
    sample_repo_config.auth_method = "https"

    env = deployment_service._get_git_env(sample_repo_config)

    assert "GIT_SSH_COMMAND" not in env


def test_get_git_env_ssh_with_key(deployment_service, sample_repo_config, tmp_path):
    """Test Git environment for SSH auth with key."""
    ssh_key = tmp_path / "id_rsa"
    ssh_key.write_text("fake-key")

    sample_repo_config.auth_method = "ssh"
    sample_repo_config.ssh_key_path = str(ssh_key)

    env = deployment_service._get_git_env(sample_repo_config)

    assert "GIT_SSH_COMMAND" in env
    assert str(ssh_key) in env["GIT_SSH_COMMAND"]


def test_get_git_env_ssh_no_key(deployment_service, sample_repo_config):
    """Test Git environment for SSH auth without key raises error."""
    sample_repo_config.auth_method = "ssh"
    sample_repo_config.ssh_key_path = None

    with pytest.raises(GitOperationError, match="requires ssh_key_path"):
        deployment_service._get_git_env(sample_repo_config)


def test_get_git_env_ssh_key_not_exists(deployment_service, sample_repo_config):
    """Test Git environment for SSH auth with non-existent key."""
    sample_repo_config.auth_method = "ssh"
    sample_repo_config.ssh_key_path = "/nonexistent/key"

    with pytest.raises(GitOperationError, match="SSH key not found"):
        deployment_service._get_git_env(sample_repo_config)


# ==================== is_docker_daemon_running Tests ====================


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
def test_is_docker_daemon_running_success(mock_exec, mock_run, deployment_service):
    """Test Docker daemon running check succeeds."""
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.return_value = Mock(returncode=0)

    result = deployment_service.is_docker_daemon_running()

    assert result is True
    mock_run.assert_called_once()


@patch.object(DeploymentService, "_get_executable_path")
def test_is_docker_daemon_running_docker_not_found(mock_exec, deployment_service):
    """Test Docker daemon check when docker not installed."""
    mock_exec.side_effect = DeploymentError("Docker not found")

    result = deployment_service.is_docker_daemon_running()

    assert result is False


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
def test_is_docker_daemon_running_daemon_error(mock_exec, mock_run, deployment_service):
    """Test Docker daemon check when daemon not running."""
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.side_effect = subprocess.CalledProcessError(1, "docker", stderr="Cannot connect")

    result = deployment_service.is_docker_daemon_running()

    assert result is False


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
def test_is_docker_daemon_running_timeout(mock_exec, mock_run, deployment_service):
    """Test Docker daemon check timeout."""
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.side_effect = subprocess.TimeoutExpired("docker", 10)

    result = deployment_service.is_docker_daemon_running()

    assert result is False


# ==================== _retry_with_backoff Tests ====================


def test_retry_with_backoff_success_first_try(deployment_service):
    """Test retry succeeds on first attempt."""
    mock_func = Mock(return_value="success")

    result = deployment_service._retry_with_backoff(mock_func)

    assert result == "success"
    assert mock_func.call_count == 1


def test_retry_with_backoff_success_after_retries(deployment_service):
    """Test retry succeeds after failures."""
    mock_func = Mock(side_effect=[GitOperationError("fail"), GitOperationError("fail"), "success"])

    result = deployment_service._retry_with_backoff(mock_func, max_retries=3)

    assert result == "success"
    assert mock_func.call_count == 3


def test_retry_with_backoff_max_retries_exceeded(deployment_service):
    """Test retry fails after max attempts."""
    mock_func = Mock(side_effect=GitOperationError("persistent failure"))

    with pytest.raises(GitOperationError, match="persistent failure"):
        deployment_service._retry_with_backoff(mock_func, max_retries=3)

    assert mock_func.call_count == 3


@pytest.mark.parametrize(
    "exception_type",
    [GitOperationError, GitCommandError],
    ids=["GitOperationError", "GitCommandError"],
)
def test_retry_with_backoff_exception_types(deployment_service, exception_type):
    """Test retry handles different exception types."""
    mock_func = Mock(side_effect=[exception_type("error"), "success"])

    result = deployment_service._retry_with_backoff(mock_func, max_retries=2)

    assert result == "success"
    assert mock_func.call_count == 2


# ==================== docker_login_registries Tests ====================


def test_docker_login_no_registries(deployment_service):
    """Test Docker login with no registries configured."""
    result = deployment_service.docker_login_registries(None)

    assert result is True


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
def test_docker_login_public_registry(mock_exec, mock_run, deployment_service):
    """Test Docker login skips public registries."""
    mock_exec.return_value = "/usr/bin/docker"
    registries = [RegistryConfig(url="docker.io")]

    result = deployment_service.docker_login_registries(registries)

    assert result is True
    mock_run.assert_not_called()


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
@patch.dict(os.environ, {"GHCR_TOKEN": "test-token"})
def test_docker_login_private_registry_success(mock_exec, mock_run, deployment_service):
    """Test Docker login to private registry succeeds."""
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.return_value = Mock(returncode=0)
    registries = [RegistryConfig(url="ghcr.io", username="user", password_env_var="GHCR_TOKEN")]

    result = deployment_service.docker_login_registries(registries)

    assert result is True
    mock_run.assert_called_once()


@patch.object(DeploymentService, "_get_executable_path")
def test_docker_login_docker_not_found(mock_exec, deployment_service):
    """Test Docker login when docker not installed."""
    mock_exec.side_effect = DeploymentError("Docker not found")
    registries = [RegistryConfig(url="ghcr.io", username="user", password_env_var="GHCR_TOKEN")]

    result = deployment_service.docker_login_registries(registries)

    assert result is False


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
def test_docker_login_password_not_set(mock_exec, mock_run, deployment_service):
    """Test Docker login fails when password env var not set."""
    mock_exec.return_value = "/usr/bin/docker"
    registries = [RegistryConfig(url="ghcr.io", username="user", password_env_var="MISSING_TOKEN")]

    result = deployment_service.docker_login_registries(registries)

    assert result is False
    mock_run.assert_not_called()


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
@patch.dict(os.environ, {"GHCR_TOKEN": "test-token"})
def test_docker_login_command_fails(mock_exec, mock_run, deployment_service):
    """Test Docker login handles command failure."""
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.side_effect = subprocess.CalledProcessError(1, "docker", stderr="Login failed")
    registries = [RegistryConfig(url="ghcr.io", username="user", password_env_var="GHCR_TOKEN")]

    result = deployment_service.docker_login_registries(registries)

    assert result is False


# ==================== docker_logout_registries Tests ====================


def test_docker_logout_no_registries(deployment_service):
    """Test Docker logout with no registries."""
    # Should not raise error
    deployment_service.docker_logout_registries(None)


@patch.object(DeploymentService, "_get_executable_path")
def test_docker_logout_docker_not_found(mock_exec, deployment_service):
    """Test Docker logout when docker not installed."""
    mock_exec.side_effect = DeploymentError("Docker not found")
    registries = [RegistryConfig(url="ghcr.io", username="user")]

    # Should not raise error, just warn
    deployment_service.docker_logout_registries(registries)


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
def test_docker_logout_success(mock_exec, mock_run, deployment_service):
    """Test Docker logout succeeds."""
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.return_value = Mock(returncode=0)
    registries = [RegistryConfig(url="ghcr.io", username="user")]

    deployment_service.docker_logout_registries(registries)

    mock_run.assert_called_once()


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
def test_docker_logout_continues_on_failure(mock_exec, mock_run, deployment_service):
    """Test Docker logout continues even if individual logout fails."""
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.side_effect = [
        Mock(returncode=1, stderr="Failed"),  # First fails
        Mock(returncode=0),  # Second succeeds
    ]
    registries = [
        RegistryConfig(url="ghcr.io", username="user1"),
        RegistryConfig(url="docker.io", username="user2"),
    ]

    # Should not raise error
    deployment_service.docker_logout_registries(registries)

    assert mock_run.call_count == 2


# ==================== ensure_repo Tests ====================


@patch("os.path.exists")
def test_ensure_repo_already_exists(
    mock_exists, deployment_service, sample_repo_config, sample_branch_config
):
    """Test ensure_repo when repository already exists."""
    mock_exists.return_value = True

    is_new, repo_path = deployment_service.ensure_repo(sample_repo_config, sample_branch_config)

    assert is_new is False
    assert "test-repo" in repo_path
    assert "main" in repo_path


@patch("git.Repo.clone_from")
@patch("os.path.exists")
@patch("os.makedirs")
def test_ensure_repo_clone_success(
    mock_makedirs,
    mock_exists,
    mock_clone,
    deployment_service,
    sample_repo_config,
    sample_branch_config,
):
    """Test ensure_repo clones new repository."""
    mock_exists.return_value = False

    is_new, repo_path = deployment_service.ensure_repo(sample_repo_config, sample_branch_config)

    assert is_new is True
    mock_clone.assert_called_once()
    mock_makedirs.assert_called_once()


@patch("git.Repo.clone_from")
@patch("os.path.exists")
@patch("os.makedirs")
@patch("shutil.rmtree")
def test_ensure_repo_clone_failure_cleanup(
    mock_rmtree,
    mock_makedirs,
    mock_exists,
    mock_clone,
    deployment_service,
    sample_repo_config,
    sample_branch_config,
):
    """Test ensure_repo cleans up on clone failure."""
    mock_exists.side_effect = [False, True, True, True]
    mock_clone.side_effect = Exception("Clone failed")

    with pytest.raises(GitOperationError, match="Clone failed"):
        deployment_service.ensure_repo(sample_repo_config, sample_branch_config)

    assert mock_rmtree.call_count >= 1


# ==================== check_actual_target_state Tests ====================


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
@patch.object(DeploymentService, "is_docker_daemon_running")
def test_check_target_state_running(
    mock_daemon,
    mock_exec,
    mock_run,
    deployment_service,
    sample_repo_config,
    sample_branch_config,
    sample_target,
):
    """Test checking target state when services are running."""
    mock_daemon.return_value = True
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.return_value = Mock(returncode=0, stdout="web\napi\n")

    state = deployment_service.check_actual_target_state(
        sample_repo_config, sample_branch_config, "/path/to/repo", sample_target
    )

    assert state == "running"


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
@patch.object(DeploymentService, "is_docker_daemon_running")
def test_check_target_state_stopped(
    mock_daemon,
    mock_exec,
    mock_run,
    deployment_service,
    sample_repo_config,
    sample_branch_config,
    sample_target,
):
    """Test checking target state when no services running."""
    mock_daemon.return_value = True
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.return_value = Mock(returncode=0, stdout="")

    state = deployment_service.check_actual_target_state(
        sample_repo_config, sample_branch_config, "/path/to/repo", sample_target
    )

    assert state == "stopped"


@patch.object(DeploymentService, "is_docker_daemon_running")
def test_check_target_state_daemon_unavailable(
    mock_daemon, deployment_service, sample_repo_config, sample_branch_config, sample_target
):
    """Test checking target state when Docker daemon unavailable."""
    mock_daemon.return_value = False

    state = deployment_service.check_actual_target_state(
        sample_repo_config, sample_branch_config, "/path/to/repo", sample_target
    )

    assert state == "daemon_unavailable"


@patch("subprocess.run")
@patch.object(DeploymentService, "_get_executable_path")
@patch.object(DeploymentService, "is_docker_daemon_running")
def test_check_target_state_error(
    mock_daemon,
    mock_exec,
    mock_run,
    deployment_service,
    sample_repo_config,
    sample_branch_config,
    sample_target,
):
    """Test checking target state handles exceptions."""
    mock_daemon.return_value = True
    mock_exec.return_value = "/usr/bin/docker"
    mock_run.side_effect = Exception("Command failed")

    state = deployment_service.check_actual_target_state(
        sample_repo_config, sample_branch_config, "/path/to/repo", sample_target
    )

    assert state == "error_check"


# ==================== Integration Tests ====================


@pytest.mark.parametrize(
    "auth_method,url_prefix",
    [
        ("https", "https://"),
        ("ssh", "git@"),
    ],
    ids=["https", "ssh"],
)
def test_repo_config_auth_methods(auth_method, url_prefix):
    """Test repository configuration with different auth methods."""
    if auth_method == "https":
        repo = RepoConfig(
            name="test",
            url=f"{url_prefix}github.com/user/repo",
            auth_method=auth_method,
            branches=[],
        )
    else:
        repo = RepoConfig(
            name="test",
            url=f"{url_prefix}github.com:user/repo.git",
            auth_method=auth_method,
            branches=[],
        )

    assert repo.auth_method == auth_method
    assert repo.url.startswith(url_prefix)

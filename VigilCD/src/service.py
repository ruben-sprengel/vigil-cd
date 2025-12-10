"""Deployment Service."""

import logging
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime
from typing import Any

from git import GitCommandError, Repo

from src.config_manager import ConfigManager
from src.models import BranchConfig, ComposeTarget, RepoConfig
from src.state import state_manager

logger = logging.getLogger(__name__)

BASE_DIR = os.environ.get("REPO_BASE_PATH", "/home/vigilcd/src/repos")


class GitOperationError(Exception):
    """Exception für Git-Operationen."""

    pass


class DeploymentError(Exception):
    """Exception für Deployment-Fehler."""

    pass


class DockerConfig:
    """Docker config for cross-platform support.

    Supports:
    - Linux: Socket (/var/run/docker.sock)
    - Windows (WSL2/Docker Desktop): TCP (tcp://localhost:2375)

    """

    @staticmethod
    def get_docker_host() -> str:
        """Gets the appropriate Docker Host URL based on the platform.

        Falls back to defaults if not set.

        Returns:
            Docker Host URL (e.g. unix:///var/run/docker.sock or tcp://localhost:2375)

        """
        if os.getenv("DOCKER_HOST"):
            docker_host = os.getenv("DOCKER_HOST")
            logger.info(f"Using Docker Host from env: {docker_host}")
            return docker_host

        if platform.system() == "Windows":
            logger.info("Windows detected: Using Docker Desktop TCP (localhost:2375)")
            return "tcp://localhost:2375"

        if os.path.exists("/var/run/docker.sock"):
            logger.info("Linux detected: Using Docker Socket (/var/run/docker.sock)")
            return "unix:///var/run/docker.sock"

        logger.warning("Could not determine Docker Host, using default socket")
        return "unix:///var/run/docker.sock"


class DeploymentService:
    """Service for managing deployments."""

    def __init__(self, config_manager: ConfigManager = None) -> None:
        """Initializes the DeploymentService with configuration.

        Args:
            config_manager: Optional ConfigManager instance

        Returns:
            None

        """
        self.config = config_manager or ConfigManager()
        self.docker_host = DockerConfig.get_docker_host()
        logger.info(f"DeploymentService initialized with Docker Host: {self.docker_host}")

    def _get_executable_path(self, command: str) -> str:
        """Finds the full path of an executable command.

        Args:
            command: Name of the command (e.g., "git", "docker")

        Returns:
            Full path to the executable

        Raises:
            DeploymentError: If the command is not found in PATH.

        """
        full_path = shutil.which(command)
        if not full_path:
            raise DeploymentError(f"Executable '{command}' not found in PATH.")
        return full_path

    def _get_git_env(self, repo_conf: RepoConfig) -> dict[str, str]:
        """Creates environment variables for Git operations based on auth method.

        Args:
            repo_conf: RepoConfig object

        Returns:
            dict with environment variables for Git commands

        """
        env = os.environ.copy()

        if repo_conf.auth_method == "ssh":
            # Repo-spezifisch oder global
            ssh_key = repo_conf.ssh_key_path or self.config.get_ssh_key_path()

            if not ssh_key:
                raise GitOperationError(f"SSH auth for {repo_conf.name} requires ssh_key_path")

            if not os.path.exists(ssh_key):
                raise GitOperationError(f"SSH key not found: {ssh_key}")

            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {ssh_key} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            )
            logger.debug(f"Using SSH key for {repo_conf.name}: {ssh_key}")

        return env

    def is_docker_daemon_running(self) -> bool:
        """Checks if the Docker daemon is running and reachable.

        Returns:
            True if Docker daemon is reachable, False otherwise.

        """
        try:
            timeout = self.config.deployment.docker_daemon_timeout_seconds
            docker_cmd = self._get_executable_path("docker")
            env = os.environ.copy()
            env["DOCKER_HOST"] = self.docker_host

            subprocess.run(  # noqa: S603
                [docker_cmd, "info"],
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
                env=env,
            )
            logger.info(f"Docker daemon is running on {self.docker_host}")
            return True
        except DeploymentError:
            logger.error("Docker command not found. Is Docker installed and in PATH?")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker daemon error: {e.stderr[:100]}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Docker daemon check timed out after {timeout}s")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking Docker daemon: {e}")
            return False

    def _retry_with_backoff(
        self, func, max_retries: int | None = None, backoff_factor: float | None = None
    ) -> Any:
        """Retries a function with exponential backoff on Git errors.

        Args:
            func: Callable, das ausgeführt wird
            max_retries: Max Versuche (default aus Config)
            backoff_factor: Backoff-Faktor (default aus Config)

        Returns:
            return value from func()

        """
        max_retries = max_retries or self.config.scheduling.git_retry_count
        backoff_factor = backoff_factor or self.config.scheduling.retry_backoff_factor

        for attempt in range(max_retries):
            try:
                return func()
            except (GitOperationError, GitCommandError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Max retries ({max_retries}) exceeded: {e}")
                    raise

                wait_time = backoff_factor**attempt
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed. Retry after {wait_time}s: {e}"
                )
                time.sleep(wait_time)
        return None

    def docker_login_registries(self, registries: list | None) -> bool:
        """Logs in to private Docker registries before deployment.

        Public registries are skipped (username=None).

        Args:
            registries: List of RegistryConfig objects or None

        Returns:
            True if successful, False if login failed

        """
        if not registries:
            logger.debug("No registries configured, using default public docker.io")
            return True

        try:
            docker_cmd = self._get_executable_path("docker")
        except DeploymentError as e:
            logger.error(f"Docker login failed: {e}")
            return False

        for registry in registries:
            # Skip public registries (no username)
            if not registry.username:
                logger.debug(f"Skipping public registry: {registry.url}")
                continue

            # Get password from environment variable
            password = os.getenv(registry.password_env_var)
            if not password:
                logger.error("Password env var not set.")
                return False

            cmd = [
                docker_cmd,
                "login",
                "-u",
                registry.username,
                "-p",
                password,
                registry.url,
            ]

            try:
                env = os.environ.copy()
                env["DOCKER_HOST"] = self.docker_host

                subprocess.run(  # noqa: S603
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                    env=env,
                )
                logger.info(f"Docker login successful for {registry.url}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Docker login failed for {registry.url}: {e.stderr[:200]}")
                return False
            except subprocess.TimeoutExpired:
                logger.error(f"Docker login timeout for {registry.url}")
                return False

        return True

    def docker_logout_registries(self, registries: list | None) -> None:
        """Logs out from private Docker registries after deployment.

        Args:
            registries: List of RegistryConfig objects

        Returns:
            None

        """
        if not registries:
            return

        try:
            docker_cmd = self._get_executable_path("docker")
        except DeploymentError:
            logger.warning("Docker executable not found, skipping logout.")
            return

        for registry in registries:
            # Skip public registries
            if not registry.username:
                continue

            try:
                cmd = [docker_cmd, "logout", registry.url]
                subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)  # noqa: S603
                logger.debug(f"Docker logout for {registry.url}")
            except Exception as e:
                logger.warning(f"Docker logout failed for {registry.url}: {e}")

    def ensure_repo(self, repo_conf: RepoConfig, branch_conf: BranchConfig) -> tuple[bool, str]:
        """Clones the repository if it does not exist locally otherwise returns the existing path.

        Returns:
            (is_new, repo_path): is_new = True if cloned, False if already exists

        """
        repo_path = os.path.join(BASE_DIR, repo_conf.name, branch_conf.name)

        if os.path.exists(repo_path):
            logger.info(f"Repository already exists: {repo_path}")
            return False, repo_path

        logger.info(f"Cloning {repo_conf.name} ({branch_conf.name}) from {repo_conf.url}...")
        os.makedirs(repo_path, exist_ok=True)

        def clone():
            try:
                git_env = self._get_git_env(repo_conf)

                Repo.clone_from(
                    repo_conf.url,
                    repo_path,
                    branch=branch_conf.name,
                    env=git_env,
                    # timeout=self.config.deployment.git_operation_timeout_seconds
                )
                logger.info(f"Successfully cloned {repo_conf.name}/{branch_conf.name}")
            except Exception as e:
                # Cleanup bei Fehler
                if os.path.exists(repo_path):
                    shutil.rmtree(repo_path)
                raise GitOperationError(f"Clone failed: {e}") from e

        self._retry_with_backoff(clone)
        return True, repo_path

    def check_and_update(self, repo_conf: RepoConfig, branch_conf: BranchConfig) -> None:  # noqa: PLR0915
        """Checks for Git updates and deploys if necessary.

        Args:
            repo_conf: RepoConfig object
            branch_conf: BranchConfig object

        Returns:
            None

        """
        repo_id = f"{repo_conf.name}/{branch_conf.name}"
        logger.info(f"Starting check_and_update for {repo_id}")

        state_manager.update_branch(
            repo_conf.name,
            branch_conf.name,
            sync_status="checking",
            last_check_time=datetime.now(),
        )

        try:
            # 1. Stelle sicher, dass Repo existiert
            is_new, repo_path = self.ensure_repo(repo_conf, branch_conf)
            repo = Repo(repo_path)

            deployment_required = False
            git_updated = False

            # 2. Prüfe auf Git-Änderungen (mit Timeout)
            try:
                remote_url = repo.remotes.origin.url
                git_env = self._get_git_env(repo_conf)
                # timeout = self.config.deployment.git_operation_timeout_seconds

                def fetch_remote_info():
                    try:
                        ls_remote_output = repo.git.ls_remote(
                            remote_url,
                            f"refs/heads/{branch_conf.name}",
                            env=git_env,
                            # timeout=timeout
                        )
                        if not ls_remote_output:
                            raise GitOperationError(
                                f"Remote returned empty for branch '{branch_conf.name}'. Does it exist?"
                            )
                        return ls_remote_output
                    except GitCommandError as e:
                        raise GitOperationError(f"ls-remote failed: {e}") from e

                ls_remote_output = self._retry_with_backoff(fetch_remote_info)
                remote_commit_hash = ls_remote_output.split()[0]
                local_commit_hash = repo.head.commit.hexsha

                state_manager.update_branch(
                    repo_conf.name, branch_conf.name, commit_hash=remote_commit_hash[:7]
                )

                # 3. Prüfe ob Update nötig
                if local_commit_hash != remote_commit_hash or is_new:
                    logger.info(f"Update available for {repo_id}")
                    state_manager.update_branch(
                        repo_conf.name, branch_conf.name, sync_status="pulling"
                    )

                    def pull_changes():
                        try:
                            # fetch und reset --hard for overwrite local changes
                            logger.info(f"Fetching changes for {repo_id}")
                            repo.remotes.origin.fetch(env=git_env)

                            remote_branch = f"origin/{branch_conf.name}"
                            repo.git.reset("--hard", remote_branch)

                            logger.info(f"Cleaning repository, excluding .env: {repo_id}")
                            repo.git.clean("-fxd", "--exclude=.env")

                            logger.info(
                                f"Successfully reset and cleaned to {remote_branch} for {repo_id}"
                            )
                        except GitCommandError as e:
                            raise GitOperationError(f"Fetch/Reset failed: {e}") from e

                    self._retry_with_backoff(pull_changes)

                    state_manager.update_branch(
                        repo_conf.name,
                        branch_conf.name,
                        sync_status="idle",
                        commit_hash=repo.head.commit.hexsha[:7],
                    )
                    git_updated = True
                    deployment_required = True
                else:
                    logger.debug(f"No updates for {repo_id}")
                    state_manager.update_branch(
                        repo_conf.name, branch_conf.name, sync_status="idle"
                    )

            except GitOperationError as e:
                logger.error(f"Git operation failed for {repo_id}: {e}")
                state_manager.update_branch(repo_conf.name, branch_conf.name, sync_status="error")
                return

            # 4. Prüfe auf fehlgeschlagene Deployments (Health Check)
            if not git_updated:
                for target in branch_conf.targets:
                    actual_state = self.check_actual_target_state(
                        repo_conf, branch_conf, repo_path, target
                    )
                    if actual_state in ["stopped", "daemon_unavailable", "error_check"]:
                        logger.warning(f"Target {target.name} health check failed: {actual_state}")
                        deployment_required = True
                        break

            # 5. Führe Deployment durch
            if deployment_required:
                for target in branch_conf.targets:
                    if target.deploy:
                        self.deploy_target(repo_conf, branch_conf, repo_path, target)
                    else:
                        state_manager.update_target(
                            repo_conf.name,
                            branch_conf.name,
                            target.name,
                            "skipped",
                            "Deploy disabled",
                        )

        except Exception as e:
            logger.exception(f"Unexpected error in check_and_update for {repo_id}: {e}")
            state_manager.update_branch(repo_conf.name, branch_conf.name, sync_status="error")

    def deploy_target(self, repo_conf, branch_conf, cwd: str, target: ComposeTarget) -> None:
        """Runs Docker Compose deployment for the given target.

        Logs in to registries if configured.

        Args:
            repo_conf: RepoConfig object mit Registries
            branch_conf: BranchConfig object
            cwd: Working Directory für Docker Compose
            target: Compose Target Config

        Returns:
            None

        """
        if not self.is_docker_daemon_running():
            logger.error(f"Docker daemon not available for {target.name}")
            state_manager.update_target(
                repo_conf.name,
                branch_conf.name,
                target.name,
                "error",
                "Docker daemon unavailable",
            )
            return

        target_id = f"{repo_conf.name}/{branch_conf.name}/{target.name}"
        logger.info(f"Starting deployment for {target_id}")

        state_manager.update_target(
            repo_conf.name,
            branch_conf.name,
            target.name,
            "deploying",
            "Starting deployment...",
        )

        try:
            docker_path = self._get_executable_path("docker")

            if not self.docker_login_registries(repo_conf.registries):
                state_manager.update_target(
                    repo_conf.name,
                    branch_conf.name,
                    target.name,
                    "error",
                    "Docker registry login failed",
                )
                return

            project_name = f"{repo_conf.name}_{branch_conf.name}".lower().replace("-", "_")
            cmd = [
                docker_path,
                "compose",
                "-p",
                project_name,
                "-f",
                target.file,
                "up",
                "-d",
            ]

            if target.build_images:
                cmd.append("--build")

            cmd.extend(["--remove-orphans"])

            timeout = self.config.deployment.docker_compose_timeout_seconds
            logger.debug(f"Docker compose command: {' '.join(cmd)}")

            env = os.environ.copy()
            env["DOCKER_HOST"] = self.docker_host

            subprocess.run(  # noqa: S603
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
                env=env,
            )

            self.docker_logout_registries(repo_conf.registries)

            logger.info(f"Deployment successful for {target_id}")
            state_manager.update_target(
                repo_conf.name, branch_conf.name, target.name, "success", "Running"
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[-500:] if e.stderr else e.stdout[-500:]
            logger.exception(f"Deployment failed for {target_id}: {error_msg}")
            state_manager.update_target(
                repo_conf.name,
                branch_conf.name,
                target.name,
                "error",
                f"Deployment error: {error_msg}",
            )

        except subprocess.TimeoutExpired:
            logger.exception(f"Deployment timeout ({timeout}s) for {target_id}")
            state_manager.update_target(
                repo_conf.name,
                branch_conf.name,
                target.name,
                "error",
                f"Timeout after {timeout}s",
            )

        except Exception as e:
            logger.exception(f"Unexpected error during deployment of {target_id}: {e}")
            state_manager.update_target(
                repo_conf.name,
                branch_conf.name,
                target.name,
                "error",
                f"Unexpected error: {str(e)[:100]}",
            )

    def check_actual_target_state(
        self, repo_conf, branch_conf, repo_path: str, target: ComposeTarget
    ) -> str:
        """Checks the actual live state of the Docker Compose target.

        Args:
            repo_conf: RepoConfig object
            branch_conf: BranchConfig object
            repo_path: Path to the repository
            target: Compose Target Config

        Returns:
            State string: "running", "stopped", "daemon_unavailable", "error_check

        """
        if not self.is_docker_daemon_running():
            return "daemon_unavailable"

        try:
            docker_path = self._get_executable_path("docker")
            project_name = f"{repo_conf.name}_{branch_conf.name}".lower().replace("-", "_")
            cmd = [
                docker_path,
                "compose",
                "-p",
                project_name,
                "-f",
                target.file,
                "ps",
                "--services",
                "--filter",
                "status=running",
            ]

            env = os.environ.copy()
            env["DOCKER_HOST"] = self.docker_host

            result = subprocess.run(  # noqa: S603
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
                env=env,
            )

            running_services = result.stdout.strip().split()

            if running_services:
                logger.info(f"Target '{target.name}' running services: {running_services}")
                return "running"

            if result.returncode == 0:
                logger.warning(f"Target '{target.name}' is STOPPED (No running containers found).")
                return "stopped"

            return "error_check"

        except Exception as e:
            logger.exception(f"Failed to check live Docker state for {target.name}: {e}")
            return "error_check"

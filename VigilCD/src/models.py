"""Defines the data models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator


class ComposeTarget(BaseModel):
    """Represents a target in a compose configuration.

    Attributes:
        name (str): The name of the target.
        file (str): The file associated with the target.
        deploy (bool): Indicates whether the target should be deployed. Defaults to False.
        build_images (bool): Whether to rebuild Docker images on deploy. Defaults to False.
                            Set to False for faster deployments if only configuration changed.

    """

    name: str
    file: str
    deploy: bool = False
    build_images: bool = False


class BranchConfig(BaseModel):
    """Represents the configuration for a branch.

    Attributes:
        name (str): The name of the branch.
        sync_enabled (bool): Indicates whether synchronization is enabled for the branch. If False, the branch will be skipped during sync operations and deployments.
        targets (list[ComposeTarget]): A list of compose targets associated with the branch.

    """

    name: str
    sync_enabled: bool
    targets: list[ComposeTarget]


class RegistryConfig(BaseModel):
    """Represents a Docker Registry configuration.

    Default is PUBLIC (docker.io). Private registries must be explicitly configured.

    Attributes:
        url (str): Registry URL (e.g., "docker.io", "ghcr.io", "registry.company.com:5000")
        username (Optional[str]): Username for private registries. If None, registry is treated as public.
        password_env_var (Optional[str]): Name of environment variable containing registry password.
                                          Only used if username is set.

    """

    url: str
    username: str | None = None
    password_env_var: str | None = None


class RepoConfig(BaseModel):
    """Represents the configuration for a repository.

    Attributes:
        name (str): The name of the repository.
        url (str): The URL of the repository.
        registries (Optional[list[RegistryConfig]]): Docker registries for this repo.
                                                     If None, defaults to public docker.io
        branches (list[BranchConfig]): A list of branch configurations for the repository.

    """

    name: str
    url: str
    auth_method: Literal["https", "ssh"] = "https"
    ssh_key_path: str | None = None  # Pro-Repo SSH Key
    registries: list[RegistryConfig] | None = None
    branches: list[BranchConfig]

    @model_validator(mode="after")
    def validate_url_for_auth_method(self) -> "Config":
        """Validates the URL based on the auth_method."""
        auth = getattr(self, "auth_method", "https")

        if auth == "ssh" and not self.url.startswith("git@"):
            raise ValueError("For SSH auth_method, the URL must start with 'git@'")

        return self


class Config(BaseModel):
    """Represents the overall configuration.

    Attributes:
        repos (list[RepoConfig]): A list of repository configurations.

    """

    repos: list[RepoConfig]


class TargetStatus(BaseModel):
    """Represents the status of a target for the frontend.

    Attributes:
        name (str): The name of the target.
        last_deploy_time (Optional[datetime]): The last deployment time of the target. Defaults to None.
        status (str): The current status of the target. Can be 'pending', 'success', 'error', or 'skipped'. Defaults to 'pending'.
        message (str): A message providing additional information about the status. Defaults to an empty string.

    """

    name: str
    last_deploy_time: datetime | None = None
    status: str = "pending"  # pending, success, error, skipped
    message: str = ""


class BranchStatus(BaseModel):
    """Represents the status of a branch for the frontend.

    Attributes:
        branch_name (str): The name of the branch.
        last_check_time (Optional[datetime]): The last time the branch was checked. Defaults to None.
        commit_hash (str): The hash of the last commit. Defaults to 'unknown'.
        sync_status (str): The synchronization status of the branch. Can be 'idle', 'pulling', or 'error'. Defaults to 'idle'.
        targets (dict[str, TargetStatus]): A dictionary mapping target names to their statuses.

    """

    branch_name: str
    last_check_time: datetime | None = None
    commit_hash: str = "unknown"
    sync_status: str = "idle"  # idle, pulling, error
    targets: dict[str, TargetStatus] = {}  # Key ist Target Name


class RepoStatus(BaseModel):
    """Represents the status of a repository for the frontend.

    Attributes:
        repo_name (str): The name of the repository.
        branches (dict[str, BranchStatus]): A dictionary mapping branch names to their statuses.

    """

    repo_name: str
    branches: dict[str, BranchStatus] = {}

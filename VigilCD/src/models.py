from pydantic import BaseModel, model_validator
from typing import Optional, Literal
from datetime import datetime


class ComposeTarget(BaseModel):
    """
    Represents a target in a compose configuration.

    Attributes:
        name (str): The name of the target.
        file (str): The file associated with the target.
        deploy (bool): Indicates whether the target should be deployed. Defaults to True.
        build_images (bool): Whether to rebuild Docker images on deploy. Defaults to True.
                            Set to False for faster deployments if only configuration changed.
    """
    name: str
    file: str
    deploy: bool = True
    build_images: bool = True


class BranchConfig(BaseModel):
    """
    Represents the configuration for a branch.

    Attributes:
        name (str): The name of the branch.
        targets (list[ComposeTarget]): A list of compose targets associated with the branch.
    """
    name: str
    targets: list[ComposeTarget]


class RegistryConfig(BaseModel):
    """
    Represents a Docker Registry configuration.

    Default is PUBLIC (docker.io). Private registries must be explicitly configured.

    Attributes:
        url (str): Registry URL (e.g., "docker.io", "ghcr.io", "registry.company.com:5000")
        username (Optional[str]): Username for private registries. If None, registry is treated as public.
        password_env_var (Optional[str]): Name of environment variable containing registry password.
                                          Only used if username is set.
    """
    url: str
    username: Optional[str] = None
    password_env_var: Optional[str] = None


class RepoConfig(BaseModel):
    """
    Represents the configuration for a repository.

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
    ssh_key_path: Optional[str] = None  # Pro-Repo SSH Key
    registries: Optional[list[RegistryConfig]] = None
    branches: list[BranchConfig]

    # @field_validator('ssh_key_path')
    # def validate_ssh_key(cls, v, values):
    #     """Validiert, dass bei SSH-Auth ein Key-Pfad angegeben ist."""
    #     if values.get('auth_method') == 'ssh' and not v:
    #         raise ValueError("ssh_key_path is required when auth_method is 'ssh'")
    #     return v

    @model_validator(mode='after')
    def validate_url_for_auth_method(self) -> 'Config':
        """
        Validates the URL based on the auth_method.
        In Pydantic v2, we use 'self' (the model instance) to access field values
        after validation (mode='after').
        """
        # Replace 'values' access with 'self' attribute access
        auth = getattr(self, 'auth_method', 'https')

        # Now, perform the original validation logic using self.url and 'auth'
        if auth == 'ssh' and not self.url.startswith('git@'):
            # This is where your actual validation logic goes
            # For example: raise ValueError("SSH authentication requires a 'git@' URL scheme")
            pass

        return self


class Config(BaseModel):
    """
    Represents the overall configuration.

    Attributes:
        repos (list[RepoConfig]): A list of repository configurations.
    """
    repos: list[RepoConfig]


# --- Status Modelle (für das Frontend) ---
class TargetStatus(BaseModel):
    """
    Represents the status of a target for the frontend.

    Attributes:
        name (str): The name of the target.
        last_deploy_time (Optional[datetime]): The last deployment time of the target. Defaults to None.
        status (str): The current status of the target. Can be 'pending', 'success', 'error', or 'skipped'. Defaults to 'pending'.
        message (str): A message providing additional information about the status. Defaults to an empty string.
    """
    name: str
    last_deploy_time: Optional[datetime] = None
    status: str = "pending"  # pending, success, error, skipped
    message: str = ""


class BranchStatus(BaseModel):
    """
    Represents the status of a branch for the frontend.

    Attributes:
        branch_name (str): The name of the branch.
        last_check_time (Optional[datetime]): The last time the branch was checked. Defaults to None.
        commit_hash (str): The hash of the last commit. Defaults to 'unknown'.
        sync_status (str): The synchronization status of the branch. Can be 'idle', 'pulling', or 'error'. Defaults to 'idle'.
        targets (dict[str, TargetStatus]): A dictionary mapping target names to their statuses.
    """
    branch_name: str
    last_check_time: Optional[datetime] = None
    commit_hash: str = "unknown"
    sync_status: str = "idle"  # idle, pulling, error
    targets: dict[str, TargetStatus] = {}  # Key ist Target Name


class RepoStatus(BaseModel):
    """
    Represents the status of a repository for the frontend.

    Attributes:
        repo_name (str): The name of the repository.
        branches (dict[str, BranchStatus]): A dictionary mapping branch names to their statuses.
    """
    repo_name: str
    branches: dict[str, BranchStatus] = {}

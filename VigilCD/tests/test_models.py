"""Unit tests for Pydantic Models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models import (
    BranchConfig,
    BranchStatus,
    ComposeTarget,
    Config,
    RegistryConfig,
    RepoConfig,
    RepoStatus,
    TargetStatus,
)

# ==================== ComposeTarget Tests ====================


def test_compose_target_minimal():
    """Test ComposeTarget with minimal required fields."""
    target = ComposeTarget(name="web", file="docker-compose.yml")

    assert target.name == "web"
    assert target.file == "docker-compose.yml"
    assert target.deploy is False
    assert target.build_images is False


def test_compose_target_full():
    """Test ComposeTarget with all fields."""
    target = ComposeTarget(
        name="api", file="docker-compose.prod.yml", deploy=True, build_images=True
    )

    assert target.name == "api"
    assert target.file == "docker-compose.prod.yml"
    assert target.deploy is True
    assert target.build_images is True


@pytest.mark.parametrize(
    "deploy,build_images",
    [
        (True, False),
        (False, True),
        (True, True),
        (False, False),
    ],
    ids=["deploy_only", "build_only", "both", "neither"],
)
def test_compose_target_flags(deploy, build_images):
    """Test ComposeTarget with various flag combinations."""
    target = ComposeTarget(name="srv", file="compose.yml", deploy=deploy, build_images=build_images)

    assert target.deploy == deploy
    assert target.build_images == build_images


def test_compose_target_serialization():
    """Test ComposeTarget serialization to dict."""
    target = ComposeTarget(name="worker", file="compose.yml", deploy=True)
    data = target.model_dump()

    assert data["name"] == "worker"
    assert data["file"] == "compose.yml"
    assert data["deploy"] is True
    assert data["build_images"] is False


# ==================== BranchConfig Tests ====================


def test_branch_config_minimal():
    """Test BranchConfig with minimal required fields."""
    branch = BranchConfig(name="main", targets=[])

    assert branch.name == "main"
    assert branch.sync_enabled is False
    assert branch.targets == []


def test_branch_config_with_targets():
    """Test BranchConfig with targets."""
    targets = [
        ComposeTarget(name="web", file="compose.yml", deploy=True),
        ComposeTarget(name="api", file="compose.api.yml", deploy=False),
    ]

    branch = BranchConfig(name="develop", sync_enabled=True, targets=targets)

    assert branch.name == "develop"
    assert branch.sync_enabled is True
    assert len(branch.targets) == 2
    assert branch.targets[0].name == "web"
    assert branch.targets[1].name == "api"


def test_branch_config_sync_enabled_default():
    """Test BranchConfig sync_enabled defaults to False."""
    branch = BranchConfig(name="staging", targets=[])

    assert branch.sync_enabled is False


def test_branch_config_serialization():
    """Test BranchConfig serialization with nested targets."""
    branch = BranchConfig(
        name="main",
        sync_enabled=True,
        targets=[ComposeTarget(name="srv", file="compose.yml")],
    )

    data = branch.model_dump()

    assert data["name"] == "main"
    assert data["sync_enabled"] is True
    assert len(data["targets"]) == 1
    assert data["targets"][0]["name"] == "srv"


# ==================== RegistryConfig Tests ====================


def test_registry_config_public():
    """Test RegistryConfig for public registry (no auth)."""
    registry = RegistryConfig(url="docker.io")

    assert registry.url == "docker.io"
    assert registry.username is None
    assert registry.password_env_var is None


def test_registry_config_private():
    """Test RegistryConfig for private registry with auth."""
    registry = RegistryConfig(url="ghcr.io", username="myuser", password_env_var="GHCR_PASSWORD")

    assert registry.url == "ghcr.io"
    assert registry.username == "myuser"
    assert registry.password_env_var == "GHCR_PASSWORD"


@pytest.mark.parametrize(
    "url",
    [
        "docker.io",
        "ghcr.io",
        "quay.io",
        "registry.company.com",
        "registry.company.com:5000",
        "localhost:5000",
    ],
    ids=["docker_hub", "github", "quay", "custom", "custom_port", "localhost"],
)
def test_registry_config_various_urls(url):
    """Test RegistryConfig with various registry URLs."""
    registry = RegistryConfig(url=url)

    assert registry.url == url


def test_registry_config_serialization():
    """Test RegistryConfig serialization."""
    registry = RegistryConfig(
        url="harbor.example.com", username="admin", password_env_var="HARBOR_PASS"
    )

    data = registry.model_dump()

    assert data["url"] == "harbor.example.com"
    assert data["username"] == "admin"
    assert data["password_env_var"] == "HARBOR_PASS"


# ==================== RepoConfig Tests ====================


def test_repo_config_minimal_https():
    """Test RepoConfig with minimal HTTPS configuration."""
    repo = RepoConfig(name="test-repo", url="https://github.com/user/repo", branches=[])

    assert repo.name == "test-repo"
    assert repo.url == "https://github.com/user/repo"
    assert repo.auth_method == "https"
    assert repo.ssh_key_path is None
    assert repo.registries is None
    assert repo.branches == []


def test_repo_config_ssh_valid():
    """Test RepoConfig with valid SSH configuration."""
    repo = RepoConfig(
        name="ssh-repo",
        url="git@github.com:user/repo.git",
        auth_method="ssh",
        ssh_key_path="/path/to/key",
        branches=[],
    )

    assert repo.name == "ssh-repo"
    assert repo.url == "git@github.com:user/repo.git"
    assert repo.auth_method == "ssh"
    assert repo.ssh_key_path == "/path/to/key"


def test_repo_config_ssh_invalid_url():
    """Test RepoConfig validation fails for SSH with HTTPS URL."""
    with pytest.raises(ValidationError, match="URL must start with 'git@'"):
        RepoConfig(
            name="invalid",
            url="https://github.com/user/repo",
            auth_method="ssh",
            branches=[],
        )


def test_repo_config_with_registries():
    """Test RepoConfig with multiple registries."""
    registries = [
        RegistryConfig(url="docker.io"),
        RegistryConfig(url="ghcr.io", username="user", password_env_var="GHCR_TOKEN"),
    ]

    repo = RepoConfig(
        name="multi-reg",
        url="https://github.com/user/repo",
        registries=registries,
        branches=[],
    )

    assert len(repo.registries) == 2
    assert repo.registries[0].url == "docker.io"
    assert repo.registries[1].username == "user"


def test_repo_config_with_branches():
    """Test RepoConfig with multiple branches."""
    branches = [
        BranchConfig(name="main", sync_enabled=True, targets=[]),
        BranchConfig(name="develop", sync_enabled=False, targets=[]),
    ]

    repo = RepoConfig(name="test", url="https://github.com/user/test", branches=branches)

    assert len(repo.branches) == 2
    assert repo.branches[0].name == "main"
    assert repo.branches[1].name == "develop"


def test_repo_config_complex():
    """Test RepoConfig with complex nested structure."""
    repo = RepoConfig(
        name="complex-repo",
        url="git@github.com:org/repo.git",
        auth_method="ssh",
        ssh_key_path="/home/user/.ssh/id_rsa",
        registries=[RegistryConfig(url="ghcr.io", username="bot", password_env_var="GHCR_TOKEN")],
        branches=[
            BranchConfig(
                name="main",
                sync_enabled=True,
                targets=[
                    ComposeTarget(name="web", file="compose.yml", deploy=True),
                    ComposeTarget(name="api", file="compose.api.yml", deploy=True),
                ],
            )
        ],
    )

    assert repo.name == "complex-repo"
    assert repo.auth_method == "ssh"
    assert len(repo.registries) == 1
    assert len(repo.branches) == 1
    assert len(repo.branches[0].targets) == 2


def test_repo_config_serialization():
    """Test RepoConfig serialization."""
    repo = RepoConfig(
        name="test",
        url="https://github.com/test/repo",
        auth_method="https",
        branches=[BranchConfig(name="main", targets=[])],
    )

    data = repo.model_dump()

    assert data["name"] == "test"
    assert data["url"] == "https://github.com/test/repo"
    assert data["auth_method"] == "https"
    assert len(data["branches"]) == 1


# ==================== Config Tests ====================


def test_config_empty():
    """Test Config with empty repos list."""
    config = Config(repos=[])

    assert config.repos == []


def test_config_single_repo():
    """Test Config with single repository."""
    repo = RepoConfig(name="test", url="https://github.com/test/repo", branches=[])

    config = Config(repos=[repo])

    assert len(config.repos) == 1
    assert config.repos[0].name == "test"


def test_config_multiple_repos():
    """Test Config with multiple repositories."""
    repos = [
        RepoConfig(name="repo1", url="https://github.com/user/repo1", branches=[]),
        RepoConfig(name="repo2", url="https://github.com/user/repo2", branches=[]),
        RepoConfig(name="repo3", url="https://github.com/user/repo3", branches=[]),
    ]

    config = Config(repos=repos)

    assert len(config.repos) == 3
    assert config.repos[0].name == "repo1"
    assert config.repos[2].name == "repo3"


def test_config_serialization():
    """Test Config serialization."""
    config = Config(
        repos=[RepoConfig(name="test", url="https://github.com/test/repo", branches=[])]
    )

    data = config.model_dump()

    assert "repos" in data
    assert len(data["repos"]) == 1


# ==================== TargetStatus Tests ====================


def test_target_status_minimal():
    """Test TargetStatus with minimal required fields."""
    target = TargetStatus(name="web")

    assert target.name == "web"
    assert target.last_deploy_time is None
    assert target.status == "pending"
    assert target.message == ""


def test_target_status_full():
    """Test TargetStatus with all fields."""
    now = datetime.now()
    target = TargetStatus(
        name="api", last_deploy_time=now, status="success", message="Deployed successfully"
    )

    assert target.name == "api"
    assert target.last_deploy_time == now
    assert target.status == "success"
    assert target.message == "Deployed successfully"


@pytest.mark.parametrize(
    "status,message",
    [
        ("pending", "Waiting..."),
        ("success", "Deployed"),
        ("error", "Failed"),
        ("skipped", "Skipped"),
        ("deploying", "In progress"),
    ],
    ids=["pending", "success", "error", "skipped", "deploying"],
)
def test_target_status_various_statuses(status, message):
    """Test TargetStatus with various status values."""
    target = TargetStatus(name="srv", status=status, message=message)

    assert target.status == status
    assert target.message == message


def test_target_status_with_timestamp():
    """Test TargetStatus with deployment timestamp."""
    deploy_time = datetime(2025, 1, 15, 10, 30, 0)
    target = TargetStatus(name="worker", last_deploy_time=deploy_time, status="success")

    assert target.last_deploy_time == deploy_time


def test_target_status_serialization():
    """Test TargetStatus serialization."""
    target = TargetStatus(name="cron", status="error", message="Failed to start")

    data = target.model_dump()

    assert data["name"] == "cron"
    assert data["status"] == "error"
    assert data["message"] == "Failed to start"
    assert data["last_deploy_time"] is None


# ==================== BranchStatus Tests ====================


def test_branch_status_minimal():
    """Test BranchStatus with minimal required fields."""
    branch = BranchStatus(branch_name="main")

    assert branch.branch_name == "main"
    assert branch.last_check_time is None
    assert branch.commit_hash == "unknown"
    assert branch.sync_status == "idle"
    assert branch.targets == {}


def test_branch_status_full():
    """Test BranchStatus with all fields."""
    now = datetime.now()
    targets = {"web": TargetStatus(name="web", status="success")}

    branch = BranchStatus(
        branch_name="develop",
        last_check_time=now,
        commit_hash="abc1234",
        sync_status="pulling",
        targets=targets,
    )

    assert branch.branch_name == "develop"
    assert branch.last_check_time == now
    assert branch.commit_hash == "abc1234"
    assert branch.sync_status == "pulling"
    assert len(branch.targets) == 1


@pytest.mark.parametrize(
    "sync_status",
    ["idle", "pulling", "checking", "error"],
    ids=["idle", "pulling", "checking", "error"],
)
def test_branch_status_various_sync_statuses(sync_status):
    """Test BranchStatus with various sync_status values."""
    branch = BranchStatus(branch_name="feature", sync_status=sync_status)

    assert branch.sync_status == sync_status


def test_branch_status_with_multiple_targets():
    """Test BranchStatus with multiple targets."""
    targets = {
        "web": TargetStatus(name="web", status="success"),
        "api": TargetStatus(name="api", status="deploying"),
        "worker": TargetStatus(name="worker", status="pending"),
    }

    branch = BranchStatus(branch_name="main", targets=targets)

    assert len(branch.targets) == 3
    assert "web" in branch.targets
    assert "api" in branch.targets
    assert "worker" in branch.targets


def test_branch_status_commit_hash_default():
    """Test BranchStatus commit_hash defaults to 'unknown'."""
    branch = BranchStatus(branch_name="staging")

    assert branch.commit_hash == "unknown"


def test_branch_status_serialization():
    """Test BranchStatus serialization with nested targets."""
    branch = BranchStatus(
        branch_name="main",
        commit_hash="def5678",
        targets={"srv": TargetStatus(name="srv", status="success")},
    )

    data = branch.model_dump()

    assert data["branch_name"] == "main"
    assert data["commit_hash"] == "def5678"
    assert "srv" in data["targets"]
    assert data["targets"]["srv"]["status"] == "success"


# ==================== RepoStatus Tests ====================


def test_repo_status_minimal():
    """Test RepoStatus with minimal required fields."""
    repo = RepoStatus(repo_name="test-repo")

    assert repo.repo_name == "test-repo"
    assert repo.branches == {}


def test_repo_status_with_branches():
    """Test RepoStatus with multiple branches."""
    branches = {
        "main": BranchStatus(branch_name="main", sync_status="idle"),
        "develop": BranchStatus(branch_name="develop", sync_status="pulling"),
    }

    repo = RepoStatus(repo_name="my-repo", branches=branches)

    assert repo.repo_name == "my-repo"
    assert len(repo.branches) == 2
    assert "main" in repo.branches
    assert "develop" in repo.branches


def test_repo_status_complex():
    """Test RepoStatus with complex nested structure."""
    branches = {
        "main": BranchStatus(
            branch_name="main",
            commit_hash="abc123",
            sync_status="idle",
            targets={
                "web": TargetStatus(name="web", status="success"),
                "api": TargetStatus(name="api", status="success"),
            },
        ),
        "develop": BranchStatus(
            branch_name="develop",
            commit_hash="def456",
            sync_status="pulling",
            targets={"web": TargetStatus(name="web", status="deploying")},
        ),
    }

    repo = RepoStatus(repo_name="complex-repo", branches=branches)

    assert len(repo.branches) == 2
    assert len(repo.branches["main"].targets) == 2
    assert len(repo.branches["develop"].targets) == 1


def test_repo_status_serialization():
    """Test RepoStatus serialization."""
    repo = RepoStatus(
        repo_name="test",
        branches={"main": BranchStatus(branch_name="main", commit_hash="xyz789")},
    )

    data = repo.model_dump()

    assert data["repo_name"] == "test"
    assert "main" in data["branches"]
    assert data["branches"]["main"]["commit_hash"] == "xyz789"


# ==================== Integration Tests ====================


def test_full_config_structure():
    """Test complete configuration structure from Config down to TargetStatus."""
    config = Config(
        repos=[
            RepoConfig(
                name="production-app",
                url="git@github.com:company/app.git",
                auth_method="ssh",
                ssh_key_path="/home/deploy/.ssh/id_rsa",
                registries=[
                    RegistryConfig(
                        url="ghcr.io", username="deploy-bot", password_env_var="GHCR_TOKEN"
                    )
                ],
                branches=[
                    BranchConfig(
                        name="main",
                        sync_enabled=True,
                        targets=[
                            ComposeTarget(
                                name="web", file="compose.web.yml", deploy=True, build_images=True
                            ),
                            ComposeTarget(
                                name="api", file="compose.api.yml", deploy=True, build_images=False
                            ),
                        ],
                    ),
                    BranchConfig(
                        name="staging",
                        sync_enabled=False,
                        targets=[ComposeTarget(name="test", file="compose.test.yml", deploy=False)],
                    ),
                ],
            )
        ]
    )

    # Verify structure
    assert len(config.repos) == 1
    repo = config.repos[0]
    assert repo.name == "production-app"
    assert repo.auth_method == "ssh"
    assert len(repo.registries) == 1
    assert len(repo.branches) == 2

    main_branch = repo.branches[0]
    assert main_branch.name == "main"
    assert main_branch.sync_enabled is True
    assert len(main_branch.targets) == 2

    web_target = main_branch.targets[0]
    assert web_target.name == "web"
    assert web_target.deploy is True
    assert web_target.build_images is True


def test_full_status_structure():
    """Test complete status structure from RepoStatus down to TargetStatus."""
    now = datetime.now()

    status = RepoStatus(
        repo_name="app",
        branches={
            "main": BranchStatus(
                branch_name="main",
                last_check_time=now,
                commit_hash="abc123",
                sync_status="idle",
                targets={
                    "web": TargetStatus(
                        name="web",
                        last_deploy_time=now,
                        status="success",
                        message="Deployed v1.2.3",
                    ),
                    "api": TargetStatus(
                        name="api",
                        last_deploy_time=now,
                        status="success",
                        message="Deployed v1.2.3",
                    ),
                },
            )
        },
    )

    # Verify structure
    assert status.repo_name == "app"
    assert "main" in status.branches

    main = status.branches["main"]
    assert main.commit_hash == "abc123"
    assert len(main.targets) == 2

    web = main.targets["web"]
    assert web.status == "success"
    assert web.last_deploy_time == now

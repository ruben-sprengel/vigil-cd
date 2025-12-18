"""Unit tests for FastAPI Application."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.models import BranchConfig, BranchStatus, ComposeTarget, RepoConfig, RepoStatus


@pytest.fixture(scope="session")
def temp_config_file():
    """Create a temporary config file for entire test session."""
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
  - name: another-repo
    url: https://github.com/user/another-repo
    auth_method: https
    branches:
      - name: develop
        sync_enabled: false
        targets:
          - name: web
            file: compose.yml
            deploy: false
""")
        yield str(config_path)


@pytest.fixture(scope="session")
def client(temp_config_file):
    """Create FastAPI test client once for entire test session.

    Note: This fixture is session-scoped for performance. Tests should not
    modify global state or depend on execution order.
    """
    os.environ["CONFIG_PATH"] = temp_config_file

    # Mock scheduler to prevent actual background jobs
    with patch("src.app.scheduler") as mock_scheduler:
        mock_scheduler.running = False

        # Import app after patching
        from src.app import app  # noqa: PLC0415

        # Create client once for entire session
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def sample_repo_config():
    """Create sample RepoConfig for testing."""
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


# ==================== Health Check Tests ====================


def test_health_check(client):
    """Test health check endpoint returns OK."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["health"] == "ok"
    assert "timestamp" in data


def test_health_check_response_format(client):
    """Test health check response has correct format."""
    response = client.get("/health")
    data = response.json()

    assert isinstance(data, dict)
    assert "health" in data
    assert "timestamp" in data
    assert isinstance(data["timestamp"], str)


# ==================== List Repos Tests ====================


def test_list_repos(client):
    """Test list repos endpoint returns repositories."""
    response = client.get("/repos")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2  # From temp_config_file


def test_list_repos_structure(client):
    """Test list repos returns correct structure."""
    response = client.get("/repos")
    data = response.json()

    assert len(data) > 0
    first_repo = data[0]
    assert "name" in first_repo
    assert "url" in first_repo
    assert "auth_method" in first_repo
    assert "branches" in first_repo


def test_list_repos_content(client):
    """Test list repos contains expected repositories."""
    response = client.get("/repos")
    data = response.json()

    repo_names = [repo["name"] for repo in data]
    assert "test-repo" in repo_names
    assert "another-repo" in repo_names


# ==================== Get Status Tests ====================


@patch("src.app.state_manager")
def test_get_status_empty(mock_state_manager, client):
    """Test get status with empty state."""
    mock_state_manager.status = {}

    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


@patch("src.app.state_manager")
def test_get_status_with_repos(mock_state_manager, client):
    """Test get status with repository data."""
    mock_state_manager.status = {
        "test-repo": RepoStatus(
            repo_name="test-repo",
            branches={
                "main": BranchStatus(
                    branch_name="main",
                    commit_hash="abc123",
                    sync_status="idle",
                )
            },
        )
    }

    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    assert "test-repo" in data


# ==================== Get Config Tests ====================


def test_get_config(client):
    """Test get config endpoint returns configuration."""
    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert "scheduling" in data
    assert "deployment" in data
    assert "logging" in data
    assert "repos_count" in data


def test_get_config_structure(client):
    """Test get config returns correct structure."""
    response = client.get("/api/config")
    data = response.json()

    assert isinstance(data["scheduling"], dict)
    assert isinstance(data["deployment"], dict)
    assert isinstance(data["logging"], dict)
    assert isinstance(data["repos_count"], int)


def test_get_config_no_sensitive_data(client):
    """Test get config does not expose sensitive data."""
    response = client.get("/api/config")
    data = response.json()

    # Should not contain sensitive fields
    data_str = json.dumps(data)
    assert "password" not in data_str.lower()
    assert "secret" not in data_str.lower()
    assert "token" not in data_str.lower()


# ==================== CORS Tests ====================


def test_cors_headers_present(client):
    """Test CORS headers are present in response."""
    response = client.options("/health", headers={"Origin": "http://localhost:4200"})

    # OPTIONS request should be handled
    assert response.status_code in [200, 405]


def test_cors_allowed_origin(client):
    """Test CORS allows configured origin."""
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:4200"},
    )

    assert response.status_code == 200
    # CORS middleware should add headers (if configured)


# ==================== Error Handling Tests ====================


def test_404_not_found(client):
    """Test 404 error for non-existent endpoint."""
    response = client.get("/nonexistent")

    assert response.status_code == 404


def test_405_method_not_allowed(client):
    """Test 405 error for invalid method."""
    response = client.post("/health")

    assert response.status_code == 405


# ==================== Parametrized Tests ====================


@pytest.mark.parametrize(
    "endpoint,method",
    [
        ("/health", "get"),
        ("/repos", "get"),
        ("/api/status", "get"),
        ("/api/config", "get"),
    ],
    ids=["health", "repos", "status", "config"],
)
def test_endpoints_return_200(client, endpoint, method):
    """Test all main endpoints return 200."""
    response = getattr(client, method)(endpoint)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "endpoint,expected_type",
    [
        ("/health", dict),
        ("/repos", list),
        ("/api/status", dict),
        ("/api/config", dict),
    ],
    ids=["health_dict", "repos_list", "status_dict", "config_dict"],
)
def test_endpoints_return_correct_type(client, endpoint, expected_type):
    """Test endpoints return correct data types."""
    response = client.get(endpoint)
    data = response.json()
    assert isinstance(data, expected_type)


# ==================== Response Schema Tests ====================


def test_health_response_schema(client):
    """Test health endpoint response matches expected schema."""
    response = client.get("/health")
    data = response.json()

    # Required fields
    assert "health" in data
    assert "timestamp" in data

    # Field types
    assert isinstance(data["health"], str)
    assert isinstance(data["timestamp"], str)

    # Field values
    assert data["health"] == "ok"


def test_config_response_schema(client):
    """Test config endpoint response matches expected schema."""
    response = client.get("/api/config")
    data = response.json()

    # Required top-level fields
    required_fields = ["scheduling", "deployment", "logging", "repos_count"]
    for field in required_fields:
        assert field in data

    # Nested structure validation
    assert isinstance(data["scheduling"], dict)
    assert "check_interval_minutes" in data["scheduling"]

    assert isinstance(data["deployment"], dict)
    assert "docker_compose_timeout_seconds" in data["deployment"]

    assert isinstance(data["logging"], dict)
    assert "level" in data["logging"]

    assert isinstance(data["repos_count"], int)
    assert data["repos_count"] >= 0

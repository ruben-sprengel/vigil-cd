"""Shared pytest fixtures and configuration for optimal performance."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ==================== Session-Scoped Fixtures ====================


@pytest.fixture(scope="session")
def temp_config_dir():
    """Create a temporary directory for config files (session-scoped)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="session")
def session_config_file(temp_config_dir):
    """Create config file once for entire test session."""
    config_path = temp_config_dir / "config.yaml"
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
    return str(config_path)


@pytest.fixture(scope="session")
def basic_config_content():
    """Basic valid config content for testing config manager."""
    return {
        "repos": [
            {
                "name": "test-repo",
                "url": "https://github.com/user/test-repo",
                "auth_method": "https",
                "branches": [
                    {
                        "name": "main",
                        "sync_enabled": True,
                        "targets": [
                            {
                                "name": "srv",
                                "file": "docker-compose.yml",
                                "deploy": True,
                                "build_images": False,
                            }
                        ],
                    }
                ],
            }
        ]
    }


@pytest.fixture(scope="session")
def app_instance(session_config_file):
    """Create FastAPI app instance once for entire session."""
    os.environ["CONFIG_PATH"] = session_config_file

    # Mock scheduler to prevent background jobs
    with patch("src.app.scheduler") as mock_scheduler:
        mock_scheduler.running = False

        # Import app after env setup
        from src.app import app  # noqa: PLC0415

        yield app


@pytest.fixture(scope="session")
def client(app_instance):
    """Create TestClient once for entire session.

    This is the main performance optimization - creates client only once
    instead of for every test.

    WARNING: Tests using this fixture should not modify global state!
    """
    with TestClient(app_instance) as test_client:
        yield test_client


# ==================== Function-Scoped Fixtures ====================


@pytest.fixture
def temp_status_file(monkeypatch, tmp_path):
    """Create temporary status file (per-test isolation)."""
    status_file = tmp_path / "test_status.json"
    monkeypatch.setattr("src.state.STATUS_FILE", str(status_file))
    return status_file


@pytest.fixture
def mock_state_manager():
    """Mock state manager for tests that modify state."""
    with patch("src.app.state_manager") as mock:
        mock.status = {}
        yield mock


@pytest.fixture
def mock_service():
    """Mock deployment service for tests."""
    with patch("src.app.service") as mock:
        yield mock


# ==================== Module-Scoped Fixtures ====================


@pytest.fixture(scope="module")
def module_temp_dir():
    """Temporary directory shared across module tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="module")
def base_temp_repo(module_temp_dir):
    """Base temporary directory for docker_env_validator tests.

    Module-scoped for performance. Each test gets a subdirectory
    for isolation while sharing the base temp directory.
    """
    return module_temp_dir


@pytest.fixture
def temp_repo(base_temp_repo, request):
    """Create isolated subdirectory for each test.

    Uses module-scoped base directory but creates unique subdirectory
    per test for isolation. Cleanup happens automatically when module
    finishes.

    This gives us:
    - Fast: Base dir created once per module
    - Isolated: Each test has own subdirectory
    - Clean: Auto cleanup after module
    """
    test_name = request.node.name
    test_dir = base_temp_repo / test_name
    test_dir.mkdir(exist_ok=True)
    return test_dir


# ==================== Autouse Fixtures ====================


@pytest.fixture(autouse=True)
def reset_mocks():
    """Automatically reset mocks after each test."""
    yield
    # Cleanup happens here automatically


# ==================== Performance Markers ====================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "fast: mark test as fast running")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")


# ==================== Performance Reporting ====================


@pytest.fixture(scope="session", autouse=True)
def performance_report(request):
    """Print performance summary after test session."""
    start = time.time()

    yield

    duration = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"Total test session duration: {duration:.2f}s")
    print(f"{'=' * 60}")

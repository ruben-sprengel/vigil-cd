"""Unit tests for State Manager."""

import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.models import RepoStatus
from src.state import StateManager


@pytest.fixture
def temp_status_file(monkeypatch):
    """Create a temporary status file and clean it up after test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_file = Path(tmpdir) / "test_status.json"
        monkeypatch.setattr("src.state.STATUS_FILE", str(status_file))
        yield status_file


@pytest.fixture
def state_manager():
    """Create a fresh StateManager instance."""
    manager = StateManager()
    manager.status = {}  # Reset status
    manager._listeners = []  # Reset listeners
    return manager


def test_init_state_manager():
    """Test StateManager initialization."""
    manager = StateManager()

    assert manager.status == {}
    assert manager._listeners == []


def test_get_repo_status_new_repo(state_manager):
    """Test getting status for a new repository."""
    repo_status = state_manager.get_repo_status("test-repo")

    assert isinstance(repo_status, RepoStatus)
    assert repo_status.repo_name == "test-repo"
    assert repo_status.branches == {}
    assert "test-repo" in state_manager.status


def test_get_repo_status_existing_repo(state_manager):
    """Test getting status for an existing repository."""
    # Create repo first
    state_manager.status["test-repo"] = RepoStatus(repo_name="test-repo")

    repo_status = state_manager.get_repo_status("test-repo")

    assert repo_status.repo_name == "test-repo"
    assert state_manager.status["test-repo"] is repo_status


def test_update_branch_new_branch(state_manager, temp_status_file):
    """Test updating a new branch status."""
    state_manager.update_branch("test-repo", "main", sync_status="checking", commit_hash="abc1234")

    repo = state_manager.status["test-repo"]
    branch = repo.branches["main"]

    assert branch.branch_name == "main"
    assert branch.sync_status == "checking"
    assert branch.commit_hash == "abc1234"


def test_update_branch_existing_branch(state_manager, temp_status_file):
    """Test updating an existing branch status."""
    # Create initial branch
    state_manager.update_branch("test-repo", "main", sync_status="idle")

    # Update it
    state_manager.update_branch("test-repo", "main", sync_status="pulling", commit_hash="def5678")

    repo = state_manager.status["test-repo"]
    branch = repo.branches["main"]

    assert branch.sync_status == "pulling"
    assert branch.commit_hash == "def5678"


@pytest.mark.parametrize(
    "field,value",
    [
        ("sync_status", "checking"),
        ("sync_status", "pulling"),
        ("sync_status", "idle"),
        ("sync_status", "error"),
        ("commit_hash", "abc1234"),
        ("commit_hash", "def5678"),
        ("last_check_time", datetime.now()),
    ],
    ids=[
        "status_checking",
        "status_pulling",
        "status_idle",
        "status_error",
        "hash_1",
        "hash_2",
        "timestamp",
    ],
)
def test_update_branch_various_fields(state_manager, temp_status_file, field, value):
    """Test updating various branch fields using parametrize."""
    state_manager.update_branch("test-repo", "main", **{field: value})

    branch = state_manager.status["test-repo"].branches["main"]

    assert getattr(branch, field) == value


def test_update_target_new_target(state_manager, temp_status_file):
    """Test updating a new target status."""
    # Create branch first
    state_manager.update_branch("test-repo", "main", sync_status="idle")

    state_manager.update_target(
        "test-repo", "main", "srv", status="deploying", message="Starting deployment"
    )

    target = state_manager.status["test-repo"].branches["main"].targets["srv"]

    assert target.name == "srv"
    assert target.status == "deploying"
    assert target.message == "Starting deployment"


def test_update_target_existing_target(state_manager, temp_status_file):
    """Test updating an existing target status."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")
    state_manager.update_target("test-repo", "main", "srv", status="deploying")

    # Update to success
    state_manager.update_target("test-repo", "main", "srv", status="success", message="Deployed")

    target = state_manager.status["test-repo"].branches["main"].targets["srv"]

    assert target.status == "success"
    assert target.message == "Deployed"
    assert target.last_deploy_time is not None


def test_update_target_success_sets_timestamp(state_manager, temp_status_file):
    """Test that successful deployment sets last_deploy_time."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")

    before = datetime.now()
    state_manager.update_target("test-repo", "main", "srv", status="success")
    after = datetime.now()

    target = state_manager.status["test-repo"].branches["main"].targets["srv"]

    assert target.last_deploy_time is not None
    assert before <= target.last_deploy_time <= after


def test_update_target_non_success_no_timestamp(state_manager, temp_status_file):
    """Test that non-success status doesn't update timestamp."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")

    state_manager.update_target("test-repo", "main", "srv", status="error", message="Failed")

    target = state_manager.status["test-repo"].branches["main"].targets["srv"]

    assert target.status == "error"
    assert target.last_deploy_time is None


@pytest.mark.parametrize(
    "status,message",
    [
        ("pending", "Waiting for deployment"),
        ("deploying", "In progress..."),
        ("success", "Deployment successful"),
        ("error", "Deployment failed"),
        ("skipped", "Deploy disabled"),
    ],
    ids=["pending", "deploying", "success", "error", "skipped"],
)
def test_update_target_various_statuses(state_manager, temp_status_file, status, message):
    """Test updating target with various status values."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")
    state_manager.update_target("test-repo", "main", "srv", status=status, message=message)

    target = state_manager.status["test-repo"].branches["main"].targets["srv"]

    assert target.status == status
    assert target.message == message


def test_update_target_nonexistent_branch(state_manager, temp_status_file):
    """Test updating target for a branch that doesn't exist."""
    # Should not raise error, but also not create target
    state_manager.update_target("test-repo", "nonexistent", "srv", status="error")

    repo = state_manager.status.get("test-repo")
    if repo:
        branch = repo.branches.get("nonexistent")
        assert branch is None


def test_save_status(state_manager, temp_status_file):
    """Test saving status to file."""
    state_manager.update_branch("test-repo", "main", sync_status="idle", commit_hash="abc123")

    assert temp_status_file.exists()

    with open(temp_status_file) as f:
        data = json.load(f)

    assert "test-repo" in data
    assert data["test-repo"]["repo_name"] == "test-repo"
    assert "main" in data["test-repo"]["branches"]
    assert data["test-repo"]["branches"]["main"]["commit_hash"] == "abc123"


def test_load_status_file_exists(state_manager, temp_status_file):
    """Test loading status from existing file."""
    # Create status file with data
    status_data = {
        "test-repo": {
            "repo_name": "test-repo",
            "branches": {
                "main": {
                    "branch_name": "main",
                    "sync_status": "idle",
                    "commit_hash": "abc123",
                    "last_check_time": None,
                    "targets": {},
                }
            },
        }
    }

    with open(temp_status_file, "w") as f:
        json.dump(status_data, f)

    state_manager.load_status()

    assert "test-repo" in state_manager.status
    assert state_manager.status["test-repo"].repo_name == "test-repo"
    assert "main" in state_manager.status["test-repo"].branches
    assert state_manager.status["test-repo"].branches["main"].commit_hash == "abc123"


def test_load_status_file_not_exists(state_manager, temp_status_file):
    """Test loading status when file doesn't exist."""
    # Ensure file doesn't exist
    if temp_status_file.exists():
        temp_status_file.unlink()

    state_manager.load_status()

    assert state_manager.status == {}


def test_load_status_invalid_json(state_manager, temp_status_file, caplog):
    """Testet das Laden des Status aus einer Datei mit ungültigem JSON."""
    temp_status_file.write_text("{ invalid json content")

    # Wir setzen das Log-Level auf ERROR, damit caplog es erfasst
    with caplog.at_level(logging.ERROR):
        state_manager.load_status()

    # Status muss nach Fehler leer sein
    assert state_manager.status == {}

    # Prüfen, ob eine Fehlermeldung im Log erscheint
    # logger.exception erzeugt einen ERROR-Level Log-Eintrag
    assert any(
        "Error loading status" in record.message
        for record in caplog.records
        if record.levelno == logging.ERROR
    )


def test_load_status_invalid_structure(state_manager, temp_status_file, caplog):
    """Testet das Laden des Status mit gültigem JSON, aber ungültiger Struktur."""
    temp_status_file.write_text('{"invalid": "structure"}')

    with caplog.at_level(logging.ERROR):
        state_manager.load_status()

    assert state_manager.status == {}

    assert any(
        "Error loading status" in record.message
        for record in caplog.records
        if record.levelno == logging.ERROR
    )


def test_to_json_serializable(state_manager):
    """Test converting status to JSON-serializable format."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")
    state_manager.update_target("test-repo", "main", "srv", status="success")

    json_data = state_manager._to_json_serializable()

    assert isinstance(json_data, dict)
    assert "test-repo" in json_data
    assert "branches" in json_data["test-repo"]

    # Should be JSON serializable
    json_str = json.dumps(json_data, default=str)
    assert isinstance(json_str, str)


def test_notify_listeners(state_manager):
    """Test notifying SSE listeners."""
    queue1 = asyncio.Queue()
    queue2 = asyncio.Queue()

    state_manager._listeners = [queue1, queue2]
    state_manager.update_branch("test-repo", "main", sync_status="idle")

    # Listeners should have received notification
    assert not queue1.empty()
    assert not queue2.empty()

    data1 = queue1.get_nowait()
    data2 = queue2.get_nowait()

    assert data1 == data2
    assert "test-repo" in data1


def test_notify_listeners_with_json_data(state_manager):
    """Test that notification contains valid JSON."""
    queue = asyncio.Queue()
    state_manager._listeners = [queue]

    state_manager.update_branch("test-repo", "main", sync_status="checking")

    data = queue.get_nowait()
    parsed = json.loads(data)

    assert "test-repo" in parsed
    assert parsed["test-repo"]["branches"]["main"]["sync_status"] == "checking"


@pytest.mark.asyncio
async def test_stream_initial_data(state_manager):
    """Test SSE stream sends initial data."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")

    stream = state_manager.stream()
    initial = await stream.__anext__()

    assert initial.startswith("data: ")
    assert "test-repo" in initial


@pytest.mark.asyncio
async def test_stream_updates(state_manager):
    """Test SSE stream sends updates."""
    stream = state_manager.stream()

    # Get initial data
    await stream.__anext__()

    # Trigger update
    state_manager.update_branch("test-repo", "main", sync_status="pulling")

    # Get update
    update = await asyncio.wait_for(stream.__anext__(), timeout=1.0)

    assert update.startswith("data: ")
    assert "pulling" in update


@pytest.mark.asyncio
async def test_stream_cleanup_on_cancel(state_manager):
    """Test that stream cleanup works on task cancellation."""

    async def consume_stream():
        """Consumer that processes stream updates."""
        async for _ in state_manager.stream():
            pass  # Process indefinitely until cancelled

    # Create and start the task
    task = asyncio.create_task(consume_stream())
    await asyncio.sleep(0.05)  # Let the stream initialize

    assert len(state_manager._listeners) == 1

    # Cancel the task (simulates client disconnect)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Give a moment for cleanup to complete
    await asyncio.sleep(0.01)

    # Listener should be removed after cancellation
    assert len(state_manager._listeners) == 0


@pytest.mark.asyncio
async def test_stream_listener_management(state_manager):
    """Test that listeners are properly added and can be tracked."""
    # Start multiple streams
    stream1 = state_manager.stream()
    stream2 = state_manager.stream()
    stream3 = state_manager.stream()

    # Get initial data from all streams
    await stream1.__anext__()
    await stream2.__anext__()
    await stream3.__anext__()

    # All three listeners should be registered
    assert len(state_manager._listeners) == 3

    # Manual cleanup for this test
    state_manager._listeners.clear()


@pytest.mark.asyncio
async def test_stream_multiple_listeners(state_manager):
    """Test multiple SSE listeners receiving updates."""
    stream1 = state_manager.stream()
    stream2 = state_manager.stream()

    # Get initial data from both streams
    await stream1.__anext__()
    await stream2.__anext__()

    assert len(state_manager._listeners) == 2

    # Trigger update
    state_manager.update_branch("test-repo", "main", sync_status="pulling")

    # Both streams should receive the update
    update1 = await asyncio.wait_for(stream1.__anext__(), timeout=1.0)
    update2 = await asyncio.wait_for(stream2.__anext__(), timeout=1.0)

    assert "pulling" in update1
    assert "pulling" in update2


def test_multiple_repos(state_manager, temp_status_file):
    """Test managing status for multiple repositories."""
    state_manager.update_branch("repo1", "main", sync_status="idle")
    state_manager.update_branch("repo2", "develop", sync_status="checking")
    state_manager.update_branch("repo3", "staging", sync_status="pulling")

    assert len(state_manager.status) == 3
    assert "repo1" in state_manager.status
    assert "repo2" in state_manager.status
    assert "repo3" in state_manager.status


def test_multiple_branches_same_repo(state_manager, temp_status_file):
    """Test managing multiple branches in the same repository."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")
    state_manager.update_branch("test-repo", "develop", sync_status="checking")
    state_manager.update_branch("test-repo", "staging", sync_status="pulling")

    repo = state_manager.status["test-repo"]

    assert len(repo.branches) == 3
    assert "main" in repo.branches
    assert "develop" in repo.branches
    assert "staging" in repo.branches


def test_multiple_targets_same_branch(state_manager, temp_status_file):
    """Test managing multiple targets in the same branch."""
    state_manager.update_branch("test-repo", "main", sync_status="idle")
    state_manager.update_target("test-repo", "main", "web", status="success")
    state_manager.update_target("test-repo", "main", "worker", status="deploying")
    state_manager.update_target("test-repo", "main", "cron", status="skipped")

    branch = state_manager.status["test-repo"].branches["main"]

    assert len(branch.targets) == 3
    assert branch.targets["web"].status == "success"
    assert branch.targets["worker"].status == "deploying"
    assert branch.targets["cron"].status == "skipped"


def test_complex_state(state_manager, temp_status_file):
    """Test complex state with multiple repos, branches, and targets."""
    # Repo 1: 2 branches, each with 2 targets
    state_manager.update_branch("repo1", "main", sync_status="idle")
    state_manager.update_target("repo1", "main", "web", status="success")
    state_manager.update_target("repo1", "main", "api", status="success")

    state_manager.update_branch("repo1", "develop", sync_status="checking")
    state_manager.update_target("repo1", "develop", "web", status="deploying")
    state_manager.update_target("repo1", "develop", "api", status="pending")

    # Repo 2: 1 branch, 1 target
    state_manager.update_branch("repo2", "main", sync_status="error")
    state_manager.update_target("repo2", "main", "srv", status="error", message="Failed")

    assert len(state_manager.status) == 2
    assert len(state_manager.status["repo1"].branches) == 2
    assert len(state_manager.status["repo1"].branches["main"].targets) == 2
    assert state_manager.status["repo2"].branches["main"].targets["srv"].status == "error"


def test_persistence_across_instances(temp_status_file):
    """Test that status persists across StateManager instances."""
    # First instance
    manager1 = StateManager()
    manager1.update_branch("test-repo", "main", sync_status="idle", commit_hash="abc123")

    # Second instance loads the saved data
    manager2 = StateManager()
    manager2.load_status()

    assert "test-repo" in manager2.status
    assert manager2.status["test-repo"].branches["main"].commit_hash == "abc123"

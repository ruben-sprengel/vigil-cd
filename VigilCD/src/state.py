"""State management."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from src.models import BranchStatus, RepoStatus, TargetStatus

logger = logging.getLogger(__name__)

STATUS_FILE = "vigilcd_status.json"


class StateManager:
    """Manages the application state, including loading/saving status and notifying SSE clients."""

    def __init__(self) -> None:
        """Init the StateManager."""
        self.status: dict[str, RepoStatus] = {}
        self._listeners: list[asyncio.Queue] = []

    def get_repo_status(self, repo_name: str) -> RepoStatus:
        """Gets the RepoStatus for a given repository, creating it if it doesn't exist.

        Args:
            repo_name (str): The name of the repository.

        Returns:
            RepoStatus: The status object for the repository.

        """
        if repo_name not in self.status:
            self.status[repo_name] = RepoStatus(repo_name=repo_name)
        return self.status[repo_name]

    def _to_json_serializable(self) -> dict[str, Any]:
        """Converts the current status to a JSON-serializable dict.

        Returns:
            dict: JSON-serializable representation of the status.
        """
        data = {k: v.model_dump() for k, v in self.status.items()}
        return data

    def _save_status(self) -> None:
        """Saves the current status to a JSON file."""
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._to_json_serializable(), f, default=str, indent=4)
        except Exception:
            logger.exception("Error saving status")

    def load_status(self) -> None:
        """Loads the status from a JSON file, if it exists."""
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, encoding="utf-8") as f:
                    data = json.load(f)

                loaded_status = {}
                for repo_name, repo_data in data.items():
                    loaded_status[repo_name] = RepoStatus(**repo_data)

                self.status = loaded_status
            except Exception:
                logger.exception("Error loading status. Starting with empty status.")
                self.status = {}

    def update_branch(self, repo_name: str, branch_name: str, **kwargs: Any) -> None:
        """Updates a specific branch status with given attributes."""
        r_status = self.get_repo_status(repo_name)

        if branch_name not in r_status.branches:
            r_status.branches[branch_name] = BranchStatus(branch_name=branch_name)

        b_status = r_status.branches[branch_name]
        for key, value in kwargs.items():
            if hasattr(b_status, key):
                setattr(b_status, key, value)

        self.notify_listeners(repo_name)
        self._save_status()

    def update_target(
        self,
        repo_name: str,
        branch_name: str,
        target_name: str,
        status: str,
        message: str = "",
    ) -> None:
        """Updates the status of a specific deployment target."""
        r_status = self.get_repo_status(repo_name)
        b_status = r_status.branches.get(branch_name)
        if not b_status:
            return

        if target_name not in b_status.targets:
            b_status.targets[target_name] = TargetStatus(name=target_name)

        t_status = b_status.targets[target_name]
        t_status.status = status
        t_status.message = message
        if status == "success":
            t_status.last_deploy_time = datetime.now()

        self.notify_listeners(repo_name)
        self._save_status()

    def notify_listeners(self, changed_repo: str) -> None:
        """Notifies all SSE listeners about a state change."""
        data = self._to_json_serializable()
        json_data = json.dumps(data, default=str)

        for queue in self._listeners:
            queue.put_nowait(json_data)

    async def stream(self) -> AsyncGenerator[str, None]:
        """Generator für SSE."""
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.append(queue)

        initial_data = json.dumps(self._to_json_serializable(), default=str)
        yield f"data: {initial_data}\n\n"

        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        finally:
            if queue in self._listeners:
                self._listeners.remove(queue)


state_manager = StateManager()

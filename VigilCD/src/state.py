"""State management."""

import asyncio
import json
import os
from datetime import datetime

from src.models import BranchStatus, RepoStatus, TargetStatus  # Importe aus models.py

STATUS_FILE = "vigilcd_status.json"


class StateManager:
    """Manages the application state, including loading/saving status and notifying SSE clients."""

    def __init__(self):
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

    def _to_json_serializable(self) -> dict:
        """Converts the current status to a JSON-serializable dict.

        Args:
            None
        Returns:
            dict: JSON-serializable representation of the status.
        """
        data = {k: v.dict() for k, v in self.status.items()}
        return data

    def _save_status(self) -> None:
        """Saves the current status to a JSON file."""
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._to_json_serializable(), f, default=str, indent=4)
            # Hinweis: logger nutzen, falls in state.py vorhanden
            print(f"Status erfolgreich gespeichert in {STATUS_FILE}")
        except Exception as e:
            print(f"FEHLER beim Speichern des Status: {e}")

    def load_status(self) -> None:
        """Loads the status from a JSON file, if it exists."""
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, encoding="utf-8") as f:
                    data = json.load(f)

                # Deserialisierung der geladenen Daten zurück in Pydantic Modelle
                loaded_status = {}
                for repo_name, repo_data in data.items():
                    loaded_status[repo_name] = RepoStatus(**repo_data)

                self.status = loaded_status
                print(f"Status erfolgreich aus {STATUS_FILE} geladen.")
            except Exception as e:
                print(
                    f"FEHLER beim Laden oder Deserialisieren des Status: {e}. Startet mit leerem Status."
                )
                self.status = {}
        else:
            print(f"Keine Statusdatei ({STATUS_FILE}) gefunden. Startet mit leerem Status.")

    # Anpassung: Speichern nach jeder Status-Änderung
    def update_branch(self, repo_name: str, branch_name: str, **kwargs) -> None:
        """Updates a specific branch status with given attributes.

        Args:
            repo_name (str): The name of the repository.
            branch_name (str): The name of the branch.
            **kwargs: Attributes to update in the BranchStatus.

        Returns:
            None
        """
        r_status = self.get_repo_status(repo_name)

        if branch_name not in r_status.branches:
            r_status.branches[branch_name] = BranchStatus(branch_name=branch_name)

        b_status = r_status.branches[branch_name]
        for key, value in kwargs.items():
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
        """Updates the status of a specific deployment target.

        Args:
            repo_name (str): The name of the repository.
            branch_name (str): The name of the branch.
            target_name (str): The name of the deployment target.
            status (str): The new status ('pending', 'success', 'error', 'skipped').
            message (str, optional): Additional message. Defaults to "".

        Returns:
            None

        """
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
        """Notifies all SSE listeners about a state change.

        Args:
            changed_repo (str): The name of the repository that changed.

        Returns:
            None
        """
        data = {k: v.dict() for k, v in self.status.items()}
        json_data = json.dumps(data, default=str)

        for queue in self._listeners:
            queue.put_nowait(json_data)

    async def stream(self):
        """Generator für SSE."""
        queue = asyncio.Queue()
        self._listeners.append(queue)

        initial_data = json.dumps({k: v.dict() for k, v in self.status.items()}, default=str)
        yield f"data: {initial_data}\n\n"

        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            self._listeners.remove(queue)


state_manager = StateManager()

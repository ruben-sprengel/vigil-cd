import asyncio
import json
import os
from typing import Dict
from datetime import datetime
from src.models import RepoStatus, BranchStatus, TargetStatus # Importe aus models.py

# Pfad zur Statusdatei – WICHTIG: Muss in einem Docker Volume liegen!
STATUS_FILE = "vigilcd_status.json"

class StateManager:
    def __init__(self):
        self.status: Dict[str, RepoStatus] = {}
        self._listeners: list[asyncio.Queue] = []

    def get_repo_status(self, repo_name: str) -> RepoStatus:
        if repo_name not in self.status:
            self.status[repo_name] = RepoStatus(repo_name=repo_name)
        return self.status[repo_name]

    def _to_json_serializable(self) -> Dict:
        """Konvertiert den Status in ein JSON-serialisierbares Dict (inkl. Datumsformatierung)."""
        data = {k: v.dict() for k, v in self.status.items()}
        # Pydantic dict() kümmert sich um die meisten BaseModel-Konvertierungen
        return data

    def _save_status(self):
        """Speichert den aktuellen Status in einer JSON-Datei."""
        try:
            with open(STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._to_json_serializable(), f, default=str, indent=4)
            # Hinweis: logger nutzen, falls in state.py vorhanden
            print(f"Status erfolgreich gespeichert in {STATUS_FILE}")
        except Exception as e:
            print(f"FEHLER beim Speichern des Status: {e}")

    def load_status(self):
        """Lädt den Status aus der JSON-Datei beim Start."""
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Deserialisierung der geladenen Daten zurück in Pydantic Modelle
                loaded_status = {}
                for repo_name, repo_data in data.items():
                    loaded_status[repo_name] = RepoStatus(**repo_data)

                self.status = loaded_status
                print(f"Status erfolgreich aus {STATUS_FILE} geladen.")
            except Exception as e:
                print(f"FEHLER beim Laden oder Deserialisieren des Status: {e}. Startet mit leerem Status.")
                self.status = {}
        else:
            print(f"Keine Statusdatei ({STATUS_FILE}) gefunden. Startet mit leerem Status.")

    # Anpassung: Speichern nach jeder Status-Änderung
    def update_branch(self, repo_name: str, branch_name: str, **kwargs):
        """Aktualisiert Branch-Infos und benachrichtigt Clients"""
        r_status = self.get_repo_status(repo_name)

        if branch_name not in r_status.branches:
            r_status.branches[branch_name] = BranchStatus(branch_name=branch_name)

        # Update attributes
        b_status = r_status.branches[branch_name]
        for key, value in kwargs.items():
            setattr(b_status, key, value)

        self.notify_listeners(repo_name)
        self._save_status() # NEU: Status nach Update speichern

    def update_target(self, repo_name: str, branch_name: str, target_name: str, status: str, message: str = ""):
        """Aktualisiert einen spezifischen Docker-Target Status"""
        r_status = self.get_repo_status(repo_name)
        b_status = r_status.branches.get(branch_name)
        if not b_status: return

        if target_name not in b_status.targets:
            b_status.targets[target_name] = TargetStatus(name=target_name)

        t_status = b_status.targets[target_name]
        t_status.status = status
        t_status.message = message
        if status == "success":
            t_status.last_deploy_time = datetime.now()

        self.notify_listeners(repo_name)
        self._save_status() # NEU: Status nach Update speichern

    def notify_listeners(self, changed_repo: str):
        """Sendet Update an alle SSE Clients"""
        # Wir senden einfach den kompletten State als JSON Dump
        # Für sehr große Systeme würde man nur Diffs senden, hier reicht Full State.
        data = {k: v.dict() for k, v in self.status.items()}
        # Konvertierung datetime zu string passiert im json encoder,
        # hier vereinfacht wir machen pydantic json dump
        json_data = json.dumps(data, default=str)

        for queue in self._listeners:
            queue.put_nowait(json_data)

    async def stream(self):
        """Generator für SSE"""
        queue = asyncio.Queue()
        self._listeners.append(queue)

        # Initial State senden
        initial_data = json.dumps({k: v.dict() for k, v in self.status.items()}, default=str)
        yield f"data: {initial_data}\n\n"

        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            self._listeners.remove(queue)

# Globale Instanz
state_manager = StateManager()
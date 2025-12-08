from datetime import datetime
import os
import logging
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.middleware.cors import CORSMiddleware
from src.models import Config
from src.service import DeploymentService
from src.config_manager import ConfigManager
from src.webhook_handler import GitHubWebhookHandler
from contextlib import asynccontextmanager
from src.state import state_manager


logger = logging.getLogger(__name__)


config_file = os.environ.get("CONFIG_PATH", "/home/vigilcd/src/config/config.yaml")
config_manager = ConfigManager(config_file=config_file)
logging.basicConfig(
    level=getattr(logging, config_manager.logging_config.level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


service = DeploymentService(config_manager)
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown Lifecycle für FastAPI App."""
    logger.info(f"Starting VigilCD with check interval: {config_manager.scheduling.check_interval_minutes} min")

    # Initial Sync Check
    scheduled_sync_job()

    # Register periodic job
    scheduler.add_job(
        scheduled_sync_job,
        'interval',
        minutes=config_manager.scheduling.check_interval_minutes,
        id='git_sync_check',
        name='Git Synchronization Check',
        max_instances=1
    )

    scheduler.start()
    logger.info("APScheduler started successfully")

    yield

    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shutdown completed")

app = FastAPI(lifespan=lifespan, title="VigilCD - GitOps Deployment Agent")

origins = [
    "http://localhost:4200",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



def scheduled_sync_job():
    """Die Funktion, die regelmäßig vom Scheduler aufgerufen wird."""
    logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] --- Starting scheduled sync check ---")

    for repo_data in config_manager.repos_config:
        repo_config = Config.parse_obj({"repos": [repo_data]}).repos[0]
        for branch in repo_config.branches:
            try:
                service.check_and_update(repo_config, branch)
            except Exception as e:
                logger.exception(f"Error in scheduled job for {repo_config.name}/{branch.name}: {e}")

@app.get("/repos")
def list_repos():
    """Gibt alle konfigurierten Repositories zurück."""
    return config_manager.repos_config


@app.get("/health")
def health_check():
    """
    Comprehensive health check endpoint.

    Returns:
        - status: ok/degraded/error
        - docker_daemon: running/unavailable
        - scheduler: running/stopped
        - last_check: timestamp of last scheduled check
        - repo_states: summary of repository states
    """
    # docker_available = service.is_docker_daemon_running()
    # scheduler_running = scheduler.running

    repo_states = {
        "total": 0,
        "syncing": 0,
        "error": 0,
        "idle": 0
    }

    # for repo_name, repo_data in state_manager.status.items():
    #     for branch_name, branch_data in repo_data.model_dump().items():
    #         repo_states["total"] += 1
    #         sync_status = branch_data.get("sync_status", "unknown")
    #         if sync_status in ["checking", "pulling"]:
    #             repo_states["syncing"] += 1
    #         elif sync_status == "error":
    #             repo_states["error"] += 1
    #         elif sync_status == "idle":
    #             repo_states["idle"] += 1
    #
    #
    # if not docker_available or not scheduler_running or repo_states["error"] > 0:
    #     overall_status = "degraded" if docker_available and scheduler_running else "error"
    # else:
    #     overall_status = "ok"

    return {
        # "status": overall_status,
        # "timestamp": datetime.now().isoformat(),
        # "services": {
        #     "docker_daemon": "running" if docker_available else "unavailable",
        #     "scheduler": "running" if scheduler_running else "stopped",
        # },
        "repositories": repo_states,
        # "config": {
        #     "check_interval_minutes": config_manager.scheduling.check_interval_minutes,
        #     "git_retry_count": config_manager.scheduling.git_retry_count,
        # }
    }


@app.get("/api/status")
def get_status():
    """Gibt den aktuellen Status aller Repos/Branches."""
    return state_manager.status


@app.get("/api/config")
def get_config():
    """Gibt nicht-sensitive Config-Werte zurück."""
    return {
        "scheduling": config_manager.scheduling.dict(),
        "deployment": config_manager.deployment.dict(),
        "logging": config_manager.logging_config.dict(),
        "repos_count": len(config_manager.repos_config),
    }


# @app.post("/api/repos/{repo_name}/branches/{branch_name}/deploy")
# def trigger_manual_deploy(repo_name: str, branch_name: str, background_tasks: BackgroundTasks):
#     """Triggert manuelles Deployment (optional mit Auth-Token später)."""
#     # Finde Repo und Branch in Config
#     repo_config = None
#     branch_config = None
#
#     for repo_data in config_manager.repos_config:
#         if repo_data.get("name") == repo_name:
#             repo_config = Config.parse_obj({"repos": [repo_data]}).repos[0]
#             for branch_data in repo_data.get("branches", []):
#                 if branch_data.get("name") == branch_name:
#                     branch_config = repo_config.branches[repo_config.branches.index(
#                         next(b for b in repo_config.branches if b.name == branch_name)
#                     )]
#                     break
#             break
#
#     if not repo_config or not branch_config:
#         raise HTTPException(status_code=404, detail="Repo/Branch not found")
#
#     # Starte Deployment im Hintergrund
#     background_tasks.add_task(service.check_and_update, repo_config, branch_config)
#
#     return {
#         "message": f"Manual deploy triggered for {repo_name}/{branch_name}",
#         "status": "processing"
#     }


@app.post("/webhooks/github")
async def github_webhook(
    request_body: bytes,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    """
    GitHub Webhook Endpoint für Event-Driven Deployments.

    Erwartete Header:
    - X-Hub-Signature-256: HMAC-SHA256 Signatur des Payloads
    - X-GitHub-Event: Event-Typ (push, pull_request, etc.)
    """
    # Signature verifizieren
    if not x_hub_signature_256:
        logger.error("Missing X-Hub-Signature-256 header")
        raise HTTPException(status_code=401, detail="Signature verification failed")

    if not GitHubWebhookHandler.verify_signature(request_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Nur Push-Events verarbeiten
    if x_github_event != "push":
        logger.debug(f"Ignoring non-push event: {x_github_event}")
        return {"status": "ignored", "reason": f"Event type: {x_github_event}"}

    try:
        payload = json.loads(request_body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.error("Failed to parse webhook payload JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Parse Push-Event
    event_info = GitHubWebhookHandler.parse_push_event(payload)
    if not event_info:
        raise HTTPException(status_code=400, detail="Invalid push event payload")

    repo_name = event_info["repo_name"]
    branch_name = event_info["branch_name"]

    # Finde Repo und Branch in Config
    repo_config = None
    branch_config = None

    for repo_data in config_manager.repos_config:
        if repo_data.get("name") == repo_name:
            repo_config = Config.parse_obj({"repos": [repo_data]}).repos[0]
            for branch_data in repo_data.get("branches", []):
                if branch_data.get("name") == branch_name:
                    branch_config = repo_config.branches[repo_config.branches.index(
                        next(b for b in repo_config.branches if b.name == branch_name)
                    )]
                    break
            break

    if not repo_config or not branch_config:
        logger.info(f"Webhook received for unconfigured repo/branch: {repo_name}/{branch_name}")
        return {
            "status": "skipped",
            "reason": f"Repository {repo_name}/{branch_name} not configured"
        }

    # Triggere Deployment im Hintergrund
    logger.info(f"Webhook triggered deployment for {repo_name}/{branch_name}")
    background_tasks.add_task(service.check_and_update, repo_config, branch_config)

    return {
        "status": "processing",
        "message": f"Deployment triggered via webhook for {repo_name}/{branch_name}"
    }



if __name__ == "__main__":
    import uvicorn

    os.environ["RUN_MAIN"] = "true"
    uvicorn.run("app:app", host="localhost", port=8000, reload=True, workers=1)
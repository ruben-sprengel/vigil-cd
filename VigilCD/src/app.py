"""Main Application Module."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config_manager import ConfigManager
from src.models import RepoConfig
from src.service import DeploymentService
from src.state import state_manager

logger = logging.getLogger(__name__)


config_file = os.environ.get("CONFIG_PATH", "/home/vigilcd/src/config/config.yaml")
config_manager = ConfigManager(config_file=config_file)
logging.basicConfig(
    level=getattr(logging, config_manager.logging_config.level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


service = DeploymentService(config_manager)
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    """Startup/Shutdown Lifecycle."""
    logger.info(
        f"Starting VigilCD with check interval: {config_manager.scheduling.check_interval_minutes} min"
    )

    run_initial_sync()
    schedule_all_repo_jobs()
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
    CORSMiddleware,  # type: ignore[invalid-argument-type]
    allow_origins=["http://localhost:5173"],  # Svelte dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sync_single_repo_branch(repo_name: str, branch_name: str) -> None:
    """Scheduled job for a single repo/branch combination.

    This function is called by APScheduler for each repo/branch independently.

    Args:
        repo_name: Name of the repository
        branch_name: Name of the branch

    """
    # Find the repo config
    repo_config: RepoConfig | None = None
    for r in config_manager.repos_config:
        if r.name == repo_name:
            repo_config = r
            break

    if not repo_config:
        logger.error(f"Repository '{repo_name}' not found in config")
        return

    # Find the branch config
    branch_config = None
    for b in repo_config.branches:
        if b.name == branch_name:
            branch_config = b
            break

    if not branch_config:
        logger.error(f"Branch '{branch_name}' not found in repo '{repo_name}'")
        return

    if not branch_config.sync_enabled:
        logger.debug(f"Sync disabled for {repo_name}/{branch_name}, skipping")
        return

    try:
        logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] Syncing {repo_name}/{branch_name}")
        service.check_and_update(repo_config, branch_config)
    except Exception as e:
        logger.exception(f"Error syncing {repo_name}/{branch_name}: {e}")


def schedule_all_repo_jobs() -> None:
    """Schedule individual jobs for each repo/branch combination.

    Creates separate APScheduler jobs that run in parallel instead of
    one large sequential job. This improves performance and allows
    independent execution of each sync operation.

    """
    if not config_manager.repos_config:
        logger.warning("No repositories configured. Add repos to config.yaml")
        return

    job_count = 0

    for repo_config in config_manager.repos_config:
        for branch in repo_config.branches:
            if not branch.sync_enabled:
                logger.info(
                    f"Sync disabled for {repo_config.name}/{branch.name}, "
                    f"not scheduling background job"
                )
                continue

            job_id = f"sync_{repo_config.name}_{branch.name}".replace("-", "_").replace("/", "_")

            # Check if job already exists (for hot-reload scenarios)
            existing_job = scheduler.get_job(job_id)
            if existing_job:
                logger.debug(f"Job {job_id} already exists, skipping")
                continue

            # Schedule the job
            scheduler.add_job(
                sync_single_repo_branch,
                "interval",
                minutes=config_manager.scheduling.check_interval_minutes,
                args=[repo_config.name, branch.name],
                id=job_id,
                name=f"Sync {repo_config.name}/{branch.name}",
                max_instances=1,  # Prevent overlapping runs of the same repo/branch
            )

            logger.info(
                f"✓ Scheduled job '{job_id}' (every "
                f"{config_manager.scheduling.check_interval_minutes} min)"
            )
            job_count += 1

    logger.info(f"Scheduled {job_count} background sync jobs")


def run_initial_sync() -> None:
    """Run initial sync for all repos on startup (before scheduler starts).

    This ensures deployments are up-to-date immediately after container start.

    """
    logger.info("Running initial sync for all repositories...")

    if not config_manager.repos_config:
        logger.warning("No repositories configured")
        return

    for repo_config in config_manager.repos_config:
        for branch in repo_config.branches:
            if not branch.sync_enabled:
                continue

            try:
                logger.info(f"Initial sync: {repo_config.name}/{branch.name}")
                service.check_and_update(repo_config, branch)
            except Exception as e:
                logger.exception(f"Error in initial sync for {repo_config.name}/{branch.name}: {e}")


@app.get("/repos")
def list_repos() -> list[RepoConfig]:
    """Endpoint to list all configured repositories."""
    return config_manager.repos_config


@app.get("/health")
def health_check() -> dict[str, Any]:
    """Endpoint to get the overall health status of the system."""
    return {"health": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    """Endpoint to get the current deployment status."""
    return state_manager.status


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    """Endpoint to get non-sensitive configuration settings."""
    return {
        "scheduling": config_manager.scheduling.model_dump(),
        "deployment": config_manager.deployment.model_dump(),
        "logging": config_manager.logging_config.model_dump(),
        "repos_count": len(config_manager.repos_config),
    }


if __name__ == "__main__":
    import uvicorn

    os.environ["RUN_MAIN"] = "true"
    uvicorn.run("app:app", host="localhost", port=8000, reload=True, workers=1)

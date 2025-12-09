"""GitHub Webhook Handler for Event-Driven Deployments."""

import hashlib
import hmac
import logging
from typing import Any

from src.secret_manager import get_secret_manager

logger = logging.getLogger(__name__)


class GitHubWebhookHandler:
    """Handler for GitHub Webhooks."""

    @staticmethod
    def verify_signature(payload: bytes, signature: str) -> bool:
        """Verifies the HMAC-SHA256 signature of the webhook payload.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value (format: "sha256=...")

        Returns:
            True wenn Signature gültig, False sonst

        """
        secret_manager = get_secret_manager()
        webhook_secret = secret_manager.get_webhook_secret()

        if not webhook_secret:
            logger.warning("GITHUB_WEBHOOK_SECRET not set. Skipping signature verification!")
            return False

        if not signature.startswith("sha256="):
            logger.warning(f"Invalid signature format: {signature[:20]}...")
            return False

        expected_sig = (
            "sha256=" + hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        )

        is_valid = hmac.compare_digest(signature, expected_sig)

        if not is_valid:
            logger.error("Webhook signature verification failed!")

        return is_valid

    @staticmethod
    def parse_push_event(payload: dict[str, Any]) -> dict[str, str] | None:
        """Parts the push event payload to extract repository and branch names.

        Args:
            payload: Decoded JSON payload von GitHub

        Returns:
            {"repo_name": "...", "branch_name": "..."} oder None

        """
        try:
            # GitHub schickt den Repository Name in verschiedenen Formaten
            repo_name = payload.get("repository", {}).get("name")
            ref = payload.get("ref")  # Format: "refs/heads/main"

            if not repo_name or not ref:
                logger.warning("Missing repository or ref in webhook payload")
                return None

            # Extrahiere Branch-Namen aus ref
            if ref.startswith("refs/heads/"):
                branch_name = ref[len("refs/heads/") :]
            else:
                logger.warning(f"Unexpected ref format: {ref}")
                return None

            logger.info(f"Webhook: Push to {repo_name}/{branch_name}")
            return {"repo_name": repo_name, "branch_name": branch_name}

        except Exception as e:
            logger.error(f"Failed to parse webhook payload: {e}")
            return None

    @staticmethod
    def get_deployment_targets(payload: dict[str, Any]) -> list:
        """Get the deployment targets from the push event payload.

        Args:
            payload: Decoded JSON payload from GitHub

        Returns:
            Liste  of modified files

        """
        modified_files = []

        # Added files
        for file in payload.get("head_commit", {}).get("added", []):
            modified_files.append(file)

        # Modified files
        for file in payload.get("head_commit", {}).get("modified", []):
            modified_files.append(file)

        # Removed files
        for file in payload.get("head_commit", {}).get("removed", []):
            modified_files.append(file)

        return modified_files

    @staticmethod
    def should_deploy(modified_files: list, target_file: str) -> bool:
        """Checks if the target_file or other important files were changed.

        Args:
            modified_files: Modified files from the push event
            target_file: Target file to check (e.g., docker-compose.yml)


        Returns:
            True when target_file or important files changed, False otherwise

        """
        if not modified_files:
            return True

        if target_file in modified_files:
            logger.info(f"Target file changed: {target_file}")
            return True

        important_files = [".github/workflows", "Dockerfile", ".dockerignore"]
        for important_file in important_files:
            if any(important_file in file for file in modified_files):
                logger.info(f"Important file changed: {important_file}")
                return True

        logger.debug(f"No relevant files changed for {target_file}")
        return False

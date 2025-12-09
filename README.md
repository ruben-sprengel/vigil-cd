# VigilCD - GitOps Deployment Agent

**VigilCD** is a lightweight GitOps deployment agent that automatically monitors Git repositories and performs Docker Compose deployments on changes. Built for self-hosted environments with support for private repositories and Docker registries.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?logo=docker&logoColor=white)](https://www.docker.com/)

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/rubensprengel)

## About the Name

The name **VigilCD** derives from Latin **"vigil"** (watchful, vigilant) - originally meaning to watch or keep vigil. This reflects VigilCD's core behavior:

| Latin Root | Meaning | VigilCD Function |
|-----------|---------|------------------|
| **vigilia** | Wakefulness, watching | Continuous monitoring |
| **vigil** | Watchful, vigilant | Always alert & active |
| **vigilance** | Vigilance, watchfulness | Detecting changes |
| **vigilare** | To watch over | Safeguarding deployments |

## Features

-  **Automatic Git Synchronization**: Periodic polling or webhook-based
-  **Multi-Repository Support**: Manage multiple repositories and branches
-  **SSH & HTTPS Authentication**: Private GitHub/GitLab repositories
-  **Private Docker Registries**: GHCR, Docker Hub, Self-Hosted
-  **Docker Compose Deployments**: Automatic deployment on Git changes
-  **Health Checks**: Automatic recovery on container failures
-  **RESTful API**: Status monitoring and manual triggers
-  **GitHub Webhooks**: Instant deployments on push events
-  **Non-Root Container**: Security through least-privilege principle
-  **Cross-Platform**: Linux, Windows (Docker Desktop), macOS

---

## Table of Contents

- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Configuration](#️-configuration)
    - [Repository Configuration](#repository-configuration)
    - [Environment Variables](#environment-variables)
- [SSH Authentication](#-ssh-authentication)
- [Private Docker Registries](#-private-docker-registries)
- [GitHub Webhooks](#-github-webhooks)
- [API Documentation](#-api-documentation)
- [Architecture](#-architecture)
- [Troubleshooting](#-troubleshooting)
- [Security Best Practices](#️-security-best-practices)
- [Contributing](#-contributing)

---

## Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **Git** 2.30+ (for local development)
- **Python** 3.11+ (for local development)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/your-org/vigilcd.git
cd vigilcd
```

### 2. Initialize Configuration

```bash
# Make setup script executable
chmod +x init-config.sh

# Run setup (creates config.yaml, .env, SSH keys)
./init-config.sh
```

### 3. Configure Repositories

Edit `config/config.yaml` with your repositories:

```yaml
repos:
  - name: "my-app"
    url: "https://github.com/username/my-app"
    auth_method: "https"
    branches:
      - name: "main"
        targets:
          - name: "app"
            file: "docker-compose.yml"
            deploy: true
            build_images: false
```

### 4. Set Environment Variables

Edit `.env` with your credentials:

```bash
vim .env
```

### 5. Start VigilCD

```bash
docker-compose up -d
```

### 6. Verify Installation

```bash
# Check logs
docker-compose logs -f vigilcd

# Check health
curl http://localhost:8000/health

# Check status
curl http://localhost:8000/api/status
```

---

## Configuration

### File Structure

```
vigilcd/
├── config/
│   ├── config.template.yaml  ← Template with examples (in Git)
│   └── config.yaml           ← Your config (not in Git)
├── .env.template              ← Environment variables template (in Git)
├── .env                       ← Your secrets (not in Git)
├── ssh-keys/                  ← SSH keys (not in Git)
├── repos/                     ← Cloned repositories (not in Git)
└── docker-compose.yml
```

### Repository Configuration

Edit `config/config.yaml`:

```yaml
repos:
  # Public HTTPS Repository
  - name: "example-public"
    url: "https://github.com/username/repo"
    auth_method: "https"  # Default
    
    branches:
      - name: "main"
        targets:
          - name: "app"
            file: "docker-compose.yml"
            deploy: true
            build_images: false  # Set to true to rebuild images

  # Private SSH Repository (Global SSH Key)
  - name: "example-private"
    url: "git@github.com:username/private-repo.git"
    auth_method: "ssh"
    # Uses VIGILCD_SSH_KEY_PATH from environment
    
    branches:
      - name: "production"
        targets:
          - name: "api"
            file: "docker-compose.prod.yml"
            deploy: true
            build_images: true

  # Private SSH with Dedicated Deploy Key
  - name: "microservice"
    url: "git@github.com:company/microservice.git"
    auth_method: "ssh"
    ssh_key_path: "/home/vigilcd/.ssh/microservice_key"  # Repo-specific
    
    # Private Docker Registry
    registries:
      - url: "ghcr.io"
        username: "deployment-bot"
        password_env_var: "GHCR_TOKEN"
    
    branches:
      - name: "main"
        targets:
          - name: "service"
            file: "docker-compose.yml"
            deploy: true
            build_images: true
```

#### Configuration Options

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Unique repository identifier |
| `url` | string | ✅ | Git repository URL (HTTPS or SSH) |
| `auth_method` | string | ❌ | `"https"` or `"ssh"` (default: `"https"`) |
| `ssh_key_path` | string | ❌ | Path to SSH key (inside container) |
| `registries` | list | ❌ | Private Docker registry credentials |
| `branches` | list | ✅ | Branches to monitor |

**Branch Options:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Branch name (e.g., `"main"`) |
| `targets` | list | ✅ | Deployment targets |

**Target Options:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Target identifier |
| `file` | string | ✅ | Path to docker-compose.yml (relative to repo root) |
| `deploy` | boolean | ❌ | Auto-deploy on changes (default: `true`) |
| `build_images` | boolean | ❌ | Run `--build` flag (default: `false`) |

### Environment Variables

Edit `.env`:

```bash
# Git & SSH Configuration
VIGILCD_SSH_KEY_PATH=/home/vigilcd/.ssh/id_ed25519
REPO_BASE_PATH=/home/vigilcd/repos

# Scheduling
VIGILCD_CHECK_INTERVAL_MINUTES=5
VIGILCD_GIT_RETRY_COUNT=3
VIGILCD_RETRY_BACKOFF_FACTOR=2.0

# Deployment Timeouts
VIGILCD_DOCKER_TIMEOUT=300
VIGILCD_GIT_TIMEOUT=60
VIGILCD_DOCKER_DAEMON_TIMEOUT=10

# Logging
VIGILCD_LOG_LEVEL=INFO
VIGILCD_LOG_FORMAT=json

# Private Docker Registries
GHCR_TOKEN=ghp_xxxxx
COMPANY_REGISTRY_TOKEN=xxxxx

# GitHub Integration
GITHUB_TOKEN=ghp_xxxxx
WEBHOOK_SECRET=xxxxx
```

**Available Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `VIGILCD_SSH_KEY_PATH` | `/home/vigilcd/.ssh/id_ed25519` | Path to global SSH key |
| `REPO_BASE_PATH` | `/home/vigilcd/repos` | Base directory for cloned repos |
| `VIGILCD_CHECK_INTERVAL_MINUTES` | `5` | Polling interval for Git changes |
| `VIGILCD_GIT_RETRY_COUNT` | `3` | Number of retry attempts for Git operations |
| `VIGILCD_RETRY_BACKOFF_FACTOR` | `2.0` | Exponential backoff factor (2.0 = 1s, 2s, 4s, 8s...) |
| `VIGILCD_DOCKER_TIMEOUT` | `300` | Docker Compose operation timeout (seconds) |
| `VIGILCD_GIT_TIMEOUT` | `60` | Git operation timeout (seconds) |
| `VIGILCD_DOCKER_DAEMON_TIMEOUT` | `10` | Docker daemon health check timeout (seconds) |
| `VIGILCD_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `VIGILCD_LOG_FORMAT` | `json` | Log format: `json` or `text` |

---

## SSH Authentication

### Automatic Setup

```bash
./init-config.sh
# Will prompt to generate SSH keys automatically
```

### Manual Setup

#### 1. Generate SSH Key

```bash
ssh-keygen -t ed25519 -C "vigilcd-deploy" -f ./ssh-keys/id_ed25519 -N ""
```

#### 2. Add to GitHub

```bash
# Display public key
cat ./ssh-keys/id_ed25519.pub

# Add to GitHub:
# Repository Settings → Deploy Keys → Add deploy key
# Paste the public key and enable "Allow write access" if needed
```

#### 3. Set Permissions

```bash
chmod 700 ./ssh-keys
chmod 600 ./ssh-keys/id_ed25519
chmod 644 ./ssh-keys/id_ed25519.pub
```

#### 4. Configure in `config.yaml`

```yaml
repos:
  - name: "private-app"
    url: "git@github.com:username/private-app.git"
    auth_method: "ssh"
    # Uses global VIGILCD_SSH_KEY_PATH
```

### Multiple SSH Keys (Per-Repository)

```bash
# Generate repo-specific key
ssh-keygen -t ed25519 -C "microservice-deploy" -f ./ssh-keys/microservice_key -N ""

# Add to GitHub (same as above)

# Configure in config.yaml
repos:
  - name: "microservice"
    url: "git@github.com:company/microservice.git"
    auth_method: "ssh"
    ssh_key_path: "/home/vigilcd/.ssh/microservice_key"  # Repo-specific key
```

### SSH Troubleshooting

```bash
# Check SSH key permissions
ls -la ./ssh-keys/

# Should show:
# drwx------  (700) for directory
# -rw-------  (600) for private key
# -rw-r--r--  (644) for public key

# Test SSH connection
docker exec vigilcd ssh -T git@github.com

# Expected output:
# Hi username! You've successfully authenticated, but GitHub does not provide shell access.
```

---

## Private Docker Registries

### Supported Registries

- GitHub Container Registry (ghcr.io)
- Docker Hub (docker.io)
- Self-Hosted Registries
- AWS ECR
- Google Container Registry (gcr.io)
- Any registry with username/password authentication

### Configuration

#### 1. Add Registry Credentials to `.env`

```bash
# GitHub Container Registry
GHCR_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxx

# Docker Hub
DOCKERHUB_TOKEN=dckr_pat_xxxxxxxxxxxxx

# Self-Hosted Registry
COMPANY_REGISTRY_TOKEN=xxxxxxxxxxxxx
```

#### 2. Configure in `config.yaml`

```yaml
repos:
  - name: "my-app"
    url: "git@github.com:company/my-app.git"
    auth_method: "ssh"
    
    # Private registries
    registries:
      # GitHub Container Registry
      - url: "ghcr.io"
        username: "deployment-bot"
        password_env_var: "GHCR_TOKEN"
      
      # Self-Hosted Registry
      - url: "registry.company.com:5000"
        username: "ci-deployer"
        password_env_var: "COMPANY_REGISTRY_TOKEN"
      
      # Public registry (no credentials needed)
      - url: "docker.io"
    
    branches:
      - name: "main"
        targets:
          - name: "app"
            file: "docker-compose.yml"
            deploy: true
            build_images: true  # Build from private registry base images
```

### Generate GitHub Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Scopes:
    -  `read:packages` (to pull images)
    -  `write:packages` (to push images, optional)
4. Copy token and add to `.env`:

```bash
GHCR_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxx
```

### Docker Compose Example

Your `docker-compose.yml` in the repository:

```yaml
version: '3.8'

services:
  app:
    image: ghcr.io/company/my-app:latest
    # VigilCD will login to ghcr.io before deployment
    ports:
      - "3000:3000"
```

---

## GitHub Webhooks

Enable instant deployments on Git push events.

### 1. Generate Webhook Secret

```bash
# Generate random secret
openssl rand -base64 32

# Add to .env
WEBHOOK_SECRET=your-generated-secret-here
```

### 2. Configure Webhook in GitHub

1. Go to: **Repository Settings → Webhooks → Add webhook**
2. Configure:
    - **Payload URL**: `http://your-server:8000/webhooks/github`
    - **Content type**: `application/json`
    - **Secret**: Your webhook secret from `.env`
    - **Events**: Select "Just the push event"
    - **Active**: ✅ Enable

### 3. Test Webhook

```bash
# Push a change to your repository
git commit -m "test webhook" --allow-empty
git push

# Check VigilCD logs
docker-compose logs -f vigilcd

# Should show: "Webhook triggered deployment for repo/branch"
```

### Webhook Security

- HMAC-SHA256 signature verification
- Secret stored in environment variable (not in Git)
- Only processes push events
- Validates repository/branch configuration

---

## Architecture

### Components

```
┌──────────────────────────────────────────────────────┐
│                   VigilCD Container                  │
│                   (User: vigilcd)                    │
├──────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐   │
│  │   FastAPI    │  │  APScheduler │  │  GitPython│   │
│  │   Web API    │  │   Scheduler  │  │    Core   │   │ 
│  └──────────────┘  └──────────────┘  └───────────┘   │
│         │                  │                 │       │
│         └──────────────────┴─────────────────┘       │
│                          │                           │
│              ┌───────────▼───────────┐               │
│              │  DeploymentService    │               │
│              │  - Git Operations     │               │
│              │  - Docker Compose     │               │
│              │  - Health Checks      │               │
│              └───────────┬───────────┘               │
└────────────────────────────┼─────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
    │   Git   │        │ Docker  │        │  State  │
    │ Repos   │        │ Daemon  │        │ Manager │
    └─────────┘        └─────────┘        └─────────┘
```

### Workflow

1. **Scheduler**: Triggers sync check every N minutes (configurable)
2. **Git Check**: Fetches remote commit hash via `git ls-remote`
3. **Comparison**: Compares remote hash with local commit
4. **Update**: If different, performs `git fetch` + `git reset --hard`
5. **Deployment**: Executes `docker compose up -d` for configured targets
6. **Health Check**: Monitors container status via `docker compose ps`
7. **State Management**: Updates internal state for API responses

### Docker Compose Integration

VigilCD manages Docker Compose deployments by:

1. **Cloning** repositories to `/home/vigilcd/repos/{repo}/{branch}`
2. **Executing** `docker compose` commands with custom project names
3. **Monitoring** container health via Docker API
4. **Recovering** failed containers automatically

**Project Naming Convention:**

```bash
{repo_name}_{branch_name}
```

Example: `my-app_main`

This ensures multiple branches can coexist without conflicts.

---

## 🐛 Troubleshooting

### Permission Errors

```bash
# Fix ownership for vigilcd user (UID 1000)
./fix-permissions.sh

# Or manually:
sudo chown -R 1000:1000 ./ssh-keys ./repos ./logs
chmod 700 ./ssh-keys
chmod 600 ./ssh-keys/id_ed25519
```

### SSH Authentication Failed

```bash
# Check key exists and has correct permissions
ls -la ./ssh-keys/
# Should show: -rw------- (600) for private key

# Test SSH connection from container
docker exec vigilcd ssh -T git@github.com

# Check if key is mounted correctly
docker exec vigilcd ls -la /home/vigilcd/.ssh/
```

### Docker Socket Permission Denied

```bash
# Add your user to docker group
sudo usermod -aG docker $USER

# Apply changes (logout/login or):
newgrp docker

# Verify
docker ps
```

### Config Changes Not Applied

```bash
# Restart container to reload config
docker-compose restart vigilcd

# Check logs for errors
docker-compose logs vigilcd | grep -i error
```

### Git Operation Timeout

Increase timeout in `.env`:

```bash
VIGILCD_GIT_TIMEOUT=120  # Increase from 60 to 120 seconds
```

### Docker Compose Fails

```bash
# Check if docker-compose.yml exists in repo
docker exec vigilcd ls -la /home/vigilcd/repos/my-app/main/

# Test docker compose manually
docker exec vigilcd sh -c "cd /home/vigilcd/repos/my-app/main && docker compose config"

# Check logs
docker-compose logs vigilcd
```

### Webhook Not Working

```bash
# Verify webhook secret is set
docker exec vigilcd printenv | grep WEBHOOK_SECRET

# Check webhook delivery in GitHub
# Repository Settings → Webhooks → Recent Deliveries

# Enable webhook debug logging
VIGILCD_LOG_LEVEL=DEBUG docker-compose restart vigilcd
```

### Container Keeps Restarting

```bash
# Check health status
docker ps -a

# View full logs
docker-compose logs --tail=100 vigilcd

# Check config syntax
python3 -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

---

## Security Best Practices

### Never Commit Secrets

```bash
# .gitignore should contain:
config/config.yaml
.env
ssh-keys/
repos/
*.log
```

### Use Deploy Keys (Not Personal Tokens)

- ✅ Create **Deploy Keys** per repository (read-only)
- ❌ Don't use personal access tokens with full repo access

### Rotate Credentials Regularly

```bash
# Every 90 days:
1. Generate new SSH key
2. Update GitHub deploy key
3. Update ssh-keys/ directory
4. Restart VigilCD
```

### Limit Docker Registry Scopes

For GitHub Personal Access Tokens:
- ✅ `read:packages` only (if you only pull images)
- ❌ Don't use tokens with `repo` or `admin` scopes

### Use Non-Root Container

VigilCD runs as user `vigilcd` (UID 1000) for security:

```dockerfile
USER vigilcd
```

### Enable HTTPS for Webhooks

In production, use reverse proxy (nginx, Caddy) with TLS.

### File Permissions Summary

| File/Directory | Permission | Owner | Description |
|----------------|------------|-------|-------------|
| `config.yaml` | `644` | Your user | Readable by all, writable by you |
| `.env` | `600` | Your user | Only readable by you |
| `ssh-keys/` | `700` | `1000:1000` | Only accessible by vigilcd |
| `ssh-keys/id_ed25519` | `600` | `1000:1000` | Private key protected |
| `repos/` | `755` | `1000:1000` | Writable by vigilcd |

---

## Updating Configuration

### Edit Config File

```bash
# 1. Edit config
vim config/config.yaml

# 2. Restart container
docker-compose restart vigilcd

# 3. Verify changes
curl http://localhost:8000/api/config
```

### Add New Repository

```bash
# 1. Add to config.yaml
repos:
  - name: "new-repo"
    url: "git@github.com:company/new-repo.git"
    auth_method: "ssh"
    branches:
      - name: "main"
        targets:
          - name: "app"
            file: "docker-compose.yml"
            deploy: true

# 2. Restart
docker-compose restart vigilcd

# 3. Verify in logs
docker-compose logs -f vigilcd
```

---

## Production Deployment

### Recommended Setup

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  vigilcd:
    build: .
    container_name: vigilcd
    restart: always  # Auto-restart on failure
    
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
    
    # Logging
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./ssh-keys:/home/vigilcd/.ssh:ro
      - ./repos:/home/vigilcd/repos
      - ./config/config.yaml:/app/src/config/config.yaml:ro
      - ./logs:/app/logs
    
    environment:
      VIGILCD_LOG_LEVEL: "INFO"
      VIGILCD_LOG_FORMAT: "json"
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Monitoring

Use external monitoring tools:

```bash
# Prometheus metrics (future feature)
GET /metrics

# Health check endpoint for uptime monitoring
GET /health
```

### Backup Strategy

```bash
# Backup config and secrets
tar -czf vigilcd-backup-$(date +%Y%m%d).tar.gz \
  config/ \
  .env \
  ssh-keys/

# Restore
tar -xzf vigilcd-backup-20240115.tar.gz
./fix-permissions.sh
docker-compose up -d
```

---

## Performance Tuning

### Adjust Polling Interval

For fewer API calls to Git hosting:

```bash
# .env
VIGILCD_CHECK_INTERVAL_MINUTES=15  # Default: 5
```

**Recommendation**: Use webhooks instead of frequent polling.

### Increase Timeout for Large Repos

```bash
# .env
VIGILCD_GIT_TIMEOUT=180  # Default: 60
VIGILCD_DOCKER_TIMEOUT=600  # Default: 300
```

### Reduce Retry Count

For faster failure detection:

```bash
# .env
VIGILCD_GIT_RETRY_COUNT=2  # Default: 3
VIGILCD_RETRY_BACKOFF_FACTOR=1.5  # Default: 2.0
```

---

## Contributing

Contributions are welcome! Please follow these guidelines:

### Reporting Issues

1. Check existing issues first
2. Provide clear description and steps to reproduce
3. Include logs (sanitize sensitive data)
4. Specify your environment (OS, Docker version, etc.)

### Pull Requests

1. Fork the repository
2. Create feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push to branch: `git push origin feature/my-feature`
5. Create Pull Request

### Development Setup

```bash
# Clone repository
git clone https://github.com/your-org/vigilcd.git
cd vigilcd

# Install dependencies (local development)
pip install uv
uv sync --extra dev

# Run locally
uv run uvicorn src.app:app --reload

# Run tests
uv run pytest
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Git operations via [GitPython](https://gitpython.readthedocs.io/)
- Scheduling via [APScheduler](https://apscheduler.readthedocs.io/)
- Dependency management via [uv](https://github.com/astral-sh/uv)

---

## Roadmap

- [ ] Prometheus metrics endpoint
- [ ] Multi-platform architecture support (ARM64)
- [ ] Web UI for configuration
- [ ] Advanced health check strategies
- [ ] ...

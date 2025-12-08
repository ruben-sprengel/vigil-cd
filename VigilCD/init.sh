#!/bin/bash

# ===================================
# VigilCD Configuration Setup Script
# ===================================
# Initialisiert lokale Config aus Template
# Setzt Berechtigungen für vigilcd User (UID 1000)

set -e

TEMPLATE="./config/config.template.yaml"
CONFIG="./config/config.yaml"
ENV_FILE=".env"
ENV_TEMPLATE=".env.template"
CONTAINER_UID=1000
CONTAINER_GID=1000

echo "🚀 VigilCD Configuration Setup"
echo "================================"
echo ""

# ===================================
# 1. Check if template exists
# ===================================
if [ ! -f "$TEMPLATE" ]; then
    echo "❌ Error: Template not found: $TEMPLATE"
    exit 1
fi

# ===================================
# 2. Create config.yaml if not exists
# ===================================
if [ -f "$CONFIG" ]; then
    echo "⚠️  Warning: config.yaml already exists!"
    read -p "   Overwrite with template? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   Keeping existing config.yaml"
    else
        cp "$TEMPLATE" "$CONFIG"
        echo "✅ config.yaml overwritten from template"
    fi
else
    cp "$TEMPLATE" "$CONFIG"
    echo "✅ Created config.yaml from template"
fi

chmod 644 "$CONFIG"
echo "✅ Set permissions: 644 (rw-r--r--)"

# ===================================
# 3. Create .env from template if not exists
# ===================================
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_TEMPLATE" ]; then
        cp "$ENV_TEMPLATE" "$ENV_FILE"
        echo "✅ Created .env from template"
    else
        cat > "$ENV_FILE" << 'EOF'
# VigilCD Environment Variables
# ================================

# --- Git & SSH Configuration ---
# WICHTIG: Pfade für vigilcd User (nicht root)
VIGILCD_SSH_KEY_PATH=/home/vigilcd/.ssh/id_ed25519
REPO_BASE_PATH=/home/vigilcd/repos

# --- Scheduling ---
VIGILCD_CHECK_INTERVAL_MINUTES=5
VIGILCD_GIT_RETRY_COUNT=3
VIGILCD_RETRY_BACKOFF_FACTOR=2.0

# --- Deployment Timeouts ---
VIGILCD_DOCKER_TIMEOUT=300
VIGILCD_GIT_TIMEOUT=60
VIGILCD_DOCKER_DAEMON_TIMEOUT=10

# --- Logging ---
VIGILCD_LOG_LEVEL=INFO
VIGILCD_LOG_FORMAT=json

# --- Private Docker Registries ---
GHCR_TOKEN=
COMPANY_REGISTRY_TOKEN=

# --- GitHub Integration ---
GITHUB_TOKEN=
WEBHOOK_SECRET=
EOF
        echo "✅ Created .env with defaults"
    fi
    chmod 600 "$ENV_FILE"
    echo "✅ Set .env permissions: 600 (rw-------)"
else
    echo "ℹ️  .env already exists (keeping it)"
fi

# ===================================
# 4. Create necessary directories
# ===================================
mkdir -p ./repos
mkdir -p ./ssh-keys
mkdir -p ./logs

echo "✅ Created directories: repos/, ssh-keys/, logs/"

# ===================================
# 5. Set ownership for vigilcd user (UID 1000)
# ===================================
echo ""
echo "🔧 Setting ownership for container user (UID $CONTAINER_UID)..."

# Check if we need sudo
if [ "$EUID" -ne 0 ] && [ "$(id -u)" -ne "$CONTAINER_UID" ]; then
    echo "   ℹ️  Running with sudo to set ownership..."
    USE_SUDO="sudo"
else
    USE_SUDO=""
fi

# Set ownership
$USE_SUDO chown -R $CONTAINER_UID:$CONTAINER_GID ./ssh-keys 2>/dev/null || true
$USE_SUDO chown -R $CONTAINER_UID:$CONTAINER_GID ./repos 2>/dev/null || true
$USE_SUDO chown -R $CONTAINER_UID:$CONTAINER_GID ./logs 2>/dev/null || true

echo "✅ Ownership set to UID $CONTAINER_UID"

# Set permissions
chmod 700 ./ssh-keys
chmod 755 ./repos
chmod 755 ./logs

echo "✅ Directory permissions set"

# ===================================
# 6. Check if SSH keys exist
# ===================================
if [ ! -f "./ssh-keys/id_ed25519" ]; then
    echo ""
    echo "⚠️  No SSH keys found in ./ssh-keys/"
    read -p "   Generate SSH key now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ssh-keygen -t ed25519 -C "vigilcd-deploy" -f ./ssh-keys/id_ed25519 -N ""

        # Set correct ownership and permissions
        $USE_SUDO chown $CONTAINER_UID:$CONTAINER_GID ./ssh-keys/id_ed25519
        $USE_SUDO chown $CONTAINER_UID:$CONTAINER_GID ./ssh-keys/id_ed25519.pub
        chmod 600 ./ssh-keys/id_ed25519
        chmod 644 ./ssh-keys/id_ed25519.pub

        echo "✅ SSH key generated"
        echo ""
        echo "📋 Add this public key to GitHub:"
        echo "   → Repository Settings → Deploy Keys → Add deploy key"
        echo ""
        cat ./ssh-keys/id_ed25519.pub
        echo ""
    else
        echo "   Skipped SSH key generation"
    fi
else
    echo "✅ SSH keys already exist"
    # Ensure correct permissions
    $USE_SUDO chown $CONTAINER_UID:$CONTAINER_GID ./ssh-keys/id_ed25519 2>/dev/null || true
    chmod 600 ./ssh-keys/id_ed25519
fi

# ===================================
# 7. Validate config.yaml
# ===================================
echo ""
echo "🔍 Validating config.yaml..."

if command -v python3 &> /dev/null; then
    python3 - << 'PYTHON'
import yaml
import sys

try:
    with open('./config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    if not config or 'repos' not in config:
        print("❌ Invalid config: 'repos' key missing")
        sys.exit(1)

    if len(config['repos']) == 0:
        print("⚠️  Warning: No repositories configured")
        print("   Edit config.yaml to add your repositories")
    else:
        print(f"✅ Config valid: {len(config['repos'])} repositories configured")

except yaml.YAMLError as e:
    print(f"❌ YAML syntax error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Validation error: {e}")
    sys.exit(1)
PYTHON
else
    echo "⚠️  Python not found, skipping validation"
fi

# ===================================
# 8. Final summary
# ===================================
echo ""
echo "================================"
echo "📋 Permission Summary"
echo "================================"
ls -la ./ssh-keys ./repos ./config/config.yaml .env 2>/dev/null | grep -v total || true

echo ""
echo "================================"
echo "✅ Setup Complete!"
echo "================================"
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. Edit your configuration:"
echo "   vim config/config.yaml"
echo ""
echo "2. Fill in environment variables:"
echo "   vim .env"
echo ""
echo "3. Start VigilCD:"
echo "   docker-compose up -d"
echo ""
echo "4. Check logs:"
echo "   docker-compose logs -f vigilcd"
echo ""
echo "5. Access API:"
echo "   curl http://localhost:8000/health"
echo ""
echo "ℹ️  Container Info:"
echo "   - Runs as user: vigilcd (UID $CONTAINER_UID)"
echo "   - SSH keys:     /home/vigilcd/.ssh"
echo "   - Repos:        /home/vigilcd/repos"
echo "   - Config:       /app/src/config/config.yaml (read-only)"
echo ""
echo "🔧 If you encounter permission issues, run:"
echo "   ./fix-permissions.sh"
echo ""
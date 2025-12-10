#!/bin/bash

# ===================================
# VigilCD Permission Repair Script
# ===================================
# Fixes file ownership and permissions for VigilCD container
# Run this if you encounter permission issues

set -e

CONTAINER_UID=1000
CONTAINER_GID=1000

echo "🔧 VigilCD Permission Repair"
echo "================================"
echo ""

# Check if we need sudo
if [ "$EUID" -ne 0 ] && [ "$(id -u)" -ne "$CONTAINER_UID" ]; then
    echo "ℹ️  This script needs sudo to change file ownership"
    USE_SUDO="sudo"
else
    USE_SUDO=""
fi

# ===================================
# 1. Fix Directory Ownership
# ===================================
echo "📁 Fixing directory ownership..."

if [ -d "./ssh-keys" ]; then
    $USE_SUDO chown -R $CONTAINER_UID:$CONTAINER_GID ./ssh-keys
    chmod 700 ./ssh-keys
    echo "✅ ssh-keys/ → $CONTAINER_UID:$CONTAINER_GID (drwx------)"
fi

if [ -d "./repos" ]; then
    $USE_SUDO chown -R $CONTAINER_UID:$CONTAINER_GID ./repos
    chmod 755 ./repos
    echo "✅ repos/ → $CONTAINER_UID:$CONTAINER_GID (drwxr-xr-x)"
fi

if [ -d "./logs" ]; then
    $USE_SUDO chown -R $CONTAINER_UID:$CONTAINER_GID ./logs
    chmod 755 ./logs
    echo "✅ logs/ → $CONTAINER_UID:$CONTAINER_GID (drwxr-xr-x)"
fi

# ===================================
# 2. Fix SSH Key Permissions
# ===================================
echo ""
echo "🔐 Fixing SSH key permissions..."

if [ -f "./ssh-keys/id_ed25519" ]; then
    $USE_SUDO chown $CONTAINER_UID:$CONTAINER_GID ./ssh-keys/id_ed25519
    chmod 600 ./ssh-keys/id_ed25519
    echo "✅ id_ed25519 → 600 (-rw-------)"
fi

if [ -f "./ssh-keys/id_ed25519.pub" ]; then
    $USE_SUDO chown $CONTAINER_UID:$CONTAINER_GID ./ssh-keys/id_ed25519.pub
    chmod 644 ./ssh-keys/id_ed25519.pub
    echo "✅ id_ed25519.pub → 644 (-rw-r--r--)"
fi

# Fix any other SSH keys
find ./ssh-keys -type f -name "id_*" ! -name "*.pub" -exec $USE_SUDO chown $CONTAINER_UID:$CONTAINER_GID {} \; -exec chmod 600 {} \; 2>/dev/null || true
find ./ssh-keys -type f -name "*.pub" -exec $USE_SUDO chown $CONTAINER_UID:$CONTAINER_GID {} \; -exec chmod 644 {} \; 2>/dev/null || true

# ===================================
# 3. Fix Config Permissions
# ===================================
echo ""
echo "⚙️  Fixing config permissions..."

if [ -f "./config/config.yaml" ]; then
    chmod 644 ./config/config.yaml
    echo "✅ config.yaml → 644 (-rw-r--r--)"
fi

if [ -f "./.env" ]; then
    chmod 600 ./.env
    echo "✅ .env → 600 (-rw-------)"
fi

# ===================================
# 4. Verify Permissions
# ===================================
echo ""
echo "================================"
echo "📋 Current Permissions"
echo "================================"
echo ""

if [ -d "./ssh-keys" ]; then
    echo "SSH Keys:"
    ls -la ./ssh-keys | head -n 5
    echo ""
fi

if [ -d "./repos" ]; then
    echo "Repos:"
    ls -ld ./repos
    echo ""
fi

if [ -f "./config/config.yaml" ]; then
    echo "Config:"
    ls -l ./config/config.yaml
    echo ""
fi

if [ -f "./.env" ]; then
    echo ".env:"
    ls -l ./.env
    echo ""
fi

# ===================================
# 5. Test Docker Socket Access
# ===================================
echo "================================"
echo "🐳 Docker Socket Check"
echo "================================"
echo ""

if [ -S "/var/run/docker.sock" ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
    echo "Docker Socket GID: $DOCKER_GID"

    if [ -f "./.env" ]; then
        if grep -q "^DOCKER_GID=" ./.env; then
            ENV_GID=$(grep "^DOCKER_GID=" ./.env | cut -d= -f2)
            if [ "$ENV_GID" = "$DOCKER_GID" ]; then
                echo "✅ .env DOCKER_GID matches socket ($DOCKER_GID)"
            else
                echo "⚠️  .env DOCKER_GID ($ENV_GID) differs from socket ($DOCKER_GID)"
                echo "   Run: ./setup.sh to update"
            fi
        else
            echo "⚠️  DOCKER_GID not found in .env"
            echo "   Run: ./setup.sh to configure"
        fi
    fi
else
    echo "⚠️  Docker socket not found"
fi

# ===================================
# 6. Summary
# ===================================
echo ""
echo "================================"
echo "✅ Permission Repair Complete"
echo "================================"
echo ""
echo "If issues persist:"
echo ""
echo "1. Restart VigilCD:"
echo "   docker-compose restart vigilcd"
echo ""
echo "2. Check container logs:"
echo "   docker-compose logs vigilcd"
echo ""
echo "3. Verify Docker socket access:"
echo "   docker exec vigilcd docker ps"
echo ""
echo "4. Re-run complete setup:"
echo "   ./setup.sh"
echo ""
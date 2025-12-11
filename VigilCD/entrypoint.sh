#!/bin/bash
set -e

echo "🚀 VigilCD starting..."

# ===================================
# 1. Initialize config if not exists
# ===================================
CONFIG_DIR="/home/vigilcd/src/config"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
TEMPLATE_FILE="/home/vigilcd/config.template.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚙️  Config file not found, copying template..."

    # Ensure directory exists
    mkdir -p "$CONFIG_DIR"

    # Copy template
    if [ -f "$TEMPLATE_FILE" ]; then
        cp "$TEMPLATE_FILE" "$CONFIG_FILE"
        echo "✅ Created config.yaml from template"
    else
        echo "❌ ERROR: Template file not found at $TEMPLATE_FILE"
        echo "   Please mount a config.yaml or provide config.template.yaml"
        exit 1
    fi
else
    echo "✅ Config file found: $CONFIG_FILE"
fi

# ===================================
# 2. Check Docker socket
# ===================================
if [ -S "/var/run/docker.sock" ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo "unknown")
    echo "🐳 Docker socket found (GID: $DOCKER_GID)"
else
    echo "⚠️  Warning: Docker socket not found at /var/run/docker.sock"
fi

# ===================================
# 3. Start application
# ===================================
echo "🎯 Starting VigilCD application..."
exec "$@"
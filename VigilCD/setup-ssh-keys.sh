#!/bin/bash

# ===================================
# VigilCD SSH Key Setup Script
# ===================================
# Generiert SSH Keys für private GitHub Repositories
# und konfiguriert SSH-Agent für Container-Verwendung

set -e

SSH_DIR="./ssh-keys"
KEY_NAME="id_ed25519"

echo "🔐 Setting up SSH keys for VigilCD..."

# Create SSH directory
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

# Generate SSH key if not exists
if [ ! -f "$SSH_DIR/$KEY_NAME" ]; then
    echo "Generating new SSH key..."
    ssh-keygen -t ed25519 -C "vigilcd-deployment" -f "$SSH_DIR/$KEY_NAME" -N ""
    echo "✅ SSH key generated: $SSH_DIR/$KEY_NAME"
else
    echo "ℹ️  SSH key already exists: $SSH_DIR/$KEY_NAME"
fi

# Set correct permissions
chmod 600 "$SSH_DIR/$KEY_NAME"
chmod 644 "$SSH_DIR/$KEY_NAME.pub"

echo ""
echo "📋 Next steps:"
echo "1. Add the public key to your GitHub repository:"
echo "   → Repository Settings → Deploy Keys → Add deploy key"
echo ""
echo "   Public Key:"
cat "$SSH_DIR/$KEY_NAME.pub"
echo ""
echo "2. For multiple repositories with different keys:"
echo "   - Create additional keys: ssh-keygen -t ed25519 -f $SSH_DIR/repo_name_key"
echo "   - Reference in config.yaml: ssh_key_path: '/app/.ssh/repo_name_key'"
echo ""
echo "3. Start VigilCD: docker-compose up -d"
echo ""
echo "🔒 Security note: Never commit private keys to Git!"
echo "   Add 'ssh-keys/' to .gitignore"
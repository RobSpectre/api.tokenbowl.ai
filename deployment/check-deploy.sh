#!/bin/bash
# Pull-based deployment script that checks for new releases
# This can be run via a systemd timer or cron job

set -e

# Configuration
APP_DIR="/opt/token-bowl-chat-server"
REPO_URL="https://github.com/YOUR_USERNAME/token-bowl-chat-server.git"
DEPLOY_LOG="/var/log/token-bowl-chat/deploy.log"

# Ensure log directory exists
sudo mkdir -p /var/log/token-bowl-chat
sudo chown www-data:www-data /var/log/token-bowl-chat

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$DEPLOY_LOG"
}

cd "$APP_DIR"

# Fetch latest tags
git fetch --tags origin

# Get current version
CURRENT_VERSION=$(git describe --tags --exact-match 2>/dev/null || echo "none")

# Get latest release tag
LATEST_VERSION=$(git describe --tags "$(git rev-list --tags --max-count=1)")

log "Current version: $CURRENT_VERSION"
log "Latest version: $LATEST_VERSION"

# Check if there's a new version
if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
    log "Already on latest version ($LATEST_VERSION). No deployment needed."
    exit 0
fi

log "🚀 New version available: $LATEST_VERSION"
log "Starting deployment..."

# Checkout the latest release
git checkout "$LATEST_VERSION"

# Run deployment script
bash deployment/deploy.sh 2>&1 | tee -a "$DEPLOY_LOG"

log "✅ Successfully deployed version $LATEST_VERSION"

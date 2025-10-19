#!/bin/bash
set -e

echo "🚀 Starting deployment..."

# Configuration
APP_DIR="/opt/token-bowl-chat-server"
SERVICE_NAME="token-bowl-chat"

# Navigate to app directory
cd "$APP_DIR"

# Activate virtual environment
source .venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
uv pip install -e .

# Run database migrations (if using alembic in the future)
# echo "🗄️  Running database migrations..."
# alembic upgrade head

# Restart the service
echo "🔄 Restarting service..."
sudo systemctl restart "$SERVICE_NAME"

# Wait a moment for service to start
sleep 2

# Check service status
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Service restarted successfully"
else
    echo "❌ Service failed to start"
    sudo systemctl status "$SERVICE_NAME" --no-pager
    exit 1
fi

echo "✅ Deployment completed successfully!"

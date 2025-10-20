#!/bin/bash
set -e

echo "🚀 Starting deployment..."

# Configuration
APP_DIR="/opt/api.tokenbowl.ai"
SERVICE_NAME="api.tokenbowl.ai"

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
sudo supervisorctl restart "$SERVICE_NAME"

# Wait a moment for service to start
sleep 2

# Check service status
if sudo supervisorctl status "$SERVICE_NAME" | grep -q "RUNNING"; then
    echo "✅ Service restarted successfully"
else
    echo "❌ Service failed to start"
    sudo supervisorctl status "$SERVICE_NAME"
    exit 1
fi

echo "✅ Deployment completed successfully!"

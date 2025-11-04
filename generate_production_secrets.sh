#!/bin/bash

# Production Secrets Generator for Token Bowl Chat Server v2.0.0
# This script generates all required secrets for production deployment

echo "🔐 Generating production secrets for Token Bowl Chat Server..."
echo ""

# Generate secrets
CENTRIFUGO_TOKEN_SECRET=$(openssl rand -hex 32)
CENTRIFUGO_API_KEY=$(openssl rand -hex 32)
CENTRIFUGO_ADMIN_SECRET=$(openssl rand -hex 32)
CENTRIFUGO_ADMIN_PASSWORD=$(openssl rand -base64 24)
DATABASE_ENCRYPTION_KEY=$(openssl rand -hex 32)

# Create production .env file
cat > production.env << EOF
# Token Bowl Chat Server Production Environment Variables
# Generated on $(date)

# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
RELOAD=false

# Centrifugo Configuration
ENABLE_CENTRIFUGO=true
CENTRIFUGO_URL=http://localhost:8001
CENTRIFUGO_TOKEN_SECRET=$CENTRIFUGO_TOKEN_SECRET
CENTRIFUGO_API_KEY=$CENTRIFUGO_API_KEY

# Database
DATABASE_URL=sqlite:///./chat.db
DATABASE_ENCRYPTION_KEY=$DATABASE_ENCRYPTION_KEY

# Message Settings
MESSAGE_HISTORY_LIMIT=1000
WEBHOOK_TIMEOUT=10.0
WEBHOOK_MAX_RETRIES=3

# Stytch Configuration (if using)
# STYTCH_PROJECT_ID=your_project_id
# STYTCH_SECRET=your_secret
# STYTCH_ENV=live

# CORS Settings (update with your domain)
CORS_ORIGINS=["https://yourdomain.com", "https://www.yourdomain.com"]
EOF

# Create production Centrifugo config
cat > centrifugo-config-production.json << EOF
{
  "token_hmac_secret_key": "$CENTRIFUGO_TOKEN_SECRET",
  "api_key": "$CENTRIFUGO_API_KEY",
  "admin_password": "$CENTRIFUGO_ADMIN_PASSWORD",
  "admin_secret": "$CENTRIFUGO_ADMIN_SECRET",
  "allowed_origins": ["https://yourdomain.com", "https://www.yourdomain.com"],
  "log_level": "info",
  "health": true,
  "client_insecure": false,
  "namespaces": [
    {
      "name": "room",
      "presence": true,
      "join_leave": true,
      "history_size": 100,
      "history_ttl": "300s"
    },
    {
      "name": "user",
      "presence": true,
      "join_leave": false,
      "history_size": 50,
      "history_ttl": "300s"
    }
  ]
}
EOF

echo "✅ Production secrets generated!"
echo ""
echo "📁 Files created:"
echo "  - production.env (FastAPI environment variables)"
echo "  - centrifugo-config-production.json (Centrifugo configuration)"
echo ""
echo "⚠️  IMPORTANT: Update the following in the files:"
echo "  1. Replace 'yourdomain.com' with your actual domain"
echo "  2. Add Stytch credentials if using authentication"
echo "  3. Update CENTRIFUGO_URL if not using localhost"
echo ""
echo "🔐 Keep these files secure and never commit them to git!"
#!/bin/bash

# Production Deployment Script for Token Bowl Chat Server v2.0.0
# This script automates the deployment process

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Token Bowl Chat Server v2.0.0 Production Deployment${NC}"
echo ""

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}This script should not be run as root!${NC}"
   exit 1
fi

# Parse arguments
DOMAIN=${1:-""}
EMAIL=${2:-""}
DEPLOY_METHOD=${3:-"docker"}  # docker or systemd

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Usage: $0 <domain> <email> [docker|systemd]"
    echo "Example: $0 api.tokenbowl.ai admin@tokenbowl.ai docker"
    exit 1
fi

echo -e "${GREEN}Configuration:${NC}"
echo "  Domain: $DOMAIN"
echo "  Email: $EMAIL"
echo "  Method: $DEPLOY_METHOD"
echo ""

# Step 1: Install dependencies
echo -e "${YELLOW}Step 1: Installing system dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    docker.io docker-compose \
    git curl wget htop \
    sqlite3 redis-server

# Step 2: Generate production secrets
echo -e "${YELLOW}Step 2: Generating production secrets...${NC}"
if [ ! -f "production.env" ]; then
    chmod +x generate_production_secrets.sh
    ./generate_production_secrets.sh

    # Update domain in generated files
    sed -i "s/yourdomain.com/$DOMAIN/g" production.env
    sed -i "s/yourdomain.com/$DOMAIN/g" centrifugo-config-production.json
    sed -i "s/yourdomain.com/$DOMAIN/g" nginx.production.conf
else
    echo "Production secrets already exist, skipping..."
fi

# Step 3: Set up SSL certificates
echo -e "${YELLOW}Step 3: Setting up SSL certificates...${NC}"
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    sudo certbot certonly --standalone \
        -d $DOMAIN \
        -d ws.$DOMAIN \
        --non-interactive \
        --agree-tos \
        --email $EMAIL
else
    echo "SSL certificates already exist, skipping..."
fi

# Step 4: Deploy based on method
if [ "$DEPLOY_METHOD" = "docker" ]; then
    echo -e "${YELLOW}Step 4: Deploying with Docker Compose...${NC}"

    # Build and start containers
    docker-compose -f docker-compose.production.yml build
    docker-compose -f docker-compose.production.yml up -d

    # Wait for services to be healthy
    echo "Waiting for services to be healthy..."
    sleep 10
    docker-compose -f docker-compose.production.yml ps

else
    echo -e "${YELLOW}Step 4: Deploying with systemd...${NC}"

    # Create virtual environment
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -e ".[dev]"

    # Run database migrations
    alembic upgrade head

    # Create systemd service for FastAPI
    sudo tee /etc/systemd/system/tokenbowl-chat.service > /dev/null << EOF
[Unit]
Description=Token Bowl Chat Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
Environment="PATH=$PWD/venv/bin"
EnvironmentFile=$PWD/production.env
ExecStart=$PWD/venv/bin/uvicorn token_bowl_chat_server.server:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # Create systemd service for Centrifugo
    sudo tee /etc/systemd/system/centrifugo.service > /dev/null << EOF
[Unit]
Description=Centrifugo real-time messaging server
After=network.target

[Service]
Type=simple
User=$USER
ExecStart=/usr/local/bin/centrifugo --config=$PWD/centrifugo-config-production.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # Download and install Centrifugo if not present
    if [ ! -f "/usr/local/bin/centrifugo" ]; then
        wget https://github.com/centrifugal/centrifugo/releases/download/v5.4.9/centrifugo_5.4.9_linux_amd64.tar.gz
        tar xzf centrifugo_5.4.9_linux_amd64.tar.gz
        sudo mv centrifugo /usr/local/bin/
        rm centrifugo_5.4.9_linux_amd64.tar.gz
    fi

    # Start services
    sudo systemctl daemon-reload
    sudo systemctl enable tokenbowl-chat centrifugo
    sudo systemctl start tokenbowl-chat centrifugo
fi

# Step 5: Configure Nginx
echo -e "${YELLOW}Step 5: Configuring Nginx...${NC}"
sudo cp nginx.production.conf /etc/nginx/sites-available/tokenbowl
sudo ln -sf /etc/nginx/sites-available/tokenbowl /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Step 6: Set up monitoring
echo -e "${YELLOW}Step 6: Setting up monitoring...${NC}"
cat > check_health.sh << 'EOF'
#!/bin/bash
# Health check script

API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
WS_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health)

if [ "$API_HEALTH" != "200" ]; then
    echo "API server is unhealthy: $API_HEALTH"
    exit 1
fi

if [ "$WS_HEALTH" != "200" ]; then
    echo "WebSocket server is unhealthy: $WS_HEALTH"
    exit 1
fi

echo "All services are healthy"
EOF
chmod +x check_health.sh

# Add to crontab for monitoring
(crontab -l 2>/dev/null; echo "*/5 * * * * $PWD/check_health.sh || systemctl restart tokenbowl-chat centrifugo") | crontab -

# Step 7: Verify deployment
echo -e "${YELLOW}Step 7: Verifying deployment...${NC}"
sleep 5

# Test endpoints
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/health)
WS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://ws.$DOMAIN/health)

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "API Server: https://$DOMAIN"
echo "  Status: $API_STATUS"
echo ""
echo "WebSocket Server: https://ws.$DOMAIN"
echo "  Status: $WS_STATUS"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update your frontend to use these endpoints"
echo "2. Test WebSocket connections with the test client"
echo "3. Monitor logs:"
if [ "$DEPLOY_METHOD" = "docker" ]; then
    echo "   docker-compose -f docker-compose.production.yml logs -f"
else
    echo "   sudo journalctl -u tokenbowl-chat -f"
    echo "   sudo journalctl -u centrifugo -f"
fi
echo "4. Set up backups for chat.db"
echo ""
echo -e "${GREEN}✅ Deployment successful!${NC}"
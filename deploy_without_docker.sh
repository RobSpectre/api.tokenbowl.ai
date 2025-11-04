#!/bin/bash

# Deployment script for Token Bowl Chat Server WITHOUT Docker
# This uses systemd services instead

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Token Bowl Chat Server - Non-Docker Production Deployment${NC}"
echo ""

# Step 1: Install system dependencies
echo -e "${YELLOW}Step 1: Installing system dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    nginx certbot python3-certbot-nginx \
    git curl wget sqlite3 \
    build-essential

# Step 2: Set up Python environment
echo -e "${YELLOW}Step 2: Setting up Python environment...${NC}"
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# Step 3: Generate production configuration
echo -e "${YELLOW}Step 3: Generating production configuration...${NC}"
if [ ! -f "production.env" ]; then
    ./generate_production_secrets.sh
    echo -e "${RED}IMPORTANT: Edit production.env and update domain names!${NC}"
    read -p "Press enter after updating production.env..."
fi

# Step 4: Set up database
echo -e "${YELLOW}Step 4: Setting up database...${NC}"
source venv/bin/activate
alembic upgrade head

# Step 5: Install Centrifugo
echo -e "${YELLOW}Step 5: Installing Centrifugo...${NC}"
if [ ! -f "/usr/local/bin/centrifugo" ]; then
    wget https://github.com/centrifugal/centrifugo/releases/download/v5.4.9/centrifugo_5.4.9_linux_amd64.tar.gz
    tar xzf centrifugo_5.4.9_linux_amd64.tar.gz
    sudo mv centrifugo /usr/local/bin/
    sudo chmod +x /usr/local/bin/centrifugo
    rm centrifugo_5.4.9_linux_amd64.tar.gz
    echo "Centrifugo installed successfully"
else
    echo "Centrifugo already installed"
fi

# Step 6: Create systemd service for FastAPI
echo -e "${YELLOW}Step 6: Creating FastAPI systemd service...${NC}"
sudo tee /etc/systemd/system/tokenbowl-chat.service > /dev/null << EOF
[Unit]
Description=Token Bowl Chat Server (FastAPI)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PWD
Environment="PATH=$PWD/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$PWD/production.env
ExecStartPre=$PWD/venv/bin/alembic upgrade head
ExecStart=$PWD/venv/bin/uvicorn token_bowl_chat_server.server:app \\
    --host 0.0.0.0 \\
    --port 8000 \\
    --workers 4 \\
    --log-level info \\
    --access-log \\
    --use-colors

# Restart policy
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PWD

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Step 7: Create systemd service for Centrifugo
echo -e "${YELLOW}Step 7: Creating Centrifugo systemd service...${NC}"
sudo tee /etc/systemd/system/centrifugo.service > /dev/null << EOF
[Unit]
Description=Centrifugo real-time messaging server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PWD
ExecStart=/usr/local/bin/centrifugo --config=$PWD/centrifugo-config-production.json
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PWD

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Step 8: Enable and start services
echo -e "${YELLOW}Step 8: Starting services...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable tokenbowl-chat centrifugo
sudo systemctl start centrifugo
sleep 2
sudo systemctl start tokenbowl-chat

# Step 9: Check service status
echo -e "${YELLOW}Step 9: Checking service status...${NC}"
sudo systemctl status tokenbowl-chat --no-pager
sudo systemctl status centrifugo --no-pager

# Step 10: Create log rotation
echo -e "${YELLOW}Step 10: Setting up log rotation...${NC}"
sudo tee /etc/logrotate.d/tokenbowl > /dev/null << 'EOF'
/var/log/tokenbowl/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        systemctl reload tokenbowl-chat >/dev/null 2>&1 || true
    endscript
}
EOF

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "Services are running:"
echo "  - FastAPI: http://localhost:8000"
echo "  - Centrifugo: http://localhost:8001"
echo ""
echo "Useful commands:"
echo "  View logs: sudo journalctl -u tokenbowl-chat -f"
echo "           sudo journalctl -u centrifugo -f"
echo ""
echo "  Restart:  sudo systemctl restart tokenbowl-chat centrifugo"
echo "  Stop:     sudo systemctl stop tokenbowl-chat centrifugo"
echo "  Status:   sudo systemctl status tokenbowl-chat centrifugo"
echo ""
echo "Next steps:"
echo "1. Configure Nginx (sudo nginx -t && sudo systemctl reload nginx)"
echo "2. Set up SSL certificates with Let's Encrypt"
echo "3. Update your frontend to use the API endpoints"
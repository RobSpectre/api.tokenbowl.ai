# Deployment Guide

This guide covers automated deployment to your Digital Ocean droplet when you publish a GitHub release.

Since you're using **Cloudflare Zero Trust for SSH**, we provide two deployment approaches:

1. **Self-Hosted GitHub Actions Runner** (Recommended) - GitHub deploys directly from your server
2. **Pull-Based Deployment** (Simpler alternative) - Server checks for new releases automatically

---

## Option 1: Self-Hosted GitHub Actions Runner (Recommended)

This approach runs a GitHub Actions runner on your droplet, allowing deployments to happen locally without needing inbound SSH access.

### Setup Steps

#### 1. Install the Application

SSH into your droplet via Cloudflare Zero Trust:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
sudo mkdir -p /opt/token-bowl-chat-server
sudo chown $USER:$USER /opt/token-bowl-chat-server
cd /opt
git clone https://github.com/YOUR_USERNAME/token-bowl-chat-server.git
cd token-bowl-chat-server

# Set up Python virtual environment
uv venv
source .venv/bin/activate
uv pip install -e .

# Create .env file with your configuration
sudo nano /opt/token-bowl-chat-server/.env
```

Example `.env` file:
```bash
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
STYTCH_PROJECT_ID=your-project-id
STYTCH_SECRET=your-secret
STYTCH_ENVIRONMENT=live
```

#### 2. Set Up Systemd Service

```bash
# Create log directory
sudo mkdir -p /var/log/token-bowl-chat
sudo chown www-data:www-data /var/log/token-bowl-chat

# Install systemd service
sudo cp deployment/token-bowl-chat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable token-bowl-chat
sudo systemctl start token-bowl-chat

# Check status
sudo systemctl status token-bowl-chat
```

#### 3. Set Up GitHub Actions Self-Hosted Runner

On your GitHub repository page:

1. Go to **Settings** → **Actions** → **Runners**
2. Click **New self-hosted runner**
3. Select **Linux** and **x64**
4. Follow the installation commands on your droplet:

```bash
# Create a folder for the runner
mkdir -p ~/actions-runner && cd ~/actions-runner

# Download (use the commands from GitHub's UI - they include your specific token)
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz

# Extract
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# Configure (use the token from GitHub's UI)
./config.sh --url https://github.com/YOUR_USERNAME/token-bowl-chat-server --token YOUR_TOKEN

# Install as a service
sudo ./svc.sh install
sudo ./svc.sh start
```

#### 4. Give Runner Permissions for Deployment

The runner needs to restart the systemd service:

```bash
# Allow the runner user to restart the service without a password
sudo visudo

# Add this line (replace 'runner-user' with your runner's username):
runner-user ALL=(ALL) NOPASSWD: /bin/systemctl restart token-bowl-chat, /bin/systemctl is-active token-bowl-chat, /bin/systemctl status token-bowl-chat
```

#### 5. Make Deploy Script Executable

```bash
chmod +x /opt/token-bowl-chat-server/deployment/deploy.sh
```

### How to Deploy

1. Make your code changes and commit them
2. Create a new release on GitHub:
   - Go to **Releases** → **Create a new release**
   - Create a new tag (e.g., `v1.0.0`)
   - Click **Publish release**
3. GitHub Actions will automatically deploy to your server
4. Monitor the deployment in the **Actions** tab

---

## Option 2: Pull-Based Deployment (Simpler Alternative)

With this approach, your server checks for new GitHub releases every 5 minutes and automatically deploys them.

### Setup Steps

#### 1-2. Follow Steps 1-2 from Option 1

Complete the application installation and systemd service setup.

#### 3. Configure the Pull-Based Deployment

```bash
# Edit the check-deploy.sh script to add your repository URL
sudo nano /opt/token-bowl-chat-server/deployment/check-deploy.sh

# Update this line:
REPO_URL="https://github.com/YOUR_USERNAME/token-bowl-chat-server.git"

# Make scripts executable
chmod +x /opt/token-bowl-chat-server/deployment/check-deploy.sh
chmod +x /opt/token-bowl-chat-server/deployment/deploy.sh
```

#### 4. Install Systemd Timer

```bash
# Copy timer and service files
sudo cp deployment/token-bowl-deploy.service /etc/systemd/system/
sudo cp deployment/token-bowl-deploy.timer /etc/systemd/system/

# Give www-data user permission to restart service
sudo visudo

# Add this line:
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart token-bowl-chat, /bin/systemctl is-active token-bowl-chat, /bin/systemctl status token-bowl-chat

# Enable and start the timer
sudo systemctl daemon-reload
sudo systemctl enable token-bowl-deploy.timer
sudo systemctl start token-bowl-deploy.timer

# Check timer status
sudo systemctl status token-bowl-deploy.timer

# View recent deployment logs
sudo tail -f /var/log/token-bowl-chat/deploy.log
```

### How to Deploy

1. Make your code changes and commit them
2. Create a new release on GitHub
3. Wait up to 5 minutes for the server to detect and deploy the new release
4. Check deployment logs: `sudo tail -f /var/log/token-bowl-chat/deploy.log`

---

## Nginx Configuration (Optional but Recommended)

If you want to serve the application via HTTPS with a domain name:

```bash
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx

# Create Nginx config
sudo nano /etc/nginx/sites-available/token-bowl-chat
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/token-bowl-chat /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

---

## Monitoring & Troubleshooting

### Check Application Logs

```bash
# Application logs
sudo journalctl -u token-bowl-chat -f

# Deployment logs (Option 2 only)
sudo tail -f /var/log/token-bowl-chat/deploy.log
```

### Check Service Status

```bash
# Check if running
sudo systemctl status token-bowl-chat

# Restart service
sudo systemctl restart token-bowl-chat

# View recent logs
sudo journalctl -u token-bowl-chat -n 100
```

### Test Health Endpoint

```bash
curl http://localhost:8000/health
```

### Manual Deployment

If you need to deploy manually:

```bash
cd /opt/token-bowl-chat-server
git fetch --tags
git checkout v1.0.0  # Replace with your version
bash deployment/deploy.sh
```

---

## Rollback Procedure

If a deployment breaks something:

```bash
cd /opt/token-bowl-chat-server

# List available versions
git tag

# Checkout previous version
git checkout v0.9.0  # Replace with previous version

# Deploy
bash deployment/deploy.sh
```

---

## Comparison: Self-Hosted Runner vs Pull-Based

| Feature | Self-Hosted Runner | Pull-Based |
|---------|-------------------|------------|
| **Deployment Speed** | Immediate | Up to 5 minutes |
| **Setup Complexity** | More complex | Simpler |
| **GitHub Visibility** | Shows in Actions tab | No GitHub visibility |
| **Failure Notifications** | GitHub notifications | Check logs manually |
| **Resource Usage** | Runner process always running | Minimal (checks every 5 min) |
| **Recommended For** | Production | Development/staging |

---

## Security Considerations

1. **Database Backups**: Set up automatic database backups
2. **Secrets Management**: Keep `.env` file secure (never commit to git)
3. **Firewall**: Ensure port 8000 is not exposed (use Nginx as reverse proxy)
4. **Updates**: Keep the OS and dependencies updated
5. **Monitoring**: Set up monitoring/alerting for the service

---

## Next Steps

1. Set up database backups
2. Configure monitoring (e.g., UptimeRobot, Datadog)
3. Set up log aggregation (optional)
4. Configure alerts for deployment failures

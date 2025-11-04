# Managing Token Bowl Chat Server with systemd (No Docker)

## Quick Start

```bash
# Deploy without Docker
chmod +x deploy_without_docker.sh
./deploy_without_docker.sh
```

## Service Management Commands

### Check Status
```bash
# Both services
sudo systemctl status tokenbowl-chat centrifugo

# Individual services
sudo systemctl status tokenbowl-chat
sudo systemctl status centrifugo
```

### Start/Stop/Restart
```bash
# Start services
sudo systemctl start tokenbowl-chat centrifugo

# Stop services
sudo systemctl stop tokenbowl-chat centrifugo

# Restart services
sudo systemctl restart tokenbowl-chat centrifugo

# Reload configuration (without dropping connections)
sudo systemctl reload tokenbowl-chat
```

### View Logs
```bash
# FastAPI logs (real-time)
sudo journalctl -u tokenbowl-chat -f

# Centrifugo logs (real-time)
sudo journalctl -u centrifugo -f

# Last 100 lines
sudo journalctl -u tokenbowl-chat -n 100

# Logs from last hour
sudo journalctl -u tokenbowl-chat --since "1 hour ago"

# Today's logs
sudo journalctl -u tokenbowl-chat --since today
```

## File Locations

```
/home/youruser/api.tokenbowl.ai/
├── venv/                       # Python virtual environment
├── production.env              # Environment variables
├── centrifugo-config-production.json  # Centrifugo config
├── chat.db                     # SQLite database
└── logs/                       # Application logs

/etc/systemd/system/
├── tokenbowl-chat.service      # FastAPI service
└── centrifugo.service          # Centrifugo service

/usr/local/bin/
└── centrifugo                  # Centrifugo binary
```

## Updating the Application

```bash
# Navigate to app directory
cd ~/api.tokenbowl.ai

# Pull latest code
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Update dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Restart services
sudo systemctl restart tokenbowl-chat centrifugo
```

## Monitoring

### Health Checks
```bash
# Check if services are running
curl http://localhost:8000/health  # FastAPI
curl http://localhost:8001/health  # Centrifugo

# Check service resource usage
sudo systemctl status tokenbowl-chat | grep Memory
```

### Automatic Restart on Failure
Services are configured to automatically restart if they crash:
- `Restart=always` - Always restart on failure
- `RestartSec=10` - Wait 10 seconds before restart

### Monitor with systemd
```bash
# See all service events
sudo journalctl -u tokenbowl-chat -u centrifugo --since "1 hour ago"

# Check for errors only
sudo journalctl -u tokenbowl-chat -p err
```

## Performance Tuning

### Adjust Worker Count
Edit `/etc/systemd/system/tokenbowl-chat.service`:
```ini
ExecStart=/path/to/venv/bin/uvicorn ... --workers 4
```

Recommended workers:
- 1-2 CPU cores: 2 workers
- 4 CPU cores: 4 workers
- 8+ CPU cores: 8 workers

### Memory Limits
Add to service file if needed:
```ini
[Service]
MemoryMax=2G
MemoryHigh=1500M
```

### File Descriptor Limits
Already set in service files:
```ini
LimitNOFILE=65536  # Max open files
LimitNPROC=4096    # Max processes
```

## Troubleshooting

### Service Won't Start
```bash
# Check for errors
sudo journalctl -xe -u tokenbowl-chat

# Common issues:
# 1. Port already in use
sudo lsof -i :8000
sudo lsof -i :8001

# 2. Permission issues
ls -la production.env centrifugo-config-production.json

# 3. Python dependencies missing
source venv/bin/activate
pip install -e ".[dev]"
```

### High Memory Usage
```bash
# Check memory usage
ps aux | grep -E 'uvicorn|centrifugo'

# Restart to clear memory
sudo systemctl restart tokenbowl-chat centrifugo
```

### Database Locked (SQLite)
```bash
# Check for stuck processes
fuser chat.db

# If needed, restart services
sudo systemctl restart tokenbowl-chat
```

## Backup and Recovery

### Automated Backups
Add to crontab (`crontab -e`):
```bash
# Daily database backup at 2 AM
0 2 * * * sqlite3 /home/youruser/api.tokenbowl.ai/chat.db ".backup /backups/chat-$(date +\%Y\%m\%d).db"

# Weekly config backup
0 3 * * 0 tar -czf /backups/config-$(date +\%Y\%m\%d).tar.gz -C /home/youruser/api.tokenbowl.ai production.env centrifugo-config-production.json
```

### Manual Backup
```bash
# Database
sqlite3 chat.db ".backup chat-backup-$(date +%Y%m%d).db"

# Full backup
tar -czf tokenbowl-backup-$(date +%Y%m%d).tar.gz \
    chat.db \
    production.env \
    centrifugo-config-production.json
```

### Restore from Backup
```bash
# Stop services
sudo systemctl stop tokenbowl-chat centrifugo

# Restore database
cp /backups/chat-20241104.db chat.db

# Restart services
sudo systemctl start tokenbowl-chat centrifugo
```

## Security Notes

The systemd services include security hardening:
- `NoNewPrivileges=true` - Prevent privilege escalation
- `PrivateTmp=true` - Isolated /tmp directory
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=true` - No access to user home directories
- `ReadWritePaths=$PWD` - Only app directory is writable

## Useful Aliases

Add to `~/.bashrc`:
```bash
# Token Bowl aliases
alias tb-status='sudo systemctl status tokenbowl-chat centrifugo'
alias tb-restart='sudo systemctl restart tokenbowl-chat centrifugo'
alias tb-logs='sudo journalctl -u tokenbowl-chat -u centrifugo -f'
alias tb-api-logs='sudo journalctl -u tokenbowl-chat -f'
alias tb-ws-logs='sudo journalctl -u centrifugo -f'
alias tb-health='curl -s http://localhost:8000/health && echo && curl -s http://localhost:8001/health'
```
# Production Deployment Guide for Token Bowl Chat Server v2.0.0

## Prerequisites

- Ubuntu 20.04+ or similar Linux distribution
- Domain name pointed to your server (e.g., api.tokenbowl.ai)
- Root or sudo access
- At least 2GB RAM, 20GB disk space
- Ports 80, 443 open for HTTP/HTTPS

## Quick Deployment

```bash
# Clone the repository
git clone https://github.com/RobSpectre/api.tokenbowl.ai.git
cd api.tokenbowl.ai

# Run the automated deployment script
chmod +x deploy_production.sh
./deploy_production.sh api.yourdomain.com admin@yourdomain.com docker
```

## Manual Step-by-Step Deployment

### 1. Generate Production Secrets

```bash
chmod +x generate_production_secrets.sh
./generate_production_secrets.sh
```

**Important**: Edit the generated files to replace `yourdomain.com` with your actual domain.

### 2. Install Dependencies

```bash
# System packages
sudo apt update
sudo apt install -y python3.11 python3.11-venv nginx certbot python3-certbot-nginx

# Docker (if using Docker deployment)
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
```

### 3. Set Up SSL Certificates

```bash
# Get SSL certificates from Let's Encrypt
sudo certbot certonly --standalone \
  -d api.yourdomain.com \
  -d ws.yourdomain.com \
  --non-interactive \
  --agree-tos \
  --email admin@yourdomain.com
```

### 4. Deploy the Services

#### Option A: Docker Deployment (Recommended)

```bash
# Build and start services
docker-compose -f docker-compose.production.yml up -d

# Check status
docker-compose -f docker-compose.production.yml ps

# View logs
docker-compose -f docker-compose.production.yml logs -f
```

#### Option B: Systemd Deployment

```bash
# Set up Python environment
python3.11 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Install Centrifugo
wget https://github.com/centrifugal/centrifugo/releases/download/v5.4.9/centrifugo_5.4.9_linux_amd64.tar.gz
tar xzf centrifugo_5.4.9_linux_amd64.tar.gz
sudo mv centrifugo /usr/local/bin/

# Start services
sudo systemctl start tokenbowl-chat centrifugo
sudo systemctl enable tokenbowl-chat centrifugo
```

### 5. Configure Nginx

```bash
# Copy nginx configuration
sudo cp nginx.production.conf /etc/nginx/sites-available/tokenbowl
sudo ln -sf /etc/nginx/sites-available/tokenbowl /etc/nginx/sites-enabled/

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### 6. Verify Deployment

```bash
# Check health endpoints
curl https://api.yourdomain.com/health
curl https://ws.yourdomain.com/health

# Test WebSocket connection
python test_centrifugo_integration.py
```

## Production Environment Variables

Edit `production.env` with your specific values:

```env
# Required changes
CORS_ORIGINS=["https://yourdomain.com"]  # Your frontend domain
CENTRIFUGO_URL=http://localhost:8001     # Or https://ws.yourdomain.com if external

# Optional Stytch authentication
STYTCH_PROJECT_ID=your_project_id
STYTCH_SECRET=your_secret
STYTCH_ENV=live

# Database (optional - defaults to SQLite)
DATABASE_URL=postgresql://user:password@localhost/dbname
```

## Security Checklist

- [ ] Generated new secrets (not using defaults)
- [ ] SSL certificates installed and auto-renewal configured
- [ ] Firewall configured (only ports 80, 443 open)
- [ ] Nginx rate limiting enabled
- [ ] CORS origins restricted to your domains
- [ ] Admin passwords changed from defaults
- [ ] Database backups configured
- [ ] Log rotation configured
- [ ] Monitoring/alerting set up

## Monitoring

### View Logs

```bash
# Docker deployment
docker-compose -f docker-compose.production.yml logs -f chat-server
docker-compose -f docker-compose.production.yml logs -f centrifugo

# Systemd deployment
sudo journalctl -u tokenbowl-chat -f
sudo journalctl -u centrifugo -f

# Nginx logs
sudo tail -f /var/log/nginx/api.tokenbowl.*.log
```

### Health Checks

The deployment script creates `check_health.sh` which runs every 5 minutes via cron.

Manual health check:
```bash
./check_health.sh
```

## Backup Strategy

### Database Backup

```bash
# SQLite backup (daily cron job)
sqlite3 chat.db ".backup /backups/chat-$(date +%Y%m%d).db"

# PostgreSQL backup (if using)
pg_dump -U username dbname > /backups/chat-$(date +%Y%m%d).sql
```

### Configuration Backup

```bash
# Backup all config files
tar -czf /backups/config-$(date +%Y%m%d).tar.gz \
  production.env \
  centrifugo-config-production.json \
  nginx.production.conf
```

## Updating the Application

```bash
# Pull latest code
git pull origin main

# Docker deployment
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

# Systemd deployment
source venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
sudo systemctl restart tokenbowl-chat centrifugo
```

## Troubleshooting

### Common Issues

1. **WebSocket connections failing**
   - Check Nginx WebSocket headers
   - Verify Centrifugo is running: `curl http://localhost:8001/health`
   - Check CORS settings in both FastAPI and Centrifugo

2. **Authentication errors**
   - Verify secrets match between FastAPI and Centrifugo
   - Check token expiration settings
   - Review logs for specific error messages

3. **Database locked errors**
   - Only occurs with SQLite under high load
   - Consider switching to PostgreSQL for production

4. **SSL certificate issues**
   - Check certificate renewal: `sudo certbot renew --dry-run`
   - Verify Nginx SSL configuration

### Debug Commands

```bash
# Test FastAPI directly
curl -H "X-API-Key: test" http://localhost:8000/health

# Test Centrifugo directly
curl http://localhost:8001/health

# Check port usage
sudo netstat -tlnp | grep -E '8000|8001'

# Check service status
systemctl status tokenbowl-chat centrifugo nginx

# Test WebSocket connection
wscat -c wss://ws.yourdomain.com/connection
```

## Performance Tuning

### FastAPI Workers

Adjust in `docker-compose.production.yml` or systemd service:
```bash
--workers 4  # Increase based on CPU cores
```

### Nginx Tuning

Edit `/etc/nginx/nginx.conf`:
```nginx
worker_processes auto;
worker_connections 4096;
keepalive_timeout 65;
keepalive_requests 100;
```

### Database Optimization

For SQLite:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;
```

For PostgreSQL, use connection pooling with pgbouncer.

## Support

- GitHub Issues: https://github.com/RobSpectre/api.tokenbowl.ai/issues
- Documentation: https://docs.tokenbowl.ai
- Email: support@tokenbowl.ai
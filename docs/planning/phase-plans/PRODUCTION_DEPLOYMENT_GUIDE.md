# Production Deployment Guide
## Goldsmith ERP - Metal Inventory Management System

**Last Updated:** 2025-11-09
**Version:** 0.1.0 (Pre-Production)

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Server Requirements](#server-requirements)
3. [Database Setup](#database-setup)
4. [Application Deployment](#application-deployment)
5. [SSL/TLS Configuration](#ssltls-configuration)
6. [Security Hardening](#security-hardening)
7. [Monitoring & Logging](#monitoring--logging)
8. [Backup Strategy](#backup-strategy)
9. [Performance Optimization](#performance-optimization)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Before You Begin
- [ ] Domain name configured (e.g., `erp.yourdomain.com`)
- [ ] Server with at least 4GB RAM, 2 CPU cores, 20GB storage
- [ ] Ubuntu 22.04 LTS or newer (recommended)
- [ ] Root or sudo access to the server
- [ ] Basic knowledge of Linux, PostgreSQL, and systemd

### Required Software
- Python 3.11+
- PostgreSQL 14+
- Nginx (reverse proxy)
- Redis 6+ (for rate limiting and caching)
- Poetry (Python dependency management)
- Certbot (for SSL certificates)

---

## Server Requirements

### Minimum Hardware
- **CPU:** 2 cores
- **RAM:** 4GB
- **Storage:** 20GB SSD
- **Network:** 100 Mbps

### Recommended Hardware (for 10-50 concurrent users)
- **CPU:** 4 cores
- **RAM:** 8GB
- **Storage:** 50GB NVMe SSD
- **Network:** 1 Gbps

---

## Database Setup

### 1. Install PostgreSQL

```bash
# Update package lists
sudo apt update

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 2. Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL shell:
CREATE DATABASE goldsmith_erp_prod;
CREATE USER goldsmith_user WITH ENCRYPTED PASSWORD 'YOUR_SECURE_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON DATABASE goldsmith_erp_prod TO goldsmith_user;

# Grant schema permissions (PostgreSQL 15+)
\c goldsmith_erp_prod
GRANT ALL ON SCHEMA public TO goldsmith_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO goldsmith_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO goldsmith_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO goldsmith_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO goldsmith_user;

\q
```

### 3. Secure PostgreSQL

Edit `/etc/postgresql/14/main/postgresql.conf`:

```conf
# Listen on localhost only (unless remote access needed)
listen_addresses = 'localhost'

# Connection limits
max_connections = 100

# Memory settings (adjust based on available RAM)
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
work_mem = 16MB
```

Edit `/etc/postgresql/14/main/pg_hba.conf`:

```conf
# Only allow local connections with password
local   all             all                                     md5
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### 4. Run Database Migrations

```bash
# Navigate to application directory
cd /opt/goldsmith_erp

# Activate virtual environment
poetry shell

# Run Alembic migrations
alembic upgrade head
```

---

## Application Deployment

### 1. Create Application User

```bash
# Create dedicated user (no login shell for security)
sudo useradd -r -s /bin/false goldsmith

# Create application directory
sudo mkdir -p /opt/goldsmith_erp
sudo chown goldsmith:goldsmith /opt/goldsmith_erp
```

### 2. Deploy Application Code

```bash
# Clone repository (or upload code)
cd /opt
sudo git clone https://github.com/your-org/goldsmith_erp.git
sudo chown -R goldsmith:goldsmith /opt/goldsmith_erp

# Switch to application directory
cd /opt/goldsmith_erp

# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
sudo -u goldsmith poetry install --no-dev --no-root
```

### 3. Configure Environment Variables

Create `/opt/goldsmith_erp/.env`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://goldsmith_user:YOUR_SECURE_PASSWORD_HERE@localhost/goldsmith_erp_prod

# Security
SECRET_KEY=GENERATE_STRONG_RANDOM_KEY_HERE  # Use: openssl rand -hex 32
JWT_SECRET_KEY=GENERATE_ANOTHER_STRONG_KEY_HERE
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Environment
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# CORS (adjust to your frontend domain)
CORS_ORIGINS=["https://erp.yourdomain.com"]

# Redis
REDIS_URL=redis://localhost:6379/0

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Email (optional - for notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@example.com
SMTP_PASSWORD=your-email-password
SMTP_FROM=noreply@yourdomain.com
```

**Important:** Set restrictive permissions on `.env`:
```bash
sudo chown goldsmith:goldsmith /opt/goldsmith_erp/.env
sudo chmod 600 /opt/goldsmith_erp/.env
```

### 4. Create Systemd Service

Create `/etc/systemd/system/goldsmith-erp.service`:

```ini
[Unit]
Description=Goldsmith ERP - FastAPI Application
After=network.target postgresql.service redis.service
Requires=postgresql.service

[Service]
Type=notify
User=goldsmith
Group=goldsmith
WorkingDirectory=/opt/goldsmith_erp
Environment="PATH=/opt/goldsmith_erp/.venv/bin"
EnvironmentFile=/opt/goldsmith_erp/.env
ExecStart=/opt/goldsmith_erp/.venv/bin/uvicorn goldsmith_erp.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --log-config /opt/goldsmith_erp/logging.conf

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=0

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/goldsmith_erp/logs

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable goldsmith-erp
sudo systemctl start goldsmith-erp

# Check status
sudo systemctl status goldsmith-erp
```

---

## SSL/TLS Configuration

### 1. Install Nginx

```bash
sudo apt install -y nginx
```

### 2. Configure Nginx

Create `/etc/nginx/sites-available/goldsmith-erp`:

```nginx
# HTTP - Redirect to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name erp.yourdomain.com;

    # Redirect all HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

# HTTPS
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name erp.yourdomain.com;

    # SSL Certificates (will be configured by Certbot)
    ssl_certificate /etc/letsencrypt/live/erp.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/erp.yourdomain.com/privkey.pem;

    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Max upload size (for order photos)
    client_max_body_size 10M;

    # Logging
    access_log /var/log/nginx/goldsmith-erp-access.log;
    error_log /var/log/nginx/goldsmith-erp-error.log;

    # Proxy to FastAPI application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for future real-time features)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint (no auth required)
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }

    # Static files (if serving from Nginx)
    location /static/ {
        alias /opt/goldsmith_erp/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/goldsmith-erp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3. Obtain SSL Certificate

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d erp.yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

---

## Security Hardening

### 1. Firewall Configuration (UFW)

```bash
# Install UFW
sudo apt install -y ufw

# Allow SSH (adjust port if needed)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### 2. Fail2Ban (Protection against brute-force)

```bash
# Install Fail2Ban
sudo apt install -y fail2ban

# Create Nginx jail
sudo nano /etc/fail2ban/jail.d/goldsmith-erp.conf
```

Add:
```ini
[goldsmith-erp-auth]
enabled = true
port = http,https
filter = goldsmith-erp-auth
logpath = /var/log/nginx/goldsmith-erp-access.log
maxretry = 5
bantime = 3600
findtime = 600
```

Create filter `/etc/fail2ban/filter.d/goldsmith-erp-auth.conf`:
```ini
[Definition]
failregex = ^<HOST> .* "POST /api/v1/auth/login HTTP/.*" 401
ignoreregex =
```

Restart Fail2Ban:
```bash
sudo systemctl restart fail2ban
sudo fail2ban-client status goldsmith-erp-auth
```

### 3. SSH Hardening

Edit `/etc/ssh/sshd_config`:
```conf
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
X11Forwarding no
```

Restart SSH:
```bash
sudo systemctl restart sshd
```

---

## Monitoring & Logging

### 1. Application Logging

The application uses structured JSON logging. Logs are written to:
- `/opt/goldsmith_erp/logs/app.log` (application logs)
- `/var/log/nginx/goldsmith-erp-access.log` (Nginx access)
- `/var/log/nginx/goldsmith-erp-error.log` (Nginx errors)

Configure log rotation `/etc/logrotate.d/goldsmith-erp`:
```conf
/opt/goldsmith_erp/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 goldsmith goldsmith
    sharedscripts
    postrotate
        systemctl reload goldsmith-erp > /dev/null 2>&1 || true
    endscript
}
```

### 2. Health Monitoring

Set up a cron job to monitor application health:

```bash
sudo nano /usr/local/bin/check-goldsmith-health.sh
```

Add:
```bash
#!/bin/bash
HEALTH_URL="http://localhost:8000/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE -ne 200 ]; then
    echo "$(date) - Health check failed! HTTP $RESPONSE" >> /var/log/goldsmith-health.log
    systemctl restart goldsmith-erp
fi
```

Make executable and add to crontab:
```bash
sudo chmod +x /usr/local/bin/check-goldsmith-health.sh
sudo crontab -e
```

Add:
```cron
*/5 * * * * /usr/local/bin/check-goldsmith-health.sh
```

---

## Backup Strategy

### 1. Database Backups

Create backup script `/usr/local/bin/backup-goldsmith-db.sh`:

```bash
#!/bin/bash
set -e

# Configuration
BACKUP_DIR="/var/backups/goldsmith_erp"
DB_NAME="goldsmith_erp_prod"
DB_USER="goldsmith_user"
RETENTION_DAYS=30

# Create backup directory
mkdir -p $BACKUP_DIR

# Generate filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/goldsmith_db_$TIMESTAMP.sql.gz"

# Perform backup
PGPASSWORD="YOUR_SECURE_PASSWORD_HERE" pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_FILE

# Verify backup
if [ -f "$BACKUP_FILE" ]; then
    echo "$(date) - Backup successful: $BACKUP_FILE" >> /var/log/goldsmith-backup.log
else
    echo "$(date) - Backup FAILED!" >> /var/log/goldsmith-backup.log
    exit 1
fi

# Clean old backups (older than RETENTION_DAYS)
find $BACKUP_DIR -name "goldsmith_db_*.sql.gz" -mtime +$RETENTION_DAYS -delete

# Optional: Upload to remote storage (S3, rsync, etc.)
# aws s3 cp $BACKUP_FILE s3://your-bucket/goldsmith-erp-backups/
```

Make executable:
```bash
sudo chmod +x /usr/local/bin/backup-goldsmith-db.sh
sudo chmod 700 /usr/local/bin/backup-goldsmith-db.sh  # Protect password
```

Schedule daily backups:
```bash
sudo crontab -e
```

Add:
```cron
0 2 * * * /usr/local/bin/backup-goldsmith-db.sh
```

### 2. Application Data Backup

```bash
# Backup uploaded files, configs, etc.
sudo rsync -av /opt/goldsmith_erp/uploads/ /var/backups/goldsmith_erp/uploads/
```

---

## Performance Optimization

### 1. Redis Setup (Caching & Rate Limiting)

```bash
# Install Redis
sudo apt install -y redis-server

# Configure Redis
sudo nano /etc/redis/redis.conf
```

Key settings:
```conf
bind 127.0.0.1
maxmemory 256mb
maxmemory-policy allkeys-lru
```

Start Redis:
```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 2. PostgreSQL Optimization

```sql
-- Create indexes for frequently queried columns
CREATE INDEX CONCURRENTLY idx_orders_customer_id ON orders(customer_id);
CREATE INDEX CONCURRENTLY idx_orders_status ON orders(status);
CREATE INDEX CONCURRENTLY idx_orders_deadline ON orders(deadline);
CREATE INDEX CONCURRENTLY idx_metal_purchases_metal_type ON metal_purchases(metal_type);
CREATE INDEX CONCURRENTLY idx_metal_purchases_date ON metal_purchases(date_purchased);
CREATE INDEX CONCURRENTLY idx_material_usage_order_id ON material_usage(order_id);

-- Analyze tables for query planner
ANALYZE;
```

### 3. Application Performance

Update systemd service to use optimal Uvicorn workers:
```ini
# Number of workers = (2 * CPU cores) + 1
--workers 9  # For 4 CPU cores
```

---

## Troubleshooting

### Common Issues

**Issue: Application won't start**
```bash
# Check logs
sudo journalctl -u goldsmith-erp -n 50 --no-pager

# Check if port is in use
sudo lsof -i :8000

# Verify environment variables
sudo -u goldsmith cat /opt/goldsmith_erp/.env
```

**Issue: Database connection errors**
```bash
# Test PostgreSQL connection
sudo -u postgres psql -U goldsmith_user -d goldsmith_erp_prod -h localhost

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-14-main.log
```

**Issue: Nginx 502 Bad Gateway**
```bash
# Check if application is running
sudo systemctl status goldsmith-erp

# Check Nginx error logs
sudo tail -f /var/log/nginx/goldsmith-erp-error.log

# Test application directly
curl http://localhost:8000/health
```

**Issue: Slow performance**
```bash
# Check system resources
htop
free -h
df -h

# Check PostgreSQL active queries
sudo -u postgres psql -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC;"
```

---

## Post-Deployment Checklist

- [ ] Database migrations completed successfully
- [ ] Application starts without errors
- [ ] SSL certificate installed and valid
- [ ] Firewall configured (UFW)
- [ ] Fail2Ban active and monitoring
- [ ] Daily database backups scheduled
- [ ] Health monitoring active
- [ ] Log rotation configured
- [ ] Redis running and configured
- [ ] Admin user created (`POST /api/v1/auth/register`)
- [ ] API documentation accessible (`https://erp.yourdomain.com/docs`)
- [ ] Performance testing completed
- [ ] Security audit performed
- [ ] Team trained on system usage

---

## Maintenance Schedule

**Daily:**
- Automated database backups (2:00 AM)
- Health checks (every 5 minutes)

**Weekly:**
- Review application logs
- Check disk space usage
- Review failed login attempts (Fail2Ban)

**Monthly:**
- Update system packages (`sudo apt update && sudo apt upgrade`)
- Review and rotate SSL certificates if needed
- Database performance analysis
- Security audit

**Quarterly:**
- Full system backup test (restore to staging)
- Dependency updates (`poetry update`)
- Performance benchmarking
- Disaster recovery drill

---

## Support & Resources

- **Documentation:** https://docs.yourdomain.com/goldsmith-erp
- **Issue Tracker:** https://github.com/your-org/goldsmith_erp/issues
- **Security Contact:** security@yourdomain.com

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2025-11-09 | Initial production deployment guide |

---

**END OF GUIDE**

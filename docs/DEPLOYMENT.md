# Deployment Guide - Goldsmith ERP

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Database Migration](#database-migration)
4. [Environment Configuration](#environment-configuration)
5. [Running with Docker](#running-with-docker)
6. [Manual Deployment](#manual-deployment)
7. [Data Seeding](#data-seeding)
8. [Security Checklist](#security-checklist)
9. [GDPR Compliance](#gdpr-compliance)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This guide covers deploying the Goldsmith ERP system with full GDPR compliance features including:
- Customer data encryption
- Audit logging
- Data retention policies
- Consent management

**Current Version:** 1.0.0 (Phase 1.6 - GDPR Compliance Complete)

---

## Prerequisites

### Required Software

- **Python**: 3.11+
- **PostgreSQL**: 15+
- **Redis**: 7+
- **Docker** (optional): 24.0+
- **Poetry**: 1.6+

### System Requirements

- **Memory**: Minimum 2GB RAM
- **Disk Space**: Minimum 5GB
- **CPU**: 2+ cores recommended

---

## Database Migration

### Step 1: Verify Alembic Configuration

Check that `alembic.ini` is configured correctly:

```bash
cat alembic.ini | grep sqlalchemy.url
```

### Step 2: Check Current Migration Status

```bash
poetry run alembic current
```

### Step 3: Apply Migrations

```bash
# Apply all pending migrations
poetry run alembic upgrade head
```

**Available Migrations:**

1. **001_initial_schema** - Base ERP schema (users, materials, orders)
2. **002_gdpr_compliance** - GDPR-compliant customer management

### Step 4: Verify Migration Success

```bash
# Check current migration version
poetry run alembic current

# Should show: 002_gdpr_compliance (head)
```

### Rollback (if needed)

```bash
# Rollback one migration
poetry run alembic downgrade -1

# Rollback to specific version
poetry run alembic downgrade 001_initial_schema

# Rollback everything
poetry run alembic downgrade base
```

---

## Environment Configuration

### Step 1: Create .env File

```bash
cp .env.example .env
```

### Step 2: Configure Required Variables

Edit `.env`:

```bash
# Security (REQUIRED - CHANGE THESE!)
SECRET_KEY=your-super-secret-jwt-key-here-min-32-chars
ENCRYPTION_KEY=your-fernet-encryption-key-here

# Database
POSTGRES_USER=user
POSTGRES_PASSWORD=secure_password_here
POSTGRES_DB=goldsmith
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Application
DEBUG=false
HOST=0.0.0.0
PORT=8000
```

### Step 3: Generate Encryption Key

```bash
# Generate new Fernet encryption key for PII
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output and add to `.env`:

```
ENCRYPTION_KEY=<generated_key_here>
```

**⚠️ SECURITY WARNING:**
- Never commit `.env` to version control
- Use different keys for dev/staging/production
- Backup encryption keys securely (lost keys = lost data)

---

## Running with Docker

### Quick Start

```bash
# Start all services (database, redis, backend, frontend)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
```

The backend will automatically:
1. Apply database migrations
2. Start the API server on http://localhost:8000

### Services

- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Frontend**: http://localhost:3000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ deletes database data)
docker-compose down -v
```

---

## Manual Deployment

### Step 1: Install Dependencies

```bash
poetry install
```

### Step 2: Start PostgreSQL and Redis

```bash
# PostgreSQL
pg_ctl -D /path/to/data start

# Redis
redis-server
```

### Step 3: Apply Migrations

```bash
poetry run alembic upgrade head
```

### Step 4: Start Backend

```bash
# Development
poetry run uvicorn goldsmith_erp.main:app --reload

# Production
poetry run uvicorn goldsmith_erp.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Data Seeding

### Seed Initial Data

```bash
poetry run python scripts/seed_data.py
```

This creates:
- 4 staff users (admin, goldsmith, sales, manager)
- 6 data retention policies
- 4 sample customers (GDPR-compliant)
- Sample materials and orders

### Default Admin Credentials

```
Email: admin@goldsmith.de
Password: admin123
```

**⚠️ Change default passwords immediately in production!**

### Migration Script (Optional)

If you have existing customer data in the `users` table:

```bash
poetry run python scripts/migrate_users_to_customers.py
```

This script:
- Finds users with orders (actual customers)
- Creates customer records with GDPR compliance
- Updates order references
- Preserves all data

---

## Security Checklist

Before deploying to production:

### Critical Security Steps

- [ ] Change `SECRET_KEY` to random 32+ character string
- [ ] Generate new `ENCRYPTION_KEY` for production
- [ ] Change all default passwords
- [ ] Set `DEBUG=false` in production
- [ ] Configure HTTPS/TLS certificates
- [ ] Set up firewall rules (only ports 80, 443)
- [ ] Enable PostgreSQL authentication
- [ ] Restrict Redis access (bind to localhost or use password)
- [ ] Configure CORS allowed origins
- [ ] Set up backup strategy for encryption keys

### Middleware Enabled

The following security middleware is automatically enabled:

✅ **Request ID** - Unique ID for request correlation
✅ **Request Logging** - All requests logged
✅ **Security Headers** - OWASP best practices
✅ **Sensitive Data Redaction** - Prevents data leakage
✅ **Rate Limiting** - Protects against abuse
✅ **GDPR Audit Logging** - All customer data access logged
✅ **CORS** - Cross-origin security

### Rate Limits (Default)

- Anonymous: 100 requests/minute
- Authenticated: 300 requests/minute
- Admin: 1000 requests/minute
- GDPR Export: 5 requests/hour

### Security Headers Added

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (production only)
- `Content-Security-Policy`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` (disables unnecessary features)

---

## GDPR Compliance

### Implemented Features

#### Article 6: Legal Basis

- Legal basis tracked for all customer data (contract, consent, legitimate_interest)
- Cannot create customer without legal basis
- Audit trail of legal basis changes

#### Article 7: Consent Management

- Granular consent tracking (marketing, email, phone, SMS)
- Consent version control
- IP address and timestamp logging
- Easy consent withdrawal

#### Article 15: Right of Access

- Complete data export in JSON format
- Includes all personal data, audit logs, orders
- Export generation logged

#### Article 17: Right to Erasure

- Soft delete (reversible, preserves data)
- Hard delete (permanent, GDPR erasure)
- Anonymization (removes PII, preserves statistics)

#### Article 30: Records of Processing

- All customer data access logged
- Who, what, when, where, why tracked
- Audit logs retained

#### Article 32: Security of Processing

- PII encrypted at rest (phone, address)
- Encryption key management
- HTTPS enforced (production)
- Access control via JWT

#### Article 5(1)(e): Storage Limitation

- Retention deadlines tracked
- Automatic retention review list
- Default: 10 years for contract-based data

### GDPR Data Protection Officer (DPO)

**Recommendation:** Appoint a DPO if:
- Processing large scale sensitive data
- Operating in EU with EU customers
- Core activities involve systematic monitoring

### Data Processing Agreement (DPA)

If using third-party services (hosting, email, etc.), ensure:
- DPA in place with all processors
- GDPR compliance clauses included
- Sub-processor list documented

---

## Troubleshooting

### Migration Issues

**Problem:** Migration fails with "relation already exists"

**Solution:**
```bash
# Check current version
poetry run alembic current

# If showing old version, try stamping
poetry run alembic stamp head

# Then apply migrations
poetry run alembic upgrade head
```

**Problem:** Migration fails with "permission denied"

**Solution:**
```bash
# Ensure PostgreSQL user has permissions
psql -U postgres -d goldsmith
GRANT ALL PRIVILEGES ON DATABASE goldsmith TO user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO user;
```

### Encryption Issues

**Problem:** "ENCRYPTION_KEY not configured"

**Solution:**
```bash
# Generate key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to .env
echo "ENCRYPTION_KEY=<generated_key>" >> .env
```

**Problem:** "Failed to decrypt data: Invalid token"

**Solution:**
- Encryption key has changed
- Data was encrypted with different key
- Restore correct encryption key from backup

### Database Connection Issues

**Problem:** "Could not connect to database"

**Solution:**
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Check connection string in .env
echo $DATABASE_URL

# Test connection
psql -h localhost -U user -d goldsmith
```

### Redis Issues

**Problem:** "Failed to connect to Redis"

**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Should return: PONG

# If not running
redis-server
```

### Rate Limit Issues

**Problem:** Getting 429 Too Many Requests

**Solution:**
- Wait for rate limit window to reset
- For development, you can adjust limits in `middleware/rate_limiting.py`
- For production, consider implementing API key tiers

---

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok"}
```

### API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/api/v1/openapi.json

### Logs

```bash
# Docker
docker-compose logs -f backend

# Manual
tail -f logs/app.log
```

### Database Stats

```sql
-- Check customer count
SELECT COUNT(*) FROM customers WHERE is_deleted = false;

-- Check audit log count
SELECT COUNT(*) FROM customer_audit_logs;

-- Check retention status
SELECT
    data_retention_category,
    COUNT(*) as customer_count,
    COUNT(CASE WHEN retention_deadline < NOW() THEN 1 END) as expired_count
FROM customers
WHERE is_deleted = false
GROUP BY data_retention_category;
```

---

## Production Deployment

### Recommended Setup

1. **Web Server**: Nginx (reverse proxy)
2. **Application**: Uvicorn with Gunicorn (multi-worker)
3. **Database**: PostgreSQL (managed service recommended)
4. **Cache**: Redis (managed service recommended)
5. **Monitoring**: Sentry, DataDog, or similar
6. **Backups**: Automated daily backups

### Example Nginx Configuration

```nginx
server {
    listen 80;
    server_name erp.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name erp.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Systemd Service

Create `/etc/systemd/system/goldsmith-erp.service`:

```ini
[Unit]
Description=Goldsmith ERP API
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=goldsmith
WorkingDirectory=/opt/goldsmith-erp
Environment="PATH=/opt/goldsmith-erp/.venv/bin"
ExecStart=/opt/goldsmith-erp/.venv/bin/uvicorn goldsmith_erp.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable goldsmith-erp
sudo systemctl start goldsmith-erp
sudo systemctl status goldsmith-erp
```

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/arcsmax/goldsmith_erp/issues
- Documentation: See `/docs` directory
- Email: support@yourdomain.com

---

**Last Updated:** 2025-11-06
**Version:** 1.0.0 (Phase 1.6 Complete)

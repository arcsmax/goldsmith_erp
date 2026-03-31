# P0 Critical Tasks - Implementation Plan
**Date:** 2025-11-09
**Priority:** CRITICAL - Must complete before production deployment

---

## Task 1: Update CostCalculationService - Integrate with MetalInventoryService

### Current State
❌ **Problem:** CostCalculationService uses hardcoded material price (45 EUR/g)
```python
# Current code in cost_calculation_service.py
material_price_per_gram = material_price_per_gram or 45.00  # HARDCODED!
```

### Target State
✅ **Solution:** Use real inventory prices from MetalInventoryService

### Changes Required

#### 1.1 Database Changes
- **Add `metal_type` column to `orders` table**
  - Type: Enum (MetalType)
  - Nullable: True (for backwards compatibility)
  - Index: Yes (for filtering)

- **Add `costing_method` column to `orders` table**
  - Type: Enum (CostingMethod)
  - Default: FIFO
  - Nullable: True

- **Add `metal_purchase_id` column to `orders` table**
  - Type: Integer (Foreign Key → metal_purchases.id)
  - Nullable: True (only used if costing_method=SPECIFIC)
  - For tracking which specific batch was used

**Migration:** `alembic/versions/XXXXX_add_metal_type_to_orders.py`

#### 1.2 Model Changes
**File:** `src/goldsmith_erp/db/models.py`
```python
# Add to Order model:
metal_type = Column(SAEnum(MetalType), nullable=True, index=True)
costing_method_used = Column(SAEnum(CostingMethod), default=CostingMethod.FIFO, nullable=True)
specific_metal_purchase_id = Column(Integer, ForeignKey("metal_purchases.id"), nullable=True)

# Relationship
specific_metal_purchase = relationship("MetalPurchase")
```

#### 1.3 Pydantic Schema Changes
**File:** `src/goldsmith_erp/models/order.py`
```python
# Add to OrderCreate:
metal_type: Optional[MetalType] = None
costing_method: Optional[CostingMethod] = Field(default=CostingMethod.FIFO)
specific_metal_purchase_id: Optional[int] = None  # For SPECIFIC method

# Add to OrderUpdate:
metal_type: Optional[MetalType] = None
costing_method: Optional[CostingMethod] = None

# Add to OrderRead:
metal_type: Optional[MetalType] = None
costing_method_used: Optional[CostingMethod] = None
specific_metal_purchase_id: Optional[int] = None
```

#### 1.4 Service Changes
**File:** `src/goldsmith_erp/services/cost_calculation_service.py`

**OLD CODE (remove hardcoded price):**
```python
@staticmethod
async def _calculate_material_cost(
    order: OrderModel,
    material_price_per_gram: Optional[float] = None
) -> float:
    # Get price (use override or default)
    price_per_gram = material_price_per_gram or 45.00  # ❌ HARDCODED
```

**NEW CODE (use inventory):**
```python
@staticmethod
async def _calculate_material_cost(
    db: AsyncSession,
    order: OrderModel
) -> float:
    """
    Calculate material cost from real inventory.

    Uses MetalInventoryService to get actual cost based on:
    - Order's metal_type
    - Order's estimated_weight_g (with scrap percentage)
    - Order's costing_method (FIFO/LIFO/AVERAGE/SPECIFIC)
    """

    # If manual override exists, use it
    if order.material_cost_override:
        return order.material_cost_override

    # If no metal type specified, cannot calculate
    if not order.metal_type:
        logger.warning(f"Order {order.id} has no metal_type, cannot calculate material cost")
        return 0.0

    # If no estimated weight, cannot calculate
    if not order.estimated_weight_g:
        logger.warning(f"Order {order.id} has no estimated_weight_g, cannot calculate")
        return 0.0

    # Calculate effective weight with scrap percentage
    scrap_percent = order.scrap_percentage or 5.0
    effective_weight = order.estimated_weight_g * (1 + scrap_percent / 100.0)

    # Get allocation from MetalInventoryService
    try:
        allocation = await MetalInventoryService.allocate_material(
            db,
            metal_type=order.metal_type,
            required_weight_g=effective_weight,
            costing_method=order.costing_method_used or CostingMethod.FIFO,
            specific_purchase_id=order.specific_metal_purchase_id
        )

        # Return total cost from allocation
        return allocation.total_cost

    except ValueError as e:
        # Insufficient inventory or other allocation error
        logger.error(f"Failed to allocate material for order {order.id}: {e}")
        # Return 0 or raise error depending on desired behavior
        raise ValueError(f"Cannot calculate material cost: {e}")
```

**Update all method signatures that call _calculate_material_cost():**
```python
# OLD:
async def calculate_order_cost(
    db: AsyncSession,
    order_id: int,
    material_price_per_gram: Optional[float] = None  # ❌ Remove this
) -> PriceBreakdown:

# NEW:
async def calculate_order_cost(
    db: AsyncSession,
    order_id: int
) -> PriceBreakdown:
```

#### 1.5 API Changes
**File:** `src/goldsmith_erp/api/routers/orders.py`

**Update order creation to support metal type:**
```python
@router.post("/", response_model=OrderRead)
async def create_order(
    order: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.ORDER_CREATE))
):
    # Validate metal_type if provided
    if order.estimated_weight_g and not order.metal_type:
        raise HTTPException(
            status_code=400,
            detail="metal_type is required when estimated_weight_g is provided"
        )

    # If SPECIFIC costing method, validate metal_purchase_id
    if order.costing_method == CostingMethod.SPECIFIC and not order.specific_metal_purchase_id:
        raise HTTPException(
            status_code=400,
            detail="specific_metal_purchase_id required for SPECIFIC costing method"
        )
```

#### 1.6 Testing Strategy
- Unit tests for _calculate_material_cost() with mock inventory
- Integration tests with real MetalInventoryService
- Edge cases: insufficient inventory, no metal_type, multiple batches

---

## Task 2: Unit Tests - Add Test Coverage for Metal Inventory

### Current State
❌ **Problem:** 0% test coverage

### Target State
✅ **Goal:** 80%+ test coverage for critical paths

### Test Structure

```
tests/
├── conftest.py                              # Shared fixtures
├── unit/
│   ├── __init__.py
│   ├── test_metal_inventory_service.py      # Service unit tests
│   ├── test_cost_calculation_service.py     # Cost calculation tests
│   └── test_metal_inventory_validators.py   # Pydantic validation tests
└── integration/
    ├── __init__.py
    ├── test_metal_inventory_api.py          # API endpoint tests
    └── test_cost_calculation_integration.py # Full workflow tests
```

### Test Cases Required

#### 2.1 conftest.py - Shared Fixtures
```python
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from goldsmith_erp.db.models import Base, User, MetalPurchase, Order
from goldsmith_erp.db.models import MetalType, CostingMethod

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def db_session():
    """Create test database session"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()

@pytest.fixture
async def sample_user(db_session):
    """Create test user"""
    user = User(email="test@example.com", hashed_password="hashed", first_name="Test", last_name="User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def sample_metal_purchase(db_session):
    """Create test metal purchase"""
    purchase = MetalPurchase(
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=4500.00,
        price_per_gram=45.00,
        supplier="Test Supplier"
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase
```

#### 2.2 test_metal_inventory_service.py - Service Tests
```python
import pytest
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService
from goldsmith_erp.models.metal_inventory import MetalPurchaseCreate, MaterialUsageCreate
from goldsmith_erp.db.models import MetalType, CostingMethod

class TestMetalPurchaseCreation:
    async def test_create_purchase_success(self, db_session):
        """Test successful metal purchase creation"""
        purchase_data = MetalPurchaseCreate(
            metal_type=MetalType.GOLD_18K,
            weight_g=100.0,
            price_total=4500.00
        )

        purchase = await MetalInventoryService.create_purchase(db_session, purchase_data)

        assert purchase.id is not None
        assert purchase.metal_type == MetalType.GOLD_18K
        assert purchase.weight_g == 100.0
        assert purchase.remaining_weight_g == 100.0
        assert purchase.price_per_gram == 45.00  # Auto-calculated
        assert purchase.price_total == 4500.00

    async def test_create_purchase_calculates_price_per_gram(self, db_session):
        """Test automatic EUR/gram calculation"""
        purchase_data = MetalPurchaseCreate(
            metal_type=MetalType.SILVER_925,
            weight_g=500.0,
            price_total=250.00
        )

        purchase = await MetalInventoryService.create_purchase(db_session, purchase_data)

        assert purchase.price_per_gram == 0.50  # 250 / 500 = 0.50

    async def test_create_purchase_invalid_weight(self, db_session):
        """Test validation rejects invalid weight"""
        with pytest.raises(ValueError):
            MetalPurchaseCreate(
                metal_type=MetalType.GOLD_18K,
                weight_g=-10.0,  # Negative weight
                price_total=100.00
            )

class TestMaterialAllocation:
    async def test_allocate_fifo(self, db_session):
        """Test FIFO allocation uses oldest batches first"""
        # Create two purchases with different dates/prices
        # ... test FIFO logic

    async def test_allocate_lifo(self, db_session):
        """Test LIFO allocation uses newest batches first"""
        # ... test LIFO logic

    async def test_allocate_average(self, db_session):
        """Test weighted average cost calculation"""
        # ... test average logic

    async def test_allocate_specific(self, db_session, sample_metal_purchase):
        """Test specific batch selection"""
        # ... test specific logic

    async def test_allocate_insufficient_inventory(self, db_session, sample_metal_purchase):
        """Test error when insufficient inventory"""
        with pytest.raises(ValueError, match="Insufficient inventory"):
            await MetalInventoryService.allocate_material(
                db_session,
                metal_type=MetalType.GOLD_18K,
                required_weight_g=200.0,  # More than available (100g)
                costing_method=CostingMethod.FIFO
            )

class TestMaterialConsumption:
    async def test_consume_material_reduces_inventory(self, db_session, sample_metal_purchase, sample_order):
        """Test that consuming material reduces remaining_weight_g"""
        usage_data = MaterialUsageCreate(
            order_id=sample_order.id,
            weight_used_g=25.0,
            costing_method=CostingMethod.FIFO
        )

        usage = await MetalInventoryService.consume_material(
            db_session, usage_data, MetalType.GOLD_18K
        )

        # Refresh purchase to get updated remaining_weight_g
        await db_session.refresh(sample_metal_purchase)

        assert sample_metal_purchase.remaining_weight_g == 75.0  # 100 - 25
        assert usage.weight_used_g == 25.0
        assert usage.cost_at_time == 1125.00  # 25 * 45.00
```

#### 2.3 test_cost_calculation_service.py - Cost Calculation Tests
```python
class TestCostCalculationWithInventory:
    async def test_calculate_cost_with_real_inventory(self, db_session, sample_metal_purchase, sample_order):
        """Test cost calculation uses real inventory prices"""
        # Set order properties
        sample_order.metal_type = MetalType.GOLD_18K
        sample_order.estimated_weight_g = 25.0
        sample_order.scrap_percentage = 5.0

        breakdown = await CostCalculationService.calculate_order_cost(
            db_session, sample_order.id
        )

        # Effective weight = 25 * 1.05 = 26.25g
        # Cost = 26.25 * 45.00 = 1181.25 EUR
        assert breakdown.material_cost == pytest.approx(1181.25, 0.01)

    async def test_calculate_cost_insufficient_inventory(self, db_session, sample_order):
        """Test error when insufficient inventory for cost calculation"""
        sample_order.metal_type = MetalType.GOLD_18K
        sample_order.estimated_weight_g = 1000.0  # Way more than available

        with pytest.raises(ValueError, match="Cannot calculate material cost"):
            await CostCalculationService.calculate_order_cost(
                db_session, sample_order.id
            )
```

#### 2.4 test_metal_inventory_api.py - API Integration Tests
```python
from httpx import AsyncClient

class TestMetalInventoryAPI:
    async def test_create_purchase_endpoint(self, client: AsyncClient, auth_headers):
        """Test POST /metal-inventory/purchases"""
        response = await client.post(
            "/api/v1/metal-inventory/purchases",
            json={
                "metal_type": "gold_18k",
                "weight_g": 100.0,
                "price_total": 4500.00,
                "supplier": "Test Supplier"
            },
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["price_per_gram"] == 45.00

    async def test_consume_material_endpoint(self, client: AsyncClient, auth_headers, sample_purchase):
        """Test POST /metal-inventory/usage"""
        response = await client.post(
            "/api/v1/metal-inventory/usage?metal_type=gold_18k",
            json={
                "order_id": 1,
                "weight_used_g": 25.0,
                "costing_method": "fifo"
            },
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["cost_at_time"] == 1125.00
```

### Test Execution Plan
```bash
# 1. Install pytest and dependencies
poetry add --group dev pytest pytest-asyncio pytest-cov httpx

# 2. Run tests
poetry run pytest tests/ -v

# 3. Run with coverage
poetry run pytest tests/ --cov=src/goldsmith_erp --cov-report=html

# 4. View coverage report
open htmlcov/index.html
```

### Coverage Targets
- **MetalInventoryService:** 85%+
- **CostCalculationService:** 80%+
- **API Endpoints:** 75%+
- **Overall:** 80%+

---

## Task 3: Production Deployment Guide

### Document Structure

**File:** `PRODUCTION_DEPLOYMENT.md`

### Sections Required

#### 3.1 Prerequisites
- Server requirements (CPU, RAM, Disk)
- Operating System (Ubuntu 22.04 LTS recommended)
- Domain name with DNS configured
- SSL certificate (Let's Encrypt)
- SMTP server for emails (optional but recommended)

#### 3.2 Environment Setup
```bash
# System packages
sudo apt update
sudo apt install python3.11 python3.11-venv postgresql-14 redis-server nginx certbot

# Create application user
sudo useradd -m -s /bin/bash goldsmith
sudo usermod -aG sudo goldsmith

# Directory structure
/opt/goldsmith_erp/
├── app/              # Application code
├── venv/             # Python virtual environment
├── logs/             # Application logs
├── backups/          # Database backups
└── uploads/          # Uploaded files (future)
```

#### 3.3 Database Configuration
```bash
# PostgreSQL setup
sudo -u postgres createuser goldsmith
sudo -u postgres createdb goldsmith_erp -O goldsmith
sudo -u postgres psql -c "ALTER USER goldsmith WITH PASSWORD 'SECURE_PASSWORD';"

# Connection pooling with PgBouncer (optional but recommended)
sudo apt install pgbouncer

# /etc/pgbouncer/pgbouncer.ini
[databases]
goldsmith_erp = host=127.0.0.1 port=5432 dbname=goldsmith_erp

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = md5
pool_mode = transaction
max_client_conn = 100
default_pool_size = 20
```

#### 3.4 Environment Variables
**File:** `.env.production`
```bash
# Database
DATABASE_URL=postgresql+asyncpg://goldsmith:PASSWORD@localhost:6432/goldsmith_erp

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=GENERATE_WITH_openssl_rand_hex_32
DEBUG=false

# API
API_V1_STR=/api/v1
APP_NAME="Goldsmith ERP"

# CORS
BACKEND_CORS_ORIGINS=["https://yourdomain.com"]

# Email (optional)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=noreply@yourdomain.com
SMTP_PASSWORD=email_password
```

**Generate SECRET_KEY:**
```bash
openssl rand -hex 32
```

#### 3.5 SSL/TLS Setup with Let's Encrypt
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal (already configured by certbot)
sudo systemctl status certbot.timer
```

#### 3.6 Nginx Configuration
**File:** `/etc/nginx/sites-available/goldsmith_erp`
```nginx
upstream goldsmith_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL configuration (Mozilla Intermediate)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256...';
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Backend API
    location /api/ {
        proxy_pass http://goldsmith_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Frontend (Vite build)
    location / {
        root /opt/goldsmith_erp/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Static files
    location /static/ {
        alias /opt/goldsmith_erp/app/static/;
        expires 30d;
    }
}
```

#### 3.7 Systemd Service
**File:** `/etc/systemd/system/goldsmith-erp.service`
```ini
[Unit]
Description=Goldsmith ERP API
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=goldsmith
Group=goldsmith
WorkingDirectory=/opt/goldsmith_erp/app
Environment="PATH=/opt/goldsmith_erp/venv/bin"
EnvironmentFile=/opt/goldsmith_erp/.env.production
ExecStart=/opt/goldsmith_erp/venv/bin/uvicorn goldsmith_erp.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --log-config /opt/goldsmith_erp/logging.yaml

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable goldsmith-erp
sudo systemctl start goldsmith-erp
sudo systemctl status goldsmith-erp
```

#### 3.8 Security Hardening
```bash
# Firewall (UFW)
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable

# Fail2ban for SSH protection
sudo apt install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Disable root SSH login
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

#### 3.9 Backup Strategy
**Automated Database Backup Script:**
```bash
#!/bin/bash
# /opt/goldsmith_erp/scripts/backup.sh

BACKUP_DIR="/opt/goldsmith_erp/backups"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

# Database backup
pg_dump -U goldsmith goldsmith_erp | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Cleanup old backups
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +$RETENTION_DAYS -delete

# Upload to S3 (optional)
# aws s3 cp "$BACKUP_DIR/db_$DATE.sql.gz" s3://your-bucket/backups/
```

**Cron job:**
```bash
# Daily backup at 2 AM
0 2 * * * /opt/goldsmith_erp/scripts/backup.sh
```

#### 3.10 Monitoring & Logging
**Structured logging configuration:**
```yaml
# /opt/goldsmith_erp/logging.yaml
version: 1
formatters:
  json:
    (): goldsmith_erp.core.logging.CustomJsonFormatter
    format: "%(asctime)s %(levelname)s %(name)s %(message)s"

handlers:
  console:
    class: logging.StreamHandler
    formatter: json
    stream: ext://sys.stdout

  file:
    class: logging.handlers.RotatingFileHandler
    formatter: json
    filename: /opt/goldsmith_erp/logs/app.log
    maxBytes: 10485760  # 10MB
    backupCount: 10

root:
  level: INFO
  handlers: [console, file]
```

**Log rotation:**
```bash
# /etc/logrotate.d/goldsmith-erp
/opt/goldsmith_erp/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 goldsmith goldsmith
}
```

#### 3.11 Initial Deployment Steps
```bash
# 1. Clone repository
cd /opt/goldsmith_erp
git clone https://github.com/arcsmax/goldsmith_erp.git app
cd app

# 2. Create virtual environment
python3.11 -m venv ../venv
source ../venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
poetry install --only main

# 4. Run database migrations
alembic upgrade head

# 5. Create admin user
python scripts/create_admin.py

# 6. Build frontend
cd frontend
npm install
npm run build

# 7. Start services
sudo systemctl start goldsmith-erp
sudo systemctl start nginx
```

#### 3.12 Post-Deployment Verification
```bash
# Health checks
curl https://yourdomain.com/health
curl https://yourdomain.com/health/detailed

# API test
curl -X POST https://yourdomain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin_password"}'

# Database connection
psql -U goldsmith -d goldsmith_erp -c "SELECT COUNT(*) FROM users;"

# Logs
sudo journalctl -u goldsmith-erp -f
tail -f /opt/goldsmith_erp/logs/app.log
```

#### 3.13 Troubleshooting
Common issues and solutions...

---

## Implementation Order

### Phase 1: CostCalculationService Integration (2-3 hours)
1. Create migration for Order model changes
2. Update Order model with metal_type fields
3. Update Pydantic schemas
4. Modify CostCalculationService
5. Update API endpoints
6. Manual testing

### Phase 2: Unit Tests (4-6 hours)
1. Create test structure (conftest.py)
2. Write MetalInventoryService tests
3. Write CostCalculationService tests
4. Write API integration tests
5. Run coverage analysis
6. Fix gaps until 80%+ coverage

### Phase 3: Production Deployment Guide (2-3 hours)
1. Create PRODUCTION_DEPLOYMENT.md
2. Document all sections
3. Create helper scripts (backup.sh, create_admin.py)
4. Test guide with fresh VM
5. Update with corrections

**Total Estimated Time:** 8-12 hours

---

## Success Criteria

✅ **Task 1 Complete When:**
- CostCalculationService uses real inventory prices
- Orders can specify metal_type and costing_method
- No hardcoded prices remain
- All existing tests still pass

✅ **Task 2 Complete When:**
- Test coverage ≥ 80% for critical paths
- All tests pass (green)
- CI/CD pipeline configured (optional)
- Coverage report available

✅ **Task 3 Complete When:**
- PRODUCTION_DEPLOYMENT.md is comprehensive
- All commands tested and verified
- Security checklist complete
- Backup strategy documented
- Can deploy to fresh Ubuntu server following guide

---

## Next Steps After P0

**P1 Tasks (after P0 complete):**
1. Expand rate limiting to all POST endpoints
2. Add Prometheus metrics
3. Create frontend UI for metal inventory
4. Implement customer history & preferences
5. Add payment tracking

**P2 Tasks:**
6. Gemstone catalog management
7. Advanced reporting
8. Photo upload UI
9. Mobile-responsive design
10. API client library (Python/TypeScript)

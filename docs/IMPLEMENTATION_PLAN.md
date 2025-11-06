# Goldsmith ERP - Detailed Implementation Plan

**Document Version**: 1.0
**Date**: 2025-11-06
**Current Phase**: 1.5 Complete (Material Management UI)
**Next Phase**: 1.6 (GDPR Compliance + Customer Management)

---

## Executive Summary

This implementation plan prioritizes **GDPR compliance and security** before adding new features. The system cannot process real customer data until critical compliance features are implemented.

### Timeline Overview

| Phase | Duration | Focus | Status |
|-------|----------|-------|--------|
| **Phase 1.1-1.5** | 4 weeks | ✅ Backend Foundation + Material Management | **COMPLETE** |
| **Phase 1.6** | 3 weeks | 🔴 GDPR Compliance (CRITICAL) | **NEXT** |
| **Phase 1.7** | 2 weeks | 🟠 Customer Management Backend | Pending |
| **Phase 1.8** | 2 weeks | 🟠 Customer Management Frontend | Pending |
| **Phase 1.9** | 2 weeks | 🟡 Order Management Full Stack | Pending |
| **Phase 1.10** | 1 week | 🟢 Security Hardening | Pending |
| **Phase 2.0** | 3 weeks | Tag System (NFC/QR) | Future |

**Total to Production-Ready**: ~13 weeks from now

---

## Phase 1.6: GDPR Compliance & Security (CRITICAL)

**Duration**: 3 weeks (15 working days)
**Priority**: 🔴 **CRITICAL** - System cannot process real customer data without this
**Dependencies**: None (must be done before customer features)

### Week 1: Database Models & Audit Logging

#### Day 1-2: Customer Model with GDPR Fields

**Task 1.6.1**: Create GDPR-Compliant Customer Model

**File**: `src/goldsmith_erp/db/models.py`

**Implementation**:
```python
class Customer(Base):
    __tablename__ = "customers"

    # Identity
    id = Column(Integer, primary_key=True, index=True)
    customer_number = Column(String, unique=True, nullable=False, index=True)

    # Personal Data
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    phone = Column(String)

    # Address
    address_line1 = Column(String)
    address_line2 = Column(String)
    postal_code = Column(String)
    city = Column(String)
    country = Column(String, default="DE")

    # GDPR Compliance (CRITICAL)
    legal_basis = Column(String, nullable=False, default="contract")
    consent_marketing = Column(Boolean, default=False)
    consent_date = Column(DateTime)
    consent_version = Column(String)
    consent_ip_address = Column(String)

    # Data Retention
    data_retention_category = Column(String, default="active")
    last_order_date = Column(DateTime)
    retention_deadline = Column(DateTime)
    deletion_scheduled = Column(DateTime)

    # Privacy Preferences
    data_processing_consent = Column(Boolean, default=True)
    email_communication_consent = Column(Boolean, default=False)
    phone_communication_consent = Column(Boolean, default=False)

    # Audit Trail
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))

    # Soft Delete
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime)
    deleted_by = Column(Integer, ForeignKey("users.id"))
    deletion_reason = Column(Text)

    # Relationships
    orders = relationship("Order", back_populates="customer")
    audit_logs = relationship("CustomerAuditLog", back_populates="customer")
    gdpr_requests = relationship("GDPRRequest", back_populates="customer")
```

**Acceptance Criteria**:
- [ ] Customer model created with all GDPR fields
- [ ] customer_number auto-generation implemented
- [ ] Relationships to Order updated (customer_id now references customers, not users)
- [ ] Alembic migration created
- [ ] Seed script updated with sample customers

**Time Estimate**: 8 hours

---

**Task 1.6.2**: Create Audit Log Model

**File**: `src/goldsmith_erp/db/models.py`

**Implementation**:
```python
class CustomerAuditLog(Base):
    __tablename__ = "customer_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Action Details
    action = Column(String, nullable=False, index=True)
    entity = Column(String, nullable=False)
    entity_id = Column(Integer)

    # Changes
    field_name = Column(String)
    old_value = Column(Text)
    new_value = Column(Text)

    # Who & When
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_email = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Context
    ip_address = Column(String)
    user_agent = Column(String)
    endpoint = Column(String)
    request_id = Column(String, index=True)

    # Legal
    legal_basis = Column(String)

    # Relationships
    customer = relationship("Customer", back_populates="audit_logs")
    user = relationship("User")
```

**Acceptance Criteria**:
- [ ] Audit log model created
- [ ] Indexes on customer_id, timestamp, request_id
- [ ] Migration created

**Time Estimate**: 4 hours

---

**Task 1.6.3**: Create GDPR Request Tracking Model

**File**: `src/goldsmith_erp/db/models.py`

```python
class GDPRRequest(Base):
    __tablename__ = "gdpr_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    request_type = Column(String, nullable=False, index=True)
    status = Column(String, default="pending", nullable=False, index=True)

    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    due_date = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)

    request_details = Column(JSONB)
    response_details = Column(JSONB)
    rejection_reason = Column(Text)

    assigned_to = Column(Integer, ForeignKey("users.id"))
    verified = Column(Boolean, default=False)
    verification_method = Column(String)

    export_file_path = Column(String)
    certificate_file_path = Column(String)

    customer = relationship("Customer", back_populates="gdpr_requests")
    assigned_user = relationship("User")
```

**Acceptance Criteria**:
- [ ] GDPR request model created
- [ ] Due date auto-calculated (30 days from request)
- [ ] Migration created

**Time Estimate**: 4 hours

---

**Task 1.6.4**: Create Data Retention Policy Model

**File**: `src/goldsmith_erp/db/models.py`

```python
class DataRetentionPolicy(Base):
    __tablename__ = "data_retention_policies"

    id = Column(Integer, primary_key=True)
    category = Column(String, nullable=False, unique=True)
    retention_period_days = Column(Integer, nullable=False)
    legal_basis = Column(String, nullable=False)
    jurisdiction = Column(String, default="EU")
    action_after_expiry = Column(String)
    auto_apply = Column(Boolean, default=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Seed Data**:
```python
# Default policies for German/EU jurisdiction
policies = [
    {
        "category": "customer_active",
        "retention_period_days": 3650,  # 10 years
        "legal_basis": "contract + §147 AO (German tax law)",
        "action_after_expiry": "anonymize"
    },
    {
        "category": "financial_records",
        "retention_period_days": 3650,
        "legal_basis": "§147 AO (German tax law)",
        "action_after_expiry": "anonymize"
    },
    {
        "category": "marketing_consent",
        "retention_period_days": 730,  # 2 years
        "legal_basis": "consent",
        "action_after_expiry": "delete"
    }
]
```

**Acceptance Criteria**:
- [ ] Retention policy model created
- [ ] Default policies seeded
- [ ] Migration created

**Time Estimate**: 2 hours

---

#### Day 3-4: Audit Logging Middleware

**Task 1.6.5**: Implement Audit Logging Middleware

**File**: `src/goldsmith_erp/middleware/audit_logger.py` (NEW)

**Implementation**:
```python
from fastapi import Request, Response
from goldsmith_erp.db.models import CustomerAuditLog
from goldsmith_erp.api.deps import get_current_user
import json

AUDITED_ENDPOINTS = {
    "/api/v1/customers": "customer",
    "/api/v1/orders": "order",
}

@app.middleware("http")
async def audit_logging_middleware(request: Request, call_next):
    # Check if endpoint should be audited
    path = request.url.path

    if any(path.startswith(endpoint) for endpoint in AUDITED_ENDPOINTS):
        # Capture request
        body = await request.body()

        # Process request
        response = await call_next(request)

        # Log the action
        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            await log_audit_entry(
                request=request,
                response=response,
                body=body
            )

        return response

    return await call_next(request)

async def log_audit_entry(request, response, body):
    # Extract user from token
    user = await get_current_user_from_request(request)

    # Determine action
    action_map = {
        "POST": "created",
        "PUT": "updated",
        "PATCH": "updated",
        "DELETE": "deleted",
        "GET": "accessed"
    }

    # Extract entity info from path
    path_parts = request.url.path.split("/")
    entity = path_parts[3] if len(path_parts) > 3 else "unknown"
    entity_id = path_parts[4] if len(path_parts) > 4 else None

    # Parse changes (for PUT/PATCH)
    old_value = None
    new_value = None
    if body:
        try:
            data = json.loads(body)
            new_value = json.dumps(data)
        except:
            pass

    # Create audit log entry
    audit_log = CustomerAuditLog(
        customer_id=extract_customer_id_from_request(request),
        action=action_map.get(request.method, "unknown"),
        entity=entity,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        timestamp=datetime.utcnow(),
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        endpoint=request.url.path,
        request_id=request.state.request_id,
        legal_basis="contract"  # or determine from context
    )

    # Save to database
    async with get_db_session() as session:
        session.add(audit_log)
        await session.commit()
```

**Acceptance Criteria**:
- [ ] Middleware captures all customer/order operations
- [ ] Logs include user, timestamp, IP, changes
- [ ] Request correlation ID implemented
- [ ] Async logging doesn't block requests
- [ ] Unit tests for audit logging

**Time Estimate**: 10 hours

---

#### Day 5: Update Order Model

**Task 1.6.6**: Update Order Model to Use Customer Table

**File**: `src/goldsmith_erp/db/models.py`

**Changes**:
```python
class Order(Base):
    # Change from user_id to customer_id
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Update relationship
    customer = relationship("Customer", back_populates="orders")
```

**Migration**:
```python
# Alembic migration
def upgrade():
    # Create customers table
    op.create_table('customers', ...)

    # Migrate existing users to customers
    # (Only those with orders)
    op.execute("""
        INSERT INTO customers (id, first_name, last_name, email, ...)
        SELECT id, first_name, last_name, email, ...
        FROM users
        WHERE id IN (SELECT DISTINCT customer_id FROM orders)
    """)

    # Update orders.customer_id (already correct since IDs match)
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_orders_customer_id',
        'orders', 'customers',
        ['customer_id'], ['id']
    )
```

**Acceptance Criteria**:
- [ ] Order model updated
- [ ] Migration created and tested
- [ ] Existing test data migrates correctly
- [ ] Relationships work properly

**Time Estimate**: 6 hours

---

### Week 2: Repositories, Services & APIs

#### Day 6-7: Customer Repository & Service

**Task 1.6.7**: Create CustomerRepository

**File**: `src/goldsmith_erp/db/repositories/customer.py` (NEW)

**Implementation**:
```python
from goldsmith_erp.db.repositories.base import BaseRepository
from goldsmith_erp.db.models import Customer

class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, db: AsyncSession):
        super().__init__(db, Customer)

    async def get_by_email(self, email: str) -> Optional[Customer]:
        result = await self.db.execute(
            select(Customer).filter(
                Customer.email == email,
                Customer.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def get_by_customer_number(self, customer_number: str) -> Optional[Customer]:
        result = await self.db.execute(
            select(Customer).filter(
                Customer.customer_number == customer_number,
                Customer.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        query: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Customer]:
        stmt = select(Customer).filter(
            Customer.is_deleted == False,
            or_(
                Customer.first_name.ilike(f"%{query}%"),
                Customer.last_name.ilike(f"%{query}%"),
                Customer.email.ilike(f"%{query}%"),
                Customer.customer_number.ilike(f"%{query}%")
            )
        ).offset(skip).limit(limit)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_past_retention_deadline(self) -> List[Customer]:
        """Get customers past retention deadline for anonymization"""
        result = await self.db.execute(
            select(Customer).filter(
                Customer.retention_deadline <= datetime.utcnow(),
                Customer.is_deleted == False
            )
        )
        return result.scalars().all()

    async def soft_delete(
        self,
        customer_id: int,
        deleted_by_user_id: int,
        reason: str
    ) -> Customer:
        customer = await self.get_by_id(customer_id)
        if not customer:
            raise ValueError("Customer not found")

        customer.is_deleted = True
        customer.deleted_at = datetime.utcnow()
        customer.deleted_by = deleted_by_user_id
        customer.deletion_reason = reason

        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def anonymize(self, customer_id: int) -> Customer:
        """Anonymize customer data for GDPR compliance"""
        customer = await self.get_by_id(customer_id)
        if not customer:
            raise ValueError("Customer not found")

        # Anonymize personal data
        customer.first_name = "ANONYMIZED"
        customer.last_name = "ANONYMIZED"
        customer.email = f"anonymized_{customer.id}@deleted.local"
        customer.phone = None
        customer.address_line1 = None
        customer.address_line2 = None
        customer.postal_code = None
        customer.city = None
        customer.is_deleted = True
        customer.deleted_at = datetime.utcnow()
        customer.deletion_reason = "GDPR retention period expired"

        await self.db.commit()
        await self.db.refresh(customer)
        return customer
```

**Acceptance Criteria**:
- [ ] Repository implements all CRUD operations
- [ ] Search functionality works
- [ ] Soft delete implemented
- [ ] Anonymization implemented
- [ ] Unit tests written

**Time Estimate**: 10 hours

---

**Task 1.6.8**: Create CustomerService

**File**: `src/goldsmith_erp/services/customer_service.py` (NEW)

**Implementation**:
```python
from goldsmith_erp.db.repositories.customer import CustomerRepository
from goldsmith_erp.models.customer import CustomerCreate, CustomerUpdate

class CustomerService:
    def __init__(self, repository: CustomerRepository):
        self.repository = repository

    async def create_customer(
        self,
        data: CustomerCreate,
        created_by_user_id: int
    ) -> Customer:
        # Generate customer number
        customer_number = await self.generate_customer_number()

        # Calculate retention deadline
        retention_deadline = datetime.utcnow() + timedelta(days=3650)  # 10 years

        customer = Customer(
            customer_number=customer_number,
            **data.dict(),
            created_by=created_by_user_id,
            retention_deadline=retention_deadline
        )

        return await self.repository.create(customer)

    async def generate_customer_number(self) -> str:
        """Generate unique customer number: CUST-YYYYMM-XXXX"""
        prefix = f"CUST-{datetime.utcnow().strftime('%Y%m')}"

        # Find last customer number for this month
        last_customer = await self.repository.db.execute(
            select(Customer)
            .filter(Customer.customer_number.startswith(prefix))
            .order_by(Customer.customer_number.desc())
            .limit(1)
        )
        last = last_customer.scalar_one_or_none()

        if last:
            last_num = int(last.customer_number.split('-')[2])
            new_num = last_num + 1
        else:
            new_num = 1

        return f"{prefix}-{new_num:04d}"

    async def update_consents(
        self,
        customer_id: int,
        consents: dict,
        ip_address: str
    ) -> Customer:
        customer = await self.repository.get_by_id(customer_id)

        customer.consent_marketing = consents.get("marketing", False)
        customer.email_communication_consent = consents.get("email", False)
        customer.phone_communication_consent = consents.get("phone", False)
        customer.consent_date = datetime.utcnow()
        customer.consent_ip_address = ip_address

        await self.repository.db.commit()
        return customer

    async def export_customer_data(self, customer_id: int) -> dict:
        """Export all customer data for GDPR compliance"""
        customer = await self.repository.get_by_id(customer_id)
        orders = await self.get_customer_orders(customer_id)
        audit_logs = await self.get_audit_logs(customer_id)

        return {
            "personal_data": {
                "customer_number": customer.customer_number,
                "name": f"{customer.first_name} {customer.last_name}",
                "email": customer.email,
                "phone": customer.phone,
                "address": {
                    "line1": customer.address_line1,
                    "line2": customer.address_line2,
                    "postal_code": customer.postal_code,
                    "city": customer.city,
                    "country": customer.country
                }
            },
            "orders": [order.dict() for order in orders],
            "consents": {
                "marketing": customer.consent_marketing,
                "email": customer.email_communication_consent,
                "phone": customer.phone_communication_consent,
                "consent_date": customer.consent_date.isoformat() if customer.consent_date else None
            },
            "audit_log": [log.dict() for log in audit_logs],
            "metadata": {
                "exported_at": datetime.utcnow().isoformat(),
                "retention_deadline": customer.retention_deadline.isoformat() if customer.retention_deadline else None,
                "legal_basis": customer.legal_basis
            }
        }
```

**Acceptance Criteria**:
- [ ] Service implements business logic
- [ ] Customer number generation works
- [ ] Consent management implemented
- [ ] Data export functionality complete
- [ ] Unit tests written

**Time Estimate**: 10 hours

---

#### Day 8-9: Customer CRUD APIs

**Task 1.6.9**: Create Customer API Router

**File**: `src/goldsmith_erp/api/routers/customers.py` (NEW)

**Endpoints**:
```python
from fastapi import APIRouter, Depends, Query
from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.models.customer import CustomerCreate, CustomerUpdate, CustomerResponse

router = APIRouter()

@router.get("/", response_model=List[CustomerResponse])
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List customers with pagination and search"""
    pass

@router.post("/", response_model=CustomerResponse, status_code=201)
async def create_customer(
    customer: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new customer"""
    pass

@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get customer by ID"""
    pass

@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    customer: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update customer"""
    pass

@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Soft delete customer"""
    pass
```

**Acceptance Criteria**:
- [ ] All CRUD endpoints implemented
- [ ] Proper error handling
- [ ] Input validation
- [ ] Authorization checks
- [ ] API tests written

**Time Estimate**: 8 hours

---

#### Day 10: GDPR-Specific APIs

**Task 1.6.10**: Implement GDPR Data Subject Rights APIs

**File**: `src/goldsmith_erp/api/routers/customers.py`

**Endpoints**:
```python
@router.get("/{customer_id}/data-export")
async def export_customer_data(
    customer_id: int,
    format: str = Query("json", regex="^(json|csv|xml)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Right to Access - Export all customer data"""
    service = CustomerService(CustomerRepository(db))
    data = await service.export_customer_data(customer_id)

    if format == "json":
        return JSONResponse(content=data)
    elif format == "csv":
        return generate_csv_response(data)
    elif format == "xml":
        return generate_xml_response(data)

@router.post("/{customer_id}/gdpr-erasure")
async def request_gdpr_erasure(
    customer_id: int,
    reason: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Right to Erasure - Delete customer data"""
    service = CustomerService(CustomerRepository(db))

    # Check if customer can be deleted (no retention requirements)
    can_delete = await service.check_if_deletable(customer_id)

    if not can_delete:
        # Schedule for future deletion
        deletion_date = await service.schedule_deletion(customer_id)
        return {
            "status": "scheduled",
            "message": "Customer has active retention requirements",
            "deletion_date": deletion_date.isoformat()
        }
    else:
        # Delete immediately
        await service.soft_delete(customer_id, current_user.id, reason)
        return {
            "status": "completed",
            "message": "Customer data deleted successfully"
        }

@router.patch("/{customer_id}/consents")
async def update_consents(
    customer_id: int,
    consents: dict,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update customer consent preferences"""
    service = CustomerService(CustomerRepository(db))
    ip_address = request.client.host

    customer = await service.update_consents(customer_id, consents, ip_address)
    return customer

@router.get("/{customer_id}/consent-history")
async def get_consent_history(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get consent change history"""
    # Query audit logs for consent changes
    pass

@router.get("/{customer_id}/audit-log")
async def get_audit_log(
    customer_id: int,
    skip: int = 0,
    limit: int = 100,
    action: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get customer audit log"""
    # Requires admin role
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Query audit logs
    pass
```

**Acceptance Criteria**:
- [ ] Data export in JSON/CSV/XML
- [ ] Erasure endpoint with retention checks
- [ ] Consent management endpoints
- [ ] Audit log access (admin only)
- [ ] API tests for GDPR endpoints

**Time Estimate**: 12 hours

---

### Week 3: Security, Testing & Documentation

#### Day 11-12: Security Enhancements

**Task 1.6.11**: Implement Data Encryption

**File**: `src/goldsmith_erp/core/encryption.py` (NEW)

**Implementation**:
```python
from cryptography.fernet import Fernet
from goldsmith_erp.core.config import settings

# Generate encryption key (store in environment variable)
# ENCRYPTION_KEY = Fernet.generate_key()

def get_fernet():
    return Fernet(settings.ENCRYPTION_KEY.encode())

def encrypt_field(value: str) -> str:
    if not value:
        return None
    fernet = get_fernet()
    return fernet.encrypt(value.encode()).decode()

def decrypt_field(encrypted_value: str) -> str:
    if not encrypted_value:
        return None
    fernet = get_fernet()
    return fernet.decrypt(encrypted_value.encode()).decode()
```

**Apply to Customer Model**:
```python
class Customer(Base):
    _phone_encrypted = Column(String, name="phone")
    _address_line1_encrypted = Column(String, name="address_line1")

    @hybrid_property
    def phone(self):
        if self._phone_encrypted:
            return decrypt_field(self._phone_encrypted)
        return None

    @phone.setter
    def phone(self, value):
        if value:
            self._phone_encrypted = encrypt_field(value)
        else:
            self._phone_encrypted = None
```

**Acceptance Criteria**:
- [ ] Encryption module implemented
- [ ] Sensitive fields encrypted (phone, address)
- [ ] Decryption works transparently
- [ ] Encryption key in environment variable
- [ ] Tests for encryption/decryption

**Time Estimate**: 10 hours

---

**Task 1.6.12**: Implement Rate Limiting

**File**: `src/goldsmith_erp/middleware/rate_limit.py` (NEW)

**Implementation**:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# Apply to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to sensitive endpoints
@router.post("/api/v1/customers/")
@limiter.limit("20/minute")
async def create_customer(...):
    pass

@router.post("/api/v1/auth/login")
@limiter.limit("5/minute")
async def login(...):
    pass
```

**Acceptance Criteria**:
- [ ] Rate limiter configured
- [ ] Applied to authentication endpoints (5/min)
- [ ] Applied to customer endpoints (20/min)
- [ ] Redis backend for distributed rate limiting
- [ ] Tests for rate limiting

**Time Estimate**: 6 hours

---

**Task 1.6.13**: Add Security Headers

**File**: `src/goldsmith_erp/main.py`

**Implementation**:
```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response

# HTTPS redirect (production only)
if not settings.DEBUG:
    app.add_middleware(HTTPSRedirectMiddleware)
```

**Acceptance Criteria**:
- [ ] All security headers added
- [ ] HTTPS redirect in production
- [ ] CSP policy configured
- [ ] Headers tested

**Time Estimate**: 3 hours

---

#### Day 13-14: Testing

**Task 1.6.14**: Write Comprehensive Tests

**Files**:
- `tests/test_customers.py`
- `tests/test_gdpr.py`
- `tests/test_audit_logging.py`

**Test Coverage**:
```python
# Customer CRUD tests
def test_create_customer():
def test_get_customer():
def test_update_customer():
def test_delete_customer():
def test_search_customers():

# GDPR tests
def test_data_export_json():
def test_data_export_csv():
def test_gdpr_erasure_immediate():
def test_gdpr_erasure_scheduled():
def test_consent_management():
def test_retention_deadline_calculation():

# Audit logging tests
def test_audit_log_created_on_customer_create():
def test_audit_log_created_on_customer_update():
def test_audit_log_includes_user_info():
def test_audit_log_includes_ip_address():

# Security tests
def test_encryption_decryption():
def test_rate_limiting():
def test_security_headers():
```

**Acceptance Criteria**:
- [ ] 80%+ code coverage
- [ ] All critical paths tested
- [ ] Integration tests for GDPR workflows
- [ ] Tests pass in CI/CD

**Time Estimate**: 16 hours

---

#### Day 15: Documentation

**Task 1.6.15**: Complete GDPR Documentation

**Files to Create/Update**:
1. `docs/PRIVACY_POLICY.md` - Legal privacy policy
2. `docs/DATA_PROCESSING_AGREEMENT.md` - For processors/controllers
3. `docs/GDPR_PROCEDURES.md` - Staff procedures
4. `docs/DATA_BREACH_RESPONSE.md` - Incident response plan

**Acceptance Criteria**:
- [ ] Privacy policy written (consult lawyer)
- [ ] Data processing agreement drafted
- [ ] Staff procedures documented
- [ ] Breach response plan created

**Time Estimate**: 8 hours

---

## Phase 1.7: Customer Management Frontend (2 weeks)

**Duration**: 2 weeks (10 working days)
**Priority**: 🟠 **HIGH**
**Dependencies**: Phase 1.6 complete

### Week 4: Customer UI

**Task 1.7.1**: Create Customer List Page

**File**: `frontend/src/pages/customers/CustomerList.tsx`

**Features**:
- Table with customer data (number, name, email, phone, orders count)
- Search by name, email, customer number
- Pagination (20 per page)
- Quick actions (View, Edit, Delete)
- Filters (active/inactive, has orders)
- Visual indicators (recent customers, high-value customers)

**Time Estimate**: 10 hours

---

**Task 1.7.2**: Create Customer Form

**File**: `frontend/src/pages/customers/CustomerForm.tsx`

**Features**:
- Create/Edit modes
- Fields: Name, Email, Phone, Address
- Consent checkboxes (marketing, email, phone)
- Privacy policy acceptance
- Form validation
- Address autocomplete (optional)

**Time Estimate**: 10 hours

---

**Task 1.7.3**: Create Customer Detail Page

**File**: `frontend/src/pages/customers/CustomerDetail.tsx`

**Features**:
- Customer information display
- Order history for customer
- Consent status display
- Edit/Delete actions
- GDPR actions section (Export data, Request deletion)

**Time Estimate**: 10 hours

---

**Task 1.7.4**: Implement GDPR Self-Service

**File**: `frontend/src/pages/customers/CustomerGDPR.tsx`

**Features**:
- Export data button (JSON/CSV/XML)
- Request deletion button
- Consent management checkboxes
- Consent history display
- Privacy policy viewer

**Time Estimate**: 8 hours

---

**Task 1.7.5**: Consent Management UI

**File**: `frontend/src/components/ConsentManager.tsx`

**Features**:
- Checkbox group for consents
- Consent timestamp display
- Update consent API integration
- Audit trail display (who changed, when)

**Time Estimate**: 6 hours

---

### Week 5: Integration & Polish

**Task 1.7.6**: Update Order Pages to Use Customers

**Files**:
- `frontend/src/pages/orders/OrderForm.tsx`
- `frontend/src/pages/orders/OrderDetail.tsx`

**Changes**:
- Add customer selector dropdown in order form
- Link to customer detail from order
- Display customer info in order detail

**Time Estimate**: 8 hours

---

**Task 1.7.7**: Add Customer Analytics Dashboard

**File**: `frontend/src/pages/Dashboard.tsx`

**Additions**:
- New customers this month
- Total customers
- Customers with pending orders
- High-value customers

**Time Estimate**: 6 hours

---

**Task 1.7.8**: Frontend Testing

**Files**:
- `frontend/src/pages/customers/__tests__/CustomerList.test.tsx`
- `frontend/src/pages/customers/__tests__/CustomerForm.test.tsx`

**Tests**:
- Component rendering
- Form validation
- API integration
- User interactions

**Time Estimate**: 10 hours

---

## Phase 1.8: Order Management Full Stack (2 weeks)

**Duration**: 2 weeks (10 working days)
**Priority**: 🟡 **MEDIUM**
**Dependencies**: Phase 1.7 complete

### Week 6: Order Backend Enhancements

**Task 1.8.1**: Enhance Order Model

**File**: `src/goldsmith_erp/db/models.py`

**Additions**:
```python
class Order(Base):
    # Add workflow states
    workflow_state = Column(String, default="draft")
    # draft → confirmed → in_progress → quality_check → completed → delivered

    # Add pricing
    subtotal = Column(Float)
    tax_amount = Column(Float)
    total_amount = Column(Float)

    # Add tracking
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    delivered_at = Column(DateTime)

    # Add assigned goldsmith
    assigned_to = Column(Integer, ForeignKey("users.id"))
    assigned_user = relationship("User", foreign_keys=[assigned_to])
```

**Time Estimate**: 4 hours

---

**Task 1.8.2**: Implement Order Service Logic

**File**: `src/goldsmith_erp/services/order_service.py`

**Features**:
- Price calculation (materials + labor)
- Workflow state transitions
- Material stock validation
- Stock deduction on order completion
- Notifications (WebSocket updates)

**Time Estimate**: 12 hours

---

**Task 1.8.3**: Enhance Order API

**File**: `src/goldsmith_erp/api/routers/orders.py`

**New Endpoints**:
- `POST /orders/{id}/workflow/advance` - Move to next state
- `POST /orders/{id}/assign` - Assign to goldsmith
- `GET /orders/my-orders` - Orders for logged-in goldsmith
- `GET /orders/statistics` - Order analytics

**Time Estimate**: 8 hours

---

### Week 7: Order Frontend

**Task 1.8.4**: Create Order List Page

**File**: `frontend/src/pages/orders/OrderList.tsx`

**Features**:
- Table with orders (number, customer, status, total, due date)
- Filters (status, assigned goldsmith, date range)
- Search by order number, customer
- Visual status indicators
- Quick actions

**Time Estimate**: 10 hours

---

**Task 1.8.5**: Create Order Form

**File**: `frontend/src/pages/orders/OrderForm.tsx`

**Features**:
- Customer selection dropdown
- Service selection (repair types, custom work)
- Material selection with stock check
- Price calculation preview
- Due date picker
- Notes/description field

**Time Estimate**: 12 hours

---

**Task 1.8.6**: Create Order Detail Page

**File**: `frontend/src/pages/orders/OrderDetail.tsx`

**Features**:
- Complete order information
- Customer details (linked)
- Materials used (linked)
- Workflow status timeline
- Actions (Advance workflow, Edit, Cancel)
- Real-time updates via WebSocket

**Time Estimate**: 10 hours

---

**Task 1.8.7**: Order Workflow UI

**File**: `frontend/src/components/OrderWorkflow.tsx`

**Features**:
- Visual workflow stepper
- State transition buttons
- Conditional actions based on state
- Confirmation dialogs

**Time Estimate**: 8 hours

---

## Phase 1.9: Security Hardening (1 week)

**Duration**: 1 week (5 working days)
**Priority**: 🟡 **MEDIUM**
**Dependencies**: Phases 1.6-1.8 complete

**Task 1.9.1**: Implement RBAC (Role-Based Access Control)

**File**: `src/goldsmith_erp/core/permissions.py`

**Implementation**:
```python
class Permission(Enum):
    CUSTOMERS_CREATE = "customers.create"
    CUSTOMERS_READ = "customers.read"
    CUSTOMERS_UPDATE = "customers.update"
    CUSTOMERS_DELETE = "customers.delete"
    CUSTOMERS_EXPORT = "customers.export"
    GDPR_ERASURE = "gdpr.erasure"
    # ... more permissions

ROLE_PERMISSIONS = {
    "admin": [*Permission],  # All permissions
    "manager": [
        Permission.CUSTOMERS_CREATE,
        Permission.CUSTOMERS_READ,
        Permission.CUSTOMERS_UPDATE,
        Permission.CUSTOMERS_EXPORT,
        # ...
    ],
    "goldsmith": [
        Permission.CUSTOMERS_READ,
        Permission.ORDERS_CREATE,
        Permission.ORDERS_UPDATE,
        # ...
    ],
}

def check_permission(user: User, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, [])
```

**Time Estimate**: 8 hours

---

**Task 1.9.2**: Add Token Refresh & Session Management

**File**: `src/goldsmith_erp/api/routers/auth.py`

**Implementation**:
- Create UserSession model
- Implement refresh token rotation
- Add logout endpoint (revoke tokens)
- Session expiry (15 minutes for access token, 7 days for refresh token)

**Time Estimate**: 10 hours

---

**Task 1.9.3**: Implement Password Policy

**File**: `src/goldsmith_erp/core/security.py`

**Features**:
- Minimum length (12 characters)
- Complexity requirements (uppercase, lowercase, number, symbol)
- Password history (prevent reuse of last 5)
- Password expiry (90 days)

**Time Estimate**: 6 hours

---

**Task 1.9.4**: Add Failed Login Tracking & Account Lockout

**File**: `src/goldsmith_erp/api/routers/auth.py`

**Implementation**:
- Track failed login attempts (Redis)
- Lockout after 5 failed attempts (30 minutes)
- Admin unlock capability

**Time Estimate**: 6 hours

---

**Task 1.9.5**: Security Audit & Penetration Testing

**Activities**:
- OWASP Top 10 vulnerability check
- SQL injection testing
- XSS testing
- CSRF testing
- Authentication bypass testing
- Authorization testing

**Time Estimate**: 10 hours

---

## Phase 2.0: Tag System (NFC/QR) - Future

**Duration**: 3 weeks
**Priority**: 🟢 **LOW** (Future)

**Overview**:
- Tag model (NFC ID + QR code)
- Tag generation API
- Tag linking to entities (orders, materials, tools)
- Mobile app for NFC scanning
- QR code scanning in web app

---

## Priority Summary

### 🔴 CRITICAL - Must Do Before Production

1. ✅ Phase 1.6: GDPR Compliance (3 weeks)
   - Customer model with GDPR fields
   - Audit logging
   - Data subject rights APIs
   - Encryption
   - Security headers

### 🟠 HIGH - Core Functionality

2. ⚠️ Phase 1.7: Customer Management Frontend (2 weeks)
   - Customer CRUD UI
   - GDPR self-service portal
   - Consent management UI

3. ⚠️ Phase 1.8: Order Management Full Stack (2 weeks)
   - Order workflow
   - Order UI
   - Customer-Order integration

### 🟡 MEDIUM - Important but Not Blocking

4. ⚠️ Phase 1.9: Security Hardening (1 week)
   - RBAC
   - Token refresh
   - Password policy
   - Failed login tracking

### 🟢 LOW - Future Enhancements

5. ⚠️ Phase 2.0: Tag System (3 weeks)
   - NFC/QR integration
   - Mobile app

---

## Resource Requirements

### Development Team

**Minimum Team**:
- 1 Full-Stack Developer (Backend + Frontend)
- 1 Data Protection Consultant (Part-time, for GDPR)
- 1 QA Tester (Part-time)

**Ideal Team**:
- 1 Backend Developer
- 1 Frontend Developer
- 1 Security Engineer (Part-time)
- 1 Data Protection Officer (Part-time)
- 1 QA Tester

### External Resources

- **Data Protection Lawyer**: Review privacy policy, DPA (€1,000-2,000)
- **Security Audit**: Professional penetration testing (€2,000-5,000)
- **SSL Certificate**: For production deployment (€0-200/year)

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GDPR non-compliance fines | High | Critical | Implement Phase 1.6 immediately |
| Data breach | Medium | High | Encryption, audit logging, security hardening |
| Scope creep | Medium | Medium | Strict phase gates, clear acceptance criteria |
| Key developer unavailable | Medium | High | Documentation, code reviews, knowledge sharing |
| Performance issues at scale | Low | Medium | Load testing, database optimization |

---

## Success Criteria

### Phase 1.6 (GDPR Compliance) Success

- [ ] All customer data has legal basis documented
- [ ] Data subject rights APIs (access, erasure, portability) functional
- [ ] Audit logging captures all data access
- [ ] Sensitive fields encrypted
- [ ] GDPR request tracking system operational
- [ ] Privacy policy published
- [ ] Staff trained on GDPR procedures
- [ ] Can demonstrate compliance to auditor

### Phase 1.7 (Customer Management) Success

- [ ] Customer CRUD operations functional in UI
- [ ] Customer search and filtering works
- [ ] GDPR self-service portal accessible
- [ ] Consent management UI operational
- [ ] Customer data export works (JSON/CSV/XML)

### Phase 1.8 (Order Management) Success

- [ ] Orders linked to customers
- [ ] Order workflow functional
- [ ] Material stock integrated with orders
- [ ] Real-time order updates via WebSocket
- [ ] Order analytics dashboard complete

### Overall MVP Success

- [ ] System can process real customer data compliantly
- [ ] All CRUD operations work end-to-end
- [ ] Authentication and authorization secure
- [ ] No critical security vulnerabilities
- [ ] 80%+ test coverage
- [ ] Production deployment successful

---

## Next Steps (Immediate Actions)

### This Week

1. **Start Phase 1.6**: Begin with Customer model (Task 1.6.1)
2. **Legal Consultation**: Contact data protection lawyer for privacy policy review
3. **Team Briefing**: Present this plan to stakeholders
4. **Environment Setup**: Add encryption keys to .env

### This Month

5. **Complete Phase 1.6**: GDPR compliance implementation
6. **Start Phase 1.7**: Customer Management frontend
7. **Security Audit**: Schedule professional security review

---

## Appendices

### A. Definition of Done

A task is "done" when:
- [ ] Code implemented and working
- [ ] Unit tests written (80%+ coverage)
- [ ] Integration tests pass
- [ ] Code reviewed by peer
- [ ] Documentation updated
- [ ] Committed to git with descriptive message
- [ ] Acceptance criteria met

### B. Git Workflow

**Branch Strategy**:
- `main` - Production-ready code
- `develop` - Integration branch
- `claude/feature-*` - Feature branches
- `claude/fix-*` - Bug fixes

**Commit Message Format**:
```
type(scope): subject

body

BREAKING CHANGE: description (if applicable)
```

**Types**: feat, fix, docs, style, refactor, test, chore

### C. Code Review Checklist

Security:
- [ ] No hardcoded secrets
- [ ] Input validation on all endpoints
- [ ] Authorization checks present
- [ ] SQL injection protected
- [ ] XSS protection in place

GDPR:
- [ ] Audit logging for data access
- [ ] Legal basis documented
- [ ] Consent captured where required
- [ ] Data retention considered

Quality:
- [ ] Code follows style guide
- [ ] Tests written and passing
- [ ] Error handling present
- [ ] Documentation updated

---

**Document Status**: ✅ Complete
**Next Review**: After Phase 1.6 completion
**Maintained By**: Development Team Lead

# GDPR Compliance Guide for Goldsmith ERP

**Document Version**: 1.0
**Date**: 2025-11-06
**Regulatory Framework**: EU General Data Protection Regulation (GDPR)
**Applies to**: All customer data processing in Goldsmith ERP

---

## Executive Summary

This document outlines the **mandatory GDPR compliance requirements** for Goldsmith ERP when handling customer personal data. The system currently has **critical gaps** that must be addressed before processing real customer information.

⚠️ **WARNING**: The system is currently **NOT GDPR compliant**. Processing real customer data without these implementations could result in fines up to **€20 million or 4% of annual global turnover**.

---

## 1. GDPR Principles & Requirements

### 1.1 Core Principles (Article 5 GDPR)

| Principle | Description | Current Status | Priority |
|-----------|-------------|----------------|----------|
| **Lawfulness, Fairness, Transparency** | Legal basis for processing, clear communication | ❌ Not implemented | 🔴 CRITICAL |
| **Purpose Limitation** | Data used only for stated purposes | ⚠️ Partial | 🟠 HIGH |
| **Data Minimization** | Collect only necessary data | ⚠️ Partial | 🟠 HIGH |
| **Accuracy** | Keep data accurate and up to date | ✅ Basic update capability | 🟡 MEDIUM |
| **Storage Limitation** | Delete when no longer needed | ❌ Not implemented | 🔴 CRITICAL |
| **Integrity & Confidentiality** | Secure data properly | ⚠️ Partial (passwords only) | 🔴 CRITICAL |
| **Accountability** | Demonstrate compliance | ❌ Not implemented | 🔴 CRITICAL |

### 1.2 Legal Basis for Processing (Article 6 GDPR)

For Goldsmith ERP, applicable legal bases:

1. **Contract (Article 6(1)(b))** - PRIMARY
   - Processing necessary to perform jewelry repair/custom order contracts
   - **Covers**: Name, contact info, order details, delivery address

2. **Consent (Article 6(1)(a))** - SECONDARY
   - Explicit consent for marketing communications
   - Optional data collection beyond contract requirements
   - **Must be**: Freely given, specific, informed, unambiguous

3. **Legal Obligation (Article 6(1)(c))** - ACCOUNTING
   - Tax and accounting record retention (typically 10 years)
   - **Covers**: Invoices, payment records

**Implementation Required**:
```python
class Customer(Base):
    # Legal basis tracking
    legal_basis_contract: Boolean = True  # Contract-based processing
    consent_marketing: Boolean = False  # Marketing consent
    consent_date: DateTime = None  # When consent given
    consent_version: String = None  # Version of terms accepted
```

---

## 2. Data Subject Rights (Chapter III GDPR)

### 2.1 Right to Access (Article 15)

**Requirement**: Customers can request all their data.

**Implementation Needed**:
```python
# API Endpoint
GET /api/v1/customers/{id}/data-export

Response:
{
  "personal_data": {
    "customer_info": {...},
    "orders": [...],
    "consents": {...},
    "audit_log": [...]
  },
  "metadata": {
    "exported_at": "2025-11-06T10:00:00Z",
    "retention_period": "10 years from last order",
    "legal_basis": "contract"
  }
}
```

**Timeline**: Must respond within **1 month** (extendable to 3 months if complex)

### 2.2 Right to Rectification (Article 16)

**Requirement**: Customers can correct inaccurate data.

**Current Status**: ⚠️ Basic update API exists, needs GDPR enhancements
- ✅ Update endpoint exists
- ❌ No audit trail of corrections
- ❌ No customer self-service portal

### 2.3 Right to Erasure / "Right to be Forgotten" (Article 17)

**Requirement**: Delete customer data when no longer needed.

**Exceptions** (when you CAN'T delete):
- Legal obligation to retain (tax records: 10 years)
- Contract still active
- Legal claims pending

**Implementation Needed**:
```python
# API Endpoint
DELETE /api/v1/customers/{id}/gdpr-erasure

Logic:
1. Check if legal retention applies (active orders, tax retention period)
2. If deletable:
   - Anonymize personal data (keep order statistics)
   - Delete contact info, addresses
   - Keep financial records (anonymized) for legal retention
3. Log erasure request and action taken
4. Generate deletion certificate
```

**Timeline**: Must comply within **1 month**

### 2.4 Right to Data Portability (Article 20)

**Requirement**: Export data in machine-readable format (JSON, CSV, XML).

**Implementation Needed**:
```python
# API Endpoint
GET /api/v1/customers/{id}/data-export?format=json

Formats supported:
- JSON (structured)
- CSV (tabular)
- XML (structured)
```

### 2.5 Right to Object (Article 21)

**Requirement**: Customer can object to processing for marketing.

**Implementation**:
- ✅ Easy opt-out from marketing
- ❌ Not yet implemented

### 2.6 Rights Related to Automated Decision-Making (Article 22)

**Current Status**: ✅ Not applicable (no automated decisions currently)

---

## 3. Required Database Changes

### 3.1 Customer Model (NEW - CRITICAL)

**Current Issue**: No separate Customer model exists. Users and Customers are conflated.

**Required Model**:
```python
class Customer(Base):
    __tablename__ = "customers"

    # Identity
    id = Column(Integer, primary_key=True, index=True)
    customer_number = Column(String, unique=True, nullable=False, index=True)

    # Personal Data (Article 4(1))
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

    # GDPR Compliance Fields (CRITICAL)
    legal_basis = Column(String, nullable=False)  # contract, consent, legal_obligation
    consent_marketing = Column(Boolean, default=False)
    consent_date = Column(DateTime)
    consent_version = Column(String)  # Version of privacy policy accepted
    consent_ip_address = Column(String)  # IP when consent given

    # Data Retention
    data_retention_category = Column(String, default="active")  # active, inactive, archived
    last_order_date = Column(DateTime)
    retention_deadline = Column(DateTime)  # When data can be deleted
    deletion_scheduled = Column(DateTime)  # Scheduled deletion date

    # Privacy Preferences
    data_processing_consent = Column(Boolean, default=True)
    email_communication_consent = Column(Boolean, default=False)
    phone_communication_consent = Column(Boolean, default=False)

    # Audit Trail
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))  # Staff member who created
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))

    # Soft Delete (for GDPR right to erasure)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)
    deleted_by = Column(Integer, ForeignKey("users.id"))
    deletion_reason = Column(Text)  # GDPR erasure, customer request, retention expired

    # Relationships
    orders = relationship("Order", back_populates="customer")
    audit_logs = relationship("CustomerAuditLog", back_populates="customer")
    gdpr_requests = relationship("GDPRRequest", back_populates="customer")
```

### 3.2 Audit Log Model (NEW - CRITICAL)

**Requirement**: Track all access and changes to customer data (Article 30 GDPR).

```python
class CustomerAuditLog(Base):
    __tablename__ = "customer_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Action Details
    action = Column(String, nullable=False, index=True)  # created, updated, accessed, deleted, exported
    entity = Column(String, nullable=False)  # customer, order, consent
    entity_id = Column(Integer)

    # Changes
    field_name = Column(String)  # Which field changed
    old_value = Column(Text)  # Previous value
    new_value = Column(Text)  # New value

    # Who & When
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_email = Column(String)  # Denormalized for audit permanence
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Context
    ip_address = Column(String)
    user_agent = Column(String)
    endpoint = Column(String)  # API endpoint used
    request_id = Column(String)  # Correlation ID

    # Legal
    legal_basis = Column(String)  # Why this action was allowed

    # Relationships
    customer = relationship("Customer", back_populates="audit_logs")
    user = relationship("User")
```

**Retention**: Audit logs must be kept for **minimum 3 years** (longer for tax-related)

### 3.3 GDPR Request Tracking (NEW - CRITICAL)

```python
class GDPRRequest(Base):
    __tablename__ = "gdpr_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Request Type
    request_type = Column(String, nullable=False, index=True)
    # Types: access, rectification, erasure, portability, objection, restrict

    # Status
    status = Column(String, default="pending", nullable=False, index=True)
    # pending, in_progress, completed, rejected

    # Timeline
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    due_date = Column(DateTime, nullable=False)  # 1 month from request
    completed_at = Column(DateTime)

    # Details
    request_details = Column(JSONB)  # Specific request information
    response_details = Column(JSONB)  # Response/action taken
    rejection_reason = Column(Text)  # If rejected, why

    # Processing
    assigned_to = Column(Integer, ForeignKey("users.id"))
    verified = Column(Boolean, default=False)  # Identity verification
    verification_method = Column(String)  # email, in_person, phone

    # Files
    export_file_path = Column(String)  # For data portability
    certificate_file_path = Column(String)  # Deletion certificate

    # Relationships
    customer = relationship("Customer", back_populates="gdpr_requests")
    assigned_user = relationship("User")
```

### 3.4 Data Retention Policy Table (NEW)

```python
class DataRetentionPolicy(Base):
    __tablename__ = "data_retention_policies"

    id = Column(Integer, primary_key=True)

    # Policy
    category = Column(String, nullable=False, unique=True)  # customer_active, customer_inactive, financial_records
    retention_period_days = Column(Integer, nullable=False)

    # Legal Basis
    legal_basis = Column(String, nullable=False)  # GDPR, tax_law, contract_law
    jurisdiction = Column(String, default="EU")

    # Actions
    action_after_expiry = Column(String)  # delete, anonymize, archive
    auto_apply = Column(Boolean, default=False)

    # Metadata
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Default Policies**:
```python
policies = [
    {
        "category": "customer_active",
        "retention_period_days": 3650,  # 10 years from last order
        "legal_basis": "contract + tax_law",
        "action_after_expiry": "anonymize"
    },
    {
        "category": "financial_records",
        "retention_period_days": 3650,  # 10 years (German tax law)
        "legal_basis": "tax_law (§147 AO)",
        "action_after_expiry": "anonymize"  # Keep amounts, remove names
    },
    {
        "category": "marketing_consent",
        "retention_period_days": 730,  # 2 years inactive
        "legal_basis": "consent",
        "action_after_expiry": "delete"
    }
]
```

---

## 4. Required API Endpoints

### 4.1 Customer CRUD with GDPR

```python
# Create Customer
POST /api/v1/customers
{
  "first_name": "Max",
  "last_name": "Mustermann",
  "email": "max@example.de",
  "phone": "+49 123 456789",
  "address": {...},
  "consents": {
    "data_processing": true,  # Required for contract
    "marketing": false,
    "privacy_policy_version": "1.0",
    "consent_ip": "192.168.1.1"
  }
}

# Get Customer (with audit log)
GET /api/v1/customers/{id}
Response includes:
- Customer data
- Consent history
- Data retention status

# Update Customer (with audit trail)
PUT /api/v1/customers/{id}
→ Automatically logs changes to CustomerAuditLog

# Soft Delete (GDPR-compliant)
DELETE /api/v1/customers/{id}
→ Sets is_deleted=true, keeps data for retention period
```

### 4.2 GDPR Data Subject Rights Endpoints

```python
# Right to Access
GET /api/v1/customers/{id}/data-export
Query params: format=json|csv|xml
Response: Complete customer data package

# Right to Erasure
POST /api/v1/customers/{id}/gdpr-erasure
{
  "reason": "customer_request",
  "verification": "email_verified"
}
Response: {
  "status": "scheduled|completed|rejected",
  "message": "...",
  "deletion_date": "2025-11-20",
  "certificate_url": "/api/v1/gdpr/certificates/abc123"
}

# Right to Rectification
PUT /api/v1/customers/{id}/rectification
{
  "corrections": {
    "email": "newemail@example.de",
    "phone": "+49 987 654321"
  },
  "requested_by": "customer"
}

# Right to Data Portability
GET /api/v1/customers/{id}/export-portable
→ Returns data in structured, machine-readable format

# GDPR Request Management
POST /api/v1/gdpr/requests
{
  "customer_id": 123,
  "request_type": "erasure",
  "details": "Customer requested full deletion"
}

GET /api/v1/gdpr/requests
→ List all GDPR requests (for staff)

GET /api/v1/gdpr/requests/{id}
→ Get specific request status
```

### 4.3 Consent Management Endpoints

```python
# Update Consents
PATCH /api/v1/customers/{id}/consents
{
  "marketing": true,
  "email_communication": true,
  "consent_version": "2.0"
}
→ Logs consent changes with timestamp, IP

# Consent History
GET /api/v1/customers/{id}/consent-history
Response: [
  {
    "consent_type": "marketing",
    "status": true,
    "timestamp": "2025-01-15T10:00:00Z",
    "ip_address": "192.168.1.1",
    "version": "1.0"
  }
]
```

### 4.4 Audit & Compliance Endpoints

```python
# Audit Log
GET /api/v1/customers/{id}/audit-log
Query: start_date, end_date, action_type
Response: Filtered audit entries

# Compliance Dashboard (Admin only)
GET /api/v1/gdpr/compliance-status
Response: {
  "pending_erasure_requests": 2,
  "overdue_requests": 0,
  "customers_pending_deletion": 5,
  "retention_policy_violations": 0
}

# Data Retention Check (Background Job)
POST /api/v1/gdpr/check-retention
→ Identifies customers past retention period
```

---

## 5. Technical Security Measures (Article 32 GDPR)

### 5.1 Encryption Requirements

#### ❌ Data at Rest Encryption - **NOT IMPLEMENTED**

**Required**:
```yaml
# PostgreSQL encryption (transparent data encryption)
postgresql.conf:
  ssl: on
  ssl_cert_file: '/path/to/server.crt'
  ssl_key_file: '/path/to/server.key'

# Or use encrypted volumes
docker-compose.yml:
  volumes:
    - type: volume
      source: pgdata
      target: /var/lib/postgresql/data
      volume:
        encrypted: true
```

**Field-Level Encryption** (sensitive fields):
```python
from cryptography.fernet import Fernet

class Customer(Base):
    # Encrypt sensitive fields
    _phone_encrypted = Column(String)
    _address_encrypted = Column(Text)

    @hybrid_property
    def phone(self):
        if self._phone_encrypted:
            return decrypt_field(self._phone_encrypted)
        return None

    @phone.setter
    def phone(self, value):
        if value:
            self._phone_encrypted = encrypt_field(value)
```

#### ⚠️ Data in Transit - **PARTIAL**

**Required**:
```nginx
# Force HTTPS
server {
    listen 443 ssl http2;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
}
```

### 5.2 Access Control

**Required Role-Based Access Control (RBAC)**:

```python
class UserRole(Enum):
    ADMIN = "admin"  # Full access
    MANAGER = "manager"  # Customer + Order management
    GOLDSMITH = "goldsmith"  # Orders + Materials, limited customer view
    RECEPTIONIST = "receptionist"  # Customer + Order creation, no deletion
    ACCOUNTANT = "accountant"  # Read-only, export financial records

# Permission Matrix
PERMISSIONS = {
    "customers.create": [ADMIN, MANAGER, RECEPTIONIST],
    "customers.read": [ADMIN, MANAGER, GOLDSMITH, RECEPTIONIST, ACCOUNTANT],
    "customers.update": [ADMIN, MANAGER, RECEPTIONIST],
    "customers.delete": [ADMIN],  # Soft delete only
    "customers.export": [ADMIN, MANAGER],
    "customers.gdpr_erasure": [ADMIN],  # Critical action
    "audit_logs.read": [ADMIN, MANAGER],
}
```

### 5.3 Authentication Enhancements

**Current Issues**:
- ⚠️ Token in localStorage (XSS vulnerability)
- ❌ No token refresh
- ❌ No session management

**Required**:
```python
# Secure session management
class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    refresh_token_hash = Column(String, unique=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)

    ip_address = Column(String)
    user_agent = Column(String)

    is_active = Column(Boolean, default=True)
    revoked_at = Column(DateTime)
    revocation_reason = Column(String)

# API Changes
POST /api/v1/auth/refresh
{
  "refresh_token": "..."
}
Response: {
  "access_token": "...",
  "expires_in": 900  # 15 minutes
}

POST /api/v1/auth/logout
→ Revokes session, adds token to blacklist
```

### 5.4 Rate Limiting

**Required**:
```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

# Apply to sensitive endpoints
@app.post("/api/v1/customers/")
@limiter.limit("10/minute")  # Max 10 customers created per minute
async def create_customer(...):
    pass

@app.post("/api/v1/auth/login")
@limiter.limit("5/minute")  # Max 5 login attempts per minute
async def login(...):
    pass
```

### 5.5 Security Headers

**Required**:
```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["goldsmith-erp.local", "*.goldsmith-erp.com"])
app.add_middleware(HTTPSRedirectMiddleware)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
```

---

## 6. Organizational Measures

### 6.1 Data Protection Impact Assessment (DPIA)

**Required** when processing creates high risk to data subjects.

**For Goldsmith ERP**: DPIA needed because:
- ✅ Systematic customer profiling (order history)
- ✅ Large scale processing of personal data
- ✅ Automated processing

**DPIA Document**: `docs/DPIA.md` (to be created)

### 6.2 Data Processing Records (Article 30)

**Required**: Document all processing activities.

```markdown
## Processing Activity Record

**Activity**: Customer Order Management
**Controller**: [Your Business Name]
**Purpose**: Fulfill jewelry repair and custom order contracts
**Legal Basis**: Contract (GDPR Art. 6(1)(b))
**Categories of Data**: Name, email, phone, address, order details
**Recipients**: Internal staff only (goldsmiths, receptionists)
**Retention Period**: 10 years from last order (tax law compliance)
**Security Measures**: Encryption, access control, audit logging
```

### 6.3 Staff Training

**Required**:
- Train all staff on GDPR principles
- Document training completion
- Annual refresher training

**Training Topics**:
1. What is personal data?
2. Data subject rights
3. How to handle GDPR requests
4. Data breach procedures
5. Secure data handling

### 6.4 Data Breach Procedures

**Timeline**: Report to supervisory authority within **72 hours** if breach risks rights/freedoms.

**Implementation**:
```python
class DataBreach(Base):
    __tablename__ = "data_breaches"

    id = Column(Integer, primary_key=True)

    # Incident
    discovered_at = Column(DateTime, nullable=False)
    breach_type = Column(String)  # unauthorized_access, data_loss, ransomware
    severity = Column(String)  # low, medium, high, critical

    # Affected Data
    affected_customer_count = Column(Integer)
    data_types_affected = Column(JSONB)  # ["name", "email", "address"]

    # Response
    containment_actions = Column(Text)
    notification_required = Column(Boolean)
    authority_notified_at = Column(DateTime)
    customers_notified_at = Column(DateTime)

    # Resolution
    root_cause = Column(Text)
    remediation_steps = Column(Text)
    resolved_at = Column(DateTime)
```

### 6.5 Privacy Policy & Terms

**Required**: Clear, accessible privacy policy.

**Must include**:
- What data we collect
- Why we collect it (legal basis)
- How long we keep it
- Who we share it with
- Data subject rights
- Contact information (DPO if applicable)

**Location**: `/privacy-policy` page on website

---

## 7. Frontend GDPR Requirements

### 7.1 Consent Collection UI

**Required at registration/first order**:

```tsx
// ConsentForm.tsx
<form>
  <h2>Datenschutz & Einwilligung</h2>

  {/* Required for contract */}
  <p>
    <input type="checkbox" required checked disabled />
    Ich stimme der Verarbeitung meiner Daten zur Auftragsabwicklung zu. (Erforderlich)
  </p>

  {/* Optional consents */}
  <p>
    <input type="checkbox" name="marketing_consent" />
    Ich möchte Informationen über neue Angebote erhalten. (Optional)
  </p>

  <p>
    <input type="checkbox" name="email_consent" />
    Kontakt per E-Mail erlaubt. (Optional)
  </p>

  <p>
    <a href="/privacy-policy" target="_blank">Datenschutzerklärung lesen</a>
  </p>

  <button type="submit">Zustimmen & Fortfahren</button>
</form>
```

### 7.2 Customer Self-Service Portal

**Required**: Allow customers to manage their data.

```tsx
// CustomerPortal.tsx
<div className="customer-portal">
  <h1>Meine Daten</h1>

  <section>
    <h2>Persönliche Informationen</h2>
    <button onClick={handleEditInfo}>Bearbeiten</button>
  </section>

  <section>
    <h2>Einwilligungen</h2>
    <label>
      <input type="checkbox" checked={consents.marketing} onChange={handleConsentChange} />
      Marketing-E-Mails
    </label>
  </section>

  <section>
    <h2>Meine Rechte</h2>
    <button onClick={handleDataExport}>Meine Daten exportieren</button>
    <button onClick={handleDataDeletion} className="danger">
      Meine Daten löschen
    </button>
  </section>
</div>
```

### 7.3 Cookie Consent Banner

**Required**: If using non-essential cookies.

```tsx
// CookieBanner.tsx
<div className="cookie-banner">
  <p>
    Wir verwenden Cookies zur Verbesserung Ihrer Erfahrung.
    <a href="/cookie-policy">Mehr erfahren</a>
  </p>
  <button onClick={acceptAll}>Alle akzeptieren</button>
  <button onClick={acceptEssential}>Nur notwendige</button>
  <button onClick={showPreferences}>Einstellungen</button>
</div>
```

---

## 8. Automated Compliance Tasks

### 8.1 Background Jobs

**Required Scheduled Tasks**:

```python
# Daily: Check retention policies
@scheduler.scheduled_job('cron', hour=2)
async def check_data_retention():
    """
    Identify customers past retention period.
    Schedule for anonymization/deletion.
    """
    customers = await get_customers_past_retention()
    for customer in customers:
        if customer.can_be_deleted():
            schedule_gdpr_erasure(customer.id)

# Daily: Monitor GDPR request deadlines
@scheduler.scheduled_job('cron', hour=8)
async def check_gdpr_deadlines():
    """
    Alert staff about upcoming GDPR request deadlines.
    """
    overdue = await get_overdue_gdpr_requests()
    for request in overdue:
        send_alert_to_admin(request)

# Weekly: Audit log rotation
@scheduler.scheduled_job('cron', day_of_week='sun', hour=3)
async def rotate_audit_logs():
    """
    Archive old audit logs to cold storage.
    Keep 3 years online, rest archived.
    """
    old_logs = await get_audit_logs_older_than(years=3)
    archive_to_cold_storage(old_logs)

# Monthly: Compliance report
@scheduler.scheduled_job('cron', day=1, hour=9)
async def generate_compliance_report():
    """
    Generate monthly GDPR compliance report.
    """
    report = {
        "gdpr_requests_processed": await count_gdpr_requests_last_month(),
        "pending_requests": await count_pending_gdpr_requests(),
        "customers_deleted": await count_deletions_last_month(),
        "data_breaches": await count_breaches_last_month(),
    }
    send_report_to_admin(report)
```

---

## 9. Compliance Checklist

### Phase 1: Foundation (CRITICAL - Week 1-2)

- [ ] Create Customer model with GDPR fields
- [ ] Create CustomerAuditLog model
- [ ] Create GDPRRequest model
- [ ] Create DataRetentionPolicy model
- [ ] Implement audit logging middleware
- [ ] Add field-level encryption for sensitive data
- [ ] Configure database encryption at rest
- [ ] Implement secure session management

### Phase 2: Data Subject Rights (CRITICAL - Week 3-4)

- [ ] Implement Right to Access (data export API)
- [ ] Implement Right to Erasure (deletion API with checks)
- [ ] Implement Right to Rectification (update with audit)
- [ ] Implement Right to Data Portability (JSON/CSV export)
- [ ] Implement Consent Management API
- [ ] Create GDPR request tracking system

### Phase 3: Frontend (HIGH - Week 5-6)

- [ ] Create Customer registration with consent collection
- [ ] Create Customer self-service portal
- [ ] Implement data export UI
- [ ] Implement data deletion request UI
- [ ] Create consent management UI
- [ ] Add cookie consent banner (if needed)
- [ ] Create privacy policy page

### Phase 4: Security (HIGH - Week 7-8)

- [ ] Implement rate limiting
- [ ] Add security headers
- [ ] Implement RBAC (role-based access control)
- [ ] Add token refresh mechanism
- [ ] Implement token blacklist
- [ ] Add failed login tracking
- [ ] Implement account lockout
- [ ] Add 2FA (optional but recommended)

### Phase 5: Organizational (MEDIUM - Week 9-10)

- [ ] Write Data Protection Impact Assessment (DPIA)
- [ ] Document data processing activities (Article 30)
- [ ] Create privacy policy
- [ ] Create cookie policy
- [ ] Create data breach response procedure
- [ ] Train staff on GDPR
- [ ] Designate data protection contact person

### Phase 6: Automation (MEDIUM - Week 11-12)

- [ ] Implement data retention check (daily job)
- [ ] Implement GDPR deadline monitoring
- [ ] Implement automated anonymization
- [ ] Create compliance dashboard
- [ ] Set up monthly compliance reports
- [ ] Implement audit log archival

---

## 10. Penalties for Non-Compliance

**GDPR Fines** (Article 83):

| Violation | Maximum Fine |
|-----------|-------------|
| Basic processing principles (Art. 5-11) | **€20 million** or **4% of annual global turnover** |
| Data subject rights violations (Art. 12-22) | €20 million or 4% |
| No legal basis for processing | €20 million or 4% |
| Security requirements violations (Art. 32) | €10 million or 2% |
| No records of processing activities | €10 million or 2% |

**Additional Consequences**:
- Reputational damage
- Loss of customer trust
- Legal costs
- Compensation to affected individuals

---

## 11. Recommended Next Steps

### Immediate Actions (This Week)

1. **Stop processing real customer data** until GDPR compliance implemented
2. **Create Customer model** with all GDPR fields
3. **Implement audit logging** for all data access
4. **Write privacy policy** (consult lawyer)

### Short-term (Next 2 Weeks)

5. **Implement data subject rights APIs** (access, erasure, portability)
6. **Add data encryption** (at rest and field-level)
7. **Create consent management** system
8. **Build customer self-service portal**

### Medium-term (Next 4 Weeks)

9. **Complete DPIA** (Data Protection Impact Assessment)
10. **Train all staff** on GDPR
11. **Implement automated compliance checks**
12. **Set up compliance dashboard**

---

## 12. Resources & Further Reading

### Official GDPR Resources

- **GDPR Full Text**: https://gdpr-info.eu/
- **EU Data Protection Board**: https://edpb.europa.eu/
- **German Federal Data Protection**: https://www.bfdi.bund.de/

### Implementation Guides

- **ICO GDPR Guide**: https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/
- **GDPR Checklist**: https://gdpr.eu/checklist/

### Legal Consultation

⚠️ **Important**: This document provides technical guidance. Consult a data protection lawyer for legal advice specific to your situation.

---

## Document Revision History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-11-06 | Initial GDPR compliance guide | Claude |

---

**Next Document**: `SECURITY_REQUIREMENTS.md` - Detailed security implementation guide

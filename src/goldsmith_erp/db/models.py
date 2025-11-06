"""
Database models for Goldsmith ERP with GDPR compliance.

This module contains all SQLAlchemy ORM models including:
- User (staff members)
- Customer (GDPR-compliant customer data)
- Order (jewelry orders)
- Material (inventory management)
- CustomerAuditLog (GDPR audit trail)
- GDPRRequest (data subject rights tracking)
- DataRetentionPolicy (data retention management)
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Table, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timedelta

Base = declarative_base()

# ============================================================================
# Association Tables
# ============================================================================

# Many-to-Many between Material and Order
order_materials = Table(
    "order_materials",
    Base.metadata,
    Column("order_id", Integer, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
    Column("material_id", Integer, ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True),
    Column("quantity", Float, default=1.0),  # How much of this material used
    Column("unit_price_at_time", Float),  # Price at the time of order (historical)
)

# ============================================================================
# User Model (Staff/Employees)
# ============================================================================

class User(Base):
    """
    User model for staff members (employees) who use the system.
    Separated from Customer to maintain clear distinction between
    staff and customers.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)

    # Role-based access control
    role = Column(String, default="goldsmith", nullable=False, index=True)
    # Roles: admin, manager, goldsmith, receptionist, accountant

    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Track last login for security
    last_login_at = Column(DateTime)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)

    # Password management
    password_changed_at = Column(DateTime, default=datetime.utcnow)
    password_expires_at = Column(DateTime)  # For password expiry policy

    # Relationships
    created_customers = relationship("Customer", foreign_keys="Customer.created_by", back_populates="creator")
    updated_customers = relationship("Customer", foreign_keys="Customer.updated_by", back_populates="updater")
    deleted_customers = relationship("Customer", foreign_keys="Customer.deleted_by", back_populates="deleter")

    assigned_orders = relationship("Order", foreign_keys="Order.assigned_to", back_populates="assigned_user")

    audit_logs = relationship("CustomerAuditLog", back_populates="user")
    gdpr_requests_assigned = relationship("GDPRRequest", back_populates="assigned_user")

    sessions = relationship("UserSession", back_populates="user")

# ============================================================================
# Customer Model (GDPR-Compliant)
# ============================================================================

class Customer(Base):
    """
    GDPR-compliant customer model for jewelry business clients.
    Includes all required fields for EU General Data Protection Regulation compliance.
    """
    __tablename__ = "customers"

    # ========================================
    # Identity
    # ========================================
    id = Column(Integer, primary_key=True, index=True)
    customer_number = Column(String, unique=True, nullable=False, index=True)
    # Format: CUST-YYYYMM-XXXX (e.g., CUST-202501-0001)

    # ========================================
    # Personal Data (GDPR Article 4(1))
    # ========================================
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    phone = Column(String)  # Will be encrypted

    # ========================================
    # Address Data
    # ========================================
    address_line1 = Column(String)  # Will be encrypted
    address_line2 = Column(String)
    postal_code = Column(String)
    city = Column(String)
    country = Column(String, default="DE")  # ISO country code

    # ========================================
    # GDPR Compliance Fields (CRITICAL)
    # ========================================

    # Legal Basis for Processing (GDPR Article 6)
    legal_basis = Column(String, nullable=False, default="contract")
    # Values: contract, consent, legal_obligation, legitimate_interest

    # Consent Management (GDPR Article 7)
    consent_marketing = Column(Boolean, default=False, nullable=False)
    consent_date = Column(DateTime)
    consent_version = Column(String)  # Version of privacy policy accepted
    consent_ip_address = Column(String)  # IP address when consent given
    consent_method = Column(String)  # web_form, in_person, phone, email

    # Data Retention (GDPR Article 5(1)(e) - Storage Limitation)
    data_retention_category = Column(String, default="active", nullable=False, index=True)
    # Values: active, inactive, archived, scheduled_deletion
    last_order_date = Column(DateTime)
    retention_deadline = Column(DateTime)  # When data must be reviewed/deleted
    deletion_scheduled = Column(DateTime)  # Scheduled deletion date

    # Privacy Preferences (GDPR Article 21 - Right to Object)
    data_processing_consent = Column(Boolean, default=True, nullable=False)
    email_communication_consent = Column(Boolean, default=False, nullable=False)
    phone_communication_consent = Column(Boolean, default=False, nullable=False)
    sms_communication_consent = Column(Boolean, default=False, nullable=False)

    # ========================================
    # Audit Trail (GDPR Article 30 - Records of Processing)
    # ========================================
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))

    # ========================================
    # Soft Delete (GDPR Article 17 - Right to Erasure)
    # ========================================
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime)
    deleted_by = Column(Integer, ForeignKey("users.id"))
    deletion_reason = Column(Text)
    # Reasons: customer_request, gdpr_erasure, retention_expired, duplicate, data_error

    # ========================================
    # Additional Business Fields
    # ========================================
    notes = Column(Text)  # Internal notes about customer
    tags = Column(JSONB)  # Flexible tags: ["vip", "frequent", "wholesale"]
    custom_fields = Column(JSONB)  # Extensible custom data

    # Customer status
    is_active = Column(Boolean, default=True, nullable=False)

    # Business metrics
    total_orders_count = Column(Integer, default=0)
    total_orders_value = Column(Float, default=0.0)

    # ========================================
    # Relationships
    # ========================================
    orders = relationship("Order", back_populates="customer")
    audit_logs = relationship("CustomerAuditLog", back_populates="customer", cascade="all, delete-orphan")
    gdpr_requests = relationship("GDPRRequest", back_populates="customer", cascade="all, delete-orphan")

    creator = relationship("User", foreign_keys=[created_by], back_populates="created_customers")
    updater = relationship("User", foreign_keys=[updated_by], back_populates="updated_customers")
    deleter = relationship("User", foreign_keys=[deleted_by], back_populates="deleted_customers")

    def __repr__(self):
        return f"<Customer(id={self.id}, customer_number='{self.customer_number}', name='{self.first_name} {self.last_name}')>"

# ============================================================================
# Customer Audit Log (GDPR Accountability)
# ============================================================================

class CustomerAuditLog(Base):
    """
    Comprehensive audit logging for all customer data access and modifications.
    Required for GDPR Article 30 (Records of processing activities).
    """
    __tablename__ = "customer_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    # ========================================
    # Action Details
    # ========================================
    action = Column(String, nullable=False, index=True)
    # Actions: created, accessed, updated, deleted, exported, anonymized,
    #          consent_given, consent_withdrawn, gdpr_request

    entity = Column(String, nullable=False)
    # Entities: customer, order, consent, gdpr_request

    entity_id = Column(Integer)  # ID of the affected entity

    # ========================================
    # Change Tracking
    # ========================================
    field_name = Column(String)  # Which field was changed (for updates)
    old_value = Column(Text)  # Previous value (sanitized)
    new_value = Column(Text)  # New value (sanitized)

    # ========================================
    # Who & When
    # ========================================
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_email = Column(String)  # Denormalized for audit permanence
    user_role = Column(String)  # Role at time of action
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # ========================================
    # Context & Technical Details
    # ========================================
    ip_address = Column(String)
    user_agent = Column(String)
    endpoint = Column(String)  # API endpoint used
    http_method = Column(String)  # GET, POST, PUT, DELETE
    request_id = Column(String, index=True)  # Correlation ID for request tracing
    session_id = Column(String)  # Session identifier

    # ========================================
    # Legal & Compliance
    # ========================================
    legal_basis = Column(String)  # Legal basis for this action
    # Values: contract, consent, legal_obligation, legitimate_interest

    purpose = Column(String)  # Purpose of data processing
    # Values: order_fulfillment, customer_service, marketing, legal_compliance

    # ========================================
    # Additional Context
    # ========================================
    description = Column(Text)  # Human-readable description of action
    metadata = Column(JSONB)  # Additional context data

    # ========================================
    # Relationships
    # ========================================
    customer = relationship("Customer", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', customer_id={self.customer_id}, timestamp={self.timestamp})>"

# ============================================================================
# GDPR Request Tracking
# ============================================================================

class GDPRRequest(Base):
    """
    Track GDPR data subject rights requests.
    Supports: Right to Access, Erasure, Rectification, Portability, Objection, Restriction.
    """
    __tablename__ = "gdpr_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    # ========================================
    # Request Type (GDPR Chapter III)
    # ========================================
    request_type = Column(String, nullable=False, index=True)
    # Types: access (Art. 15), rectification (Art. 16), erasure (Art. 17),
    #        portability (Art. 20), objection (Art. 21), restriction (Art. 18)

    # ========================================
    # Status & Timeline
    # ========================================
    status = Column(String, default="pending", nullable=False, index=True)
    # Status: pending, in_progress, completed, rejected, cancelled

    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    due_date = Column(DateTime, nullable=False)  # Must respond within 1 month (GDPR Art. 12(3))
    completed_at = Column(DateTime)

    # ========================================
    # Request Details
    # ========================================
    request_details = Column(JSONB)
    # {
    #   "specific_data": ["orders", "personal_info"],
    #   "reason": "No longer using service",
    #   "format": "json" (for portability)
    # }

    response_details = Column(JSONB)
    # {
    #   "action_taken": "Data deleted",
    #   "files_generated": ["export.json"],
    #   "notes": "Completed as requested"
    # }

    rejection_reason = Column(Text)  # If request rejected, why (GDPR Art. 12(4))

    # ========================================
    # Processing & Assignment
    # ========================================
    assigned_to = Column(Integer, ForeignKey("users.id"))
    priority = Column(String, default="normal")  # urgent, high, normal, low

    # Identity Verification (GDPR Art. 12(6))
    verified = Column(Boolean, default=False, nullable=False)
    verification_method = Column(String)  # email, in_person, phone, document
    verification_date = Column(DateTime)

    # ========================================
    # Files & Documents
    # ========================================
    export_file_path = Column(String)  # Path to data export file (for portability)
    certificate_file_path = Column(String)  # Deletion certificate path
    attachments = Column(JSONB)  # Additional file paths

    # ========================================
    # Communication
    # ========================================
    communication_log = Column(JSONB)  # Log of communications with customer
    # [
    #   {"date": "2025-01-15", "method": "email", "subject": "Request received", "sent_by": 5}
    # ]

    # ========================================
    # Relationships
    # ========================================
    customer = relationship("Customer", back_populates="gdpr_requests")
    assigned_user = relationship("User", back_populates="gdpr_requests_assigned")

    def __repr__(self):
        return f"<GDPRRequest(id={self.id}, type='{self.request_type}', status='{self.status}', customer_id={self.customer_id})>"

# ============================================================================
# Data Retention Policy
# ============================================================================

class DataRetentionPolicy(Base):
    """
    Define data retention policies for different data categories.
    Implements GDPR Article 5(1)(e) - Storage Limitation principle.
    """
    __tablename__ = "data_retention_policies"

    id = Column(Integer, primary_key=True, index=True)

    # ========================================
    # Policy Definition
    # ========================================
    category = Column(String, nullable=False, unique=True, index=True)
    # Categories: customer_active, customer_inactive, financial_records,
    #             marketing_consent, order_records, audit_logs

    retention_period_days = Column(Integer, nullable=False)
    # How long to keep data (e.g., 3650 for 10 years)

    # ========================================
    # Legal Basis
    # ========================================
    legal_basis = Column(String, nullable=False)
    # Examples: "GDPR Art. 6(1)(b) - Contract",
    #           "§147 AO - German Tax Law",
    #           "GDPR Art. 6(1)(a) - Consent"

    jurisdiction = Column(String, default="EU")
    # Jurisdiction: EU, DE (Germany), AT (Austria), etc.

    # ========================================
    # Actions
    # ========================================
    action_after_expiry = Column(String, nullable=False)
    # Actions: delete, anonymize, archive, review

    auto_apply = Column(Boolean, default=False, nullable=False)
    # Whether policy is automatically enforced

    warning_days_before = Column(Integer, default=30)
    # Days before expiry to send warning

    # ========================================
    # Documentation
    # ========================================
    description = Column(Text)
    policy_document_url = Column(String)  # Link to detailed policy document

    # ========================================
    # Metadata
    # ========================================
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))

    # ========================================
    # Relationships
    # ========================================
    creator = relationship("User")

    def __repr__(self):
        return f"<DataRetentionPolicy(category='{self.category}', days={self.retention_period_days}, action='{self.action_after_expiry}')>"

# ============================================================================
# Order Model (Updated)
# ============================================================================

class Order(Base):
    """
    Order model for jewelry repair and custom work orders.
    Now references Customer table (not User).
    """
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, index=True)  # ORDER-YYYYMM-XXXX

    # ========================================
    # Order Details
    # ========================================
    title = Column(String, nullable=False)
    description = Column(Text)
    notes = Column(Text)  # Internal notes

    # ========================================
    # Customer Reference (UPDATED - now references customers)
    # ========================================
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)

    # ========================================
    # Pricing
    # ========================================
    subtotal = Column(Float, default=0.0)  # Before tax
    tax_rate = Column(Float, default=19.0)  # VAT rate (19% in Germany)
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)  # Final price including tax

    # Legacy price field (for backward compatibility)
    price = Column(Float)  # Deprecated - use total_amount

    # ========================================
    # Workflow & Status
    # ========================================
    status = Column(String, default="draft", nullable=False, index=True)
    # Status: draft, confirmed, in_progress, quality_check, completed, delivered, cancelled

    workflow_state = Column(String, default="draft", index=True)
    # More detailed workflow tracking

    # ========================================
    # Assignment & Scheduling
    # ========================================
    assigned_to = Column(Integer, ForeignKey("users.id"))  # Assigned goldsmith
    priority = Column(String, default="normal")  # urgent, high, normal, low

    # ========================================
    # Dates
    # ========================================
    delivery_date = Column(DateTime)  # Promised delivery date
    started_at = Column(DateTime)  # When work started
    completed_at = Column(DateTime)  # When work finished
    delivered_at = Column(DateTime)  # When delivered to customer
    cancelled_at = Column(DateTime)

    # ========================================
    # Timestamps
    # ========================================
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ========================================
    # Relationships
    # ========================================
    customer = relationship("Customer", back_populates="orders")
    assigned_user = relationship("User", foreign_keys=[assigned_to], back_populates="assigned_orders")
    materials = relationship("Material", secondary=order_materials, back_populates="orders")

    def __repr__(self):
        return f"<Order(id={self.id}, order_number='{self.order_number}', customer_id={self.customer_id}, status='{self.status}')>"

# ============================================================================
# Material Model (Unchanged)
# ============================================================================

class Material(Base):
    """
    Material/Inventory model for tracking gold, silver, stones, tools, etc.
    """
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    material_type = Column(String, nullable=False, index=True)
    # Types: gold, silver, platinum, stone, tool, other

    description = Column(Text)
    unit_price = Column(Float, nullable=False)
    stock = Column(Float, nullable=False, default=0)
    unit = Column(String, nullable=False)  # g, kg, pcs (pieces), ct (carat)
    min_stock = Column(Float, default=0)  # Minimum stock level for alerts
    properties = Column(JSONB)  # Type-specific fields: purity, size, color, quality, etc.

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    orders = relationship("Order", secondary=order_materials, back_populates="materials")

    def __repr__(self):
        return f"<Material(id={self.id}, name='{self.name}', stock={self.stock} {self.unit})>"

# ============================================================================
# User Session Model (for secure session management)
# ============================================================================

class UserSession(Base):
    """
    Track user sessions for secure authentication.
    Implements token refresh and session management.
    """
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # ========================================
    # Token Information
    # ========================================
    token_hash = Column(String, nullable=False, unique=True, index=True)  # SHA256 hash of token
    refresh_token_hash = Column(String, unique=True, index=True)  # SHA256 hash of refresh token

    # ========================================
    # Session Timing
    # ========================================
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Token expiration
    refresh_expires_at = Column(DateTime, nullable=False)  # Refresh token expiration
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ========================================
    # Client Information
    # ========================================
    ip_address = Column(String)
    user_agent = Column(String)
    device_type = Column(String)  # web, mobile, tablet

    # ========================================
    # Session Status
    # ========================================
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    revoked_at = Column(DateTime)
    revocation_reason = Column(String)  # logout, security, expired, password_change

    # ========================================
    # Relationships
    # ========================================
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id}, active={self.is_active})>"

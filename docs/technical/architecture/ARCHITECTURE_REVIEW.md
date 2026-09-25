# Architecture Review: Goldsmith ERP System

> ⚠️ **SUPERSEDED (2026-09-25, ARCH-16).** This review is from 2025-11-09
> against a 39-file/v0.1.0 codebase and most of its P0/P1 items (hardcoded
> secrets, N+1 queries, connection pooling, transactions) have since been
> fixed or superseded by later work. It is no longer "READ THIS FIRST" — use
> the current architecture review instead:
> [docs/review/2026-09-25/01-architecture.md](../../review/2026-09-25/01-architecture.md)
> (plus [00-SUMMARY.md](../../review/2026-09-25/00-SUMMARY.md) and
> [MASTER-FIX-PLAN.md](../../review/2026-09-25/MASTER-FIX-PLAN.md) for what is
> open). Kept here for historical reference only, not deleted.

# Architecture Review: Goldsmith ERP System
**Review Date:** 2025-11-09
**Reviewer:** Senior Software Architect
**Codebase:** Goldsmith ERP v0.1.0 (39 Python files, 195 TypeScript files)

---

## Executive Summary

Das Goldsmith ERP ist ein gut strukturiertes System mit solider Grundarchitektur. Es verwendet moderne Technologien (FastAPI, React, PostgreSQL, Redis) und folgt vielen Best Practices. **Jedoch gibt es signifikante architektonische Probleme, die die Skalierbarkeit, Wartbarkeit und Sicherheit beeinträchtigen.**

### Critical Issues (P0 - Sofort beheben)
1. ❌ **Hardcoded Secrets in Config** - `SECRET_KEY` im Code
2. ❌ **Fehlende Error Handling Strategie** - Inkonsistente Exception-Behandlung
3. ❌ **N+1 Query Problem** - Ineffiziente DB-Queries in Services
4. ❌ **Redis Connection Pool Leak** - Neue Connection pro Request
5. ❌ **Fehlende Input Validation** - SQL Injection Risiko
6. ❌ **Keine Transaktions-Management** - Data Integrity Risk

### High Priority Issues (P1 - Diese Woche)
7. ⚠️ **Fehlende Dependency Injection** - Tight Coupling
8. ⚠️ **Mixed Concerns in Services** - Business Logic + DB Access
9. ⚠️ **Fehlende DTOs für ML Features** - 60+ Features hardcoded
10. ⚠️ **Keine Caching Strategy** - Unnötige DB-Hits
11. ⚠️ **LocalStorage für Sensitive Data** - XSS Vulnerability
12. ⚠️ **Fehlende Request Rate Limiting**

### Medium Priority (P2 - Nächste 2 Wochen)
13. 📊 **Fehlende Monitoring & Observability**
14. 📊 **Keine Structured Logging**
15. 📊 **Fehlende Health Checks**
16. 📊 **Keine Circuit Breakers für externe Services**
17. 📊 **Manuelle DB Migrations** - Risiko bei Rollbacks

---

## 1. Backend-Architektur

### 1.1 Current State: Layered Architecture
```
┌─────────────────────────────────────┐
│     API Layer (Routers)             │
│  - auth.py, orders.py, etc.         │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│     Service Layer                   │
│  - order_service.py                 │
│  - time_tracking_service.py         │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│     Data Layer (Models)             │
│  - SQLAlchemy Models                │
└─────────────────────────────────────┘
```

**Problem:** Service Layer mischt Business Logic mit Datenbank-Zugriff.

### 1.2 ❌ CRITICAL: Hardcoded Secrets

**Location:** `src/goldsmith_erp/core/config.py:25`
```python
SECRET_KEY: str = "change_this_to_a_secure_random_string"
```

**Risk:**
- Secret ist im Git-Repository committed
- Alle JWT-Tokens können geknackt werden
- Production-System ist kompromittiert

**Fix:**
```python
# config.py
from pydantic import Field, field_validator
import secrets

class Settings(BaseSettings):
    SECRET_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="JWT secret key - MUST be set in production"
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == "change_this_to_a_secure_random_string":
            raise ValueError(
                "SECRET_KEY must be changed from default! "
                "Set SECRET_KEY environment variable."
            )
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v
```

**Environment Setup:**
```bash
# .env (NICHT ins Git!)
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
```

### 1.3 ❌ CRITICAL: Redis Connection Pool Leak

**Location:** `src/goldsmith_erp/core/pubsub.py:20-24`
```python
async def get_redis_connection() -> redis.Redis:
    """Acquire a Redis client instance from the connection pool."""
    return redis.Redis(connection_pool=_redis_pool)
```

**Problem:**
- Neue Redis-Connection pro Request wird **NICHT geschlossen**
- Connection Pool wird erschöpft (default: 50 connections)
- Memory Leak bei hoher Last

**Fix:**
```python
# pubsub.py - Richtige Context Manager Implementation
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_redis_client():
    """Acquire Redis client with proper cleanup."""
    client = redis.Redis(connection_pool=_redis_pool)
    try:
        yield client
    finally:
        await client.close()

async def publish_event(channel: str, message: str) -> None:
    """Publish with automatic cleanup."""
    async with get_redis_client() as client:
        await client.publish(channel, message)
```

### 1.4 ❌ CRITICAL: N+1 Query Problem

**Location:** `src/goldsmith_erp/services/time_tracking_service.py:125-138`
```python
async def get_time_entries_for_order(
    db: AsyncSession, order_id: int, skip: int = 0, limit: int = 100
) -> List[TimeEntryModel]:
    """Holt alle Zeiterfassungen für einen bestimmten Auftrag."""
    result = await db.execute(
        select(TimeEntryModel)
        .options(
            selectinload(TimeEntryModel.activity),
            selectinload(TimeEntryModel.user),
        )
        # ❌ Fehlende selectinload für order, interruptions!
        .filter(TimeEntryModel.order_id == order_id)
```

**Problem:**
- Für jede TimeEntry wird Order einzeln geladen (N+1)
- Bei 100 TimeEntries = 101 Queries statt 1
- Interruptions werden lazy geladen → weitere 100 Queries

**Fix:**
```python
async def get_time_entries_for_order(
    db: AsyncSession, order_id: int, skip: int = 0, limit: int = 100
) -> List[TimeEntryModel]:
    """Optimized with complete eager loading."""
    result = await db.execute(
        select(TimeEntryModel)
        .options(
            selectinload(TimeEntryModel.activity),
            selectinload(TimeEntryModel.user),
            selectinload(TimeEntryModel.order),  # ✅ Added
            selectinload(TimeEntryModel.interruptions),  # ✅ Added
            selectinload(TimeEntryModel.photos),  # ✅ Added
        )
        .filter(TimeEntryModel.order_id == order_id)
        .order_by(TimeEntryModel.start_time.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
```

### 1.5 ❌ CRITICAL: Fehlende Transaktions-Management

**Location:** `src/goldsmith_erp/services/order_service.py:33-70`
```python
async def create_order(db: AsyncSession, order_in: OrderCreate) -> OrderModel:
    """Erstellt einen neuen Auftrag."""
    order_data = order_in.dict(exclude={"materials"})
    db_order = OrderModel(**order_data)

    # ❌ Keine explizite Transaction
    # ❌ Was passiert wenn materials.scalars().all() fehlschlägt?
    # ❌ Was passiert wenn Redis publish fehlschlägt?

    if order_in.materials:
        material_results = await db.execute(...)
        materials = material_results.scalars().all()
        db_order.materials = materials

    db.add(db_order)
    await db.commit()  # ❌ Partial commit möglich!
    await db.refresh(db_order)

    await publish_event(...)  # ❌ Event published NACH commit (Order existiert)
    return db_order
```

**Problem:**
- Bei Fehler in `publish_event` bleibt Order in DB (Inkonsistenz)
- Bei Fehler in Material-Zuordnung bleibt Order ohne Materials
- Keine Rollback-Strategie

**Fix:**
```python
from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError

@asynccontextmanager
async def transactional_session(db: AsyncSession):
    """Context manager for transactional operations."""
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise

async def create_order(db: AsyncSession, order_in: OrderCreate) -> OrderModel:
    """Erstellt einen neuen Auftrag mit ACID-Garantien."""
    try:
        async with transactional_session(db):
            order_data = order_in.dict(exclude={"materials"})
            db_order = OrderModel(**order_data)

            if order_in.materials:
                material_results = await db.execute(
                    select(Material).filter(Material.id.in_(order_in.materials))
                )
                materials = material_results.scalars().all()

                # Validate all materials exist
                if len(materials) != len(order_in.materials):
                    raise ValueError("Some materials not found")

                db_order.materials = materials

            db.add(db_order)
            await db.flush()  # ✅ Get ID without commit

            # ✅ Event publishing INNERHALB der Transaction
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "create",
                    "order_id": db_order.id,
                    "status": db_order.status,
                })
            )

        # ✅ Transaction erfolgreich committed
        await db.refresh(db_order)
        return db_order

    except SQLAlchemyError as e:
        logger.error(f"Database error creating order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
```

### 1.6 ⚠️ HIGH: Mixed Concerns in Services

**Problem:** Services mischen Business Logic mit DB-Zugriff.

**Empfohlene Architektur: Repository Pattern + Domain Services**

```python
# repositories/time_entry_repository.py
from abc import ABC, abstractmethod

class TimeEntryRepository(ABC):
    """Abstract repository for data access."""

    @abstractmethod
    async def create(self, entry: TimeEntryModel) -> TimeEntryModel:
        pass

    @abstractmethod
    async def get_by_id(self, entry_id: str) -> Optional[TimeEntryModel]:
        pass

    @abstractmethod
    async def get_running_for_user(self, user_id: int) -> Optional[TimeEntryModel]:
        pass

class SQLAlchemyTimeEntryRepository(TimeEntryRepository):
    """Concrete PostgreSQL implementation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, entry: TimeEntryModel) -> TimeEntryModel:
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def get_running_for_user(self, user_id: int) -> Optional[TimeEntryModel]:
        result = await self.db.execute(
            select(TimeEntryModel)
            .filter(
                and_(
                    TimeEntryModel.user_id == user_id,
                    TimeEntryModel.end_time.is_(None)
                )
            )
        )
        return result.scalar_one_or_none()

# services/time_tracking_domain_service.py
class TimeTrackingDomainService:
    """Pure business logic - NO database access."""

    def __init__(
        self,
        time_entry_repo: TimeEntryRepository,
        activity_repo: ActivityRepository,
        event_publisher: EventPublisher,
    ):
        self.time_entry_repo = time_entry_repo
        self.activity_repo = activity_repo
        self.event_publisher = event_publisher

    async def start_tracking(
        self, order_id: int, user_id: int, activity_id: int
    ) -> TimeEntryModel:
        """Start time tracking with business rules."""

        # Rule 1: User can only have ONE running entry
        running = await self.time_entry_repo.get_running_for_user(user_id)
        if running:
            raise BusinessRuleViolation(
                f"User already has running entry: {running.id}"
            )

        # Rule 2: Activity must exist and be active
        activity = await self.activity_repo.get_by_id(activity_id)
        if not activity:
            raise BusinessRuleViolation("Activity not found")

        # Create entry
        entry = TimeEntryModel(
            id=str(uuid.uuid4()),
            order_id=order_id,
            user_id=user_id,
            activity_id=activity_id,
            start_time=datetime.utcnow(),
        )

        # Save
        entry = await self.time_entry_repo.create(entry)

        # Publish domain event
        await self.event_publisher.publish(
            TimeTrackingStartedEvent(
                entry_id=entry.id,
                order_id=order_id,
                user_id=user_id,
            )
        )

        # Update activity stats (side effect)
        await self.activity_repo.increment_usage(activity_id)

        return entry
```

**Benefits:**
- ✅ Testbar ohne Datenbank (Mock Repository)
- ✅ Business Rules explizit
- ✅ Austauschbare Datenschicht (PostgreSQL → MongoDB)
- ✅ Klare Separation of Concerns

---

## 2. Frontend-Architektur

### 2.1 ❌ CRITICAL: LocalStorage für Access Tokens

**Location:** `frontend/src/api/client.ts:19`
```typescript
const token = localStorage.getItem('access_token');
```

**Problem:**
- XSS-Angriff kann Token stehlen
- Token ist persistent (überlebt Browser-Neustart)
- Kein HttpOnly-Flag möglich

**Fix: HttpOnly Cookies + CSRF Protection**
```typescript
// backend: auth.py
from fastapi import Response

@router.post("/login/access-token")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    # ... authentication logic ...

    access_token = create_access_token(data={"sub": str(user.id)})

    # ✅ Set HttpOnly cookie instead of returning in body
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # ✅ Not accessible via JavaScript
        secure=True,    # ✅ HTTPS only
        samesite="strict",  # ✅ CSRF protection
        max_age=60 * 60 * 24 * 8,  # 8 days
    )

    return {"message": "Login successful"}

// frontend: Remove localStorage, use credentials
const apiClient = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,  // ✅ Send cookies
});

// Remove token interceptor - cookies sent automatically
```

### 2.2 ⚠️ HIGH: Fehlende State Management Architektur

**Current:** React Context für alles (OrderContext, AuthContext)

**Problem bei Skalierung:**
- Alle Komponenten re-rendern bei jedem State-Change
- Keine DevTools für Debugging
- Schwer testbar

**Recommended: Zustand oder Redux Toolkit**
```typescript
// stores/timeTrackingStore.ts
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface TimeTrackingState {
  runningEntry: TimeEntry | null;
  activities: Activity[];

  // Actions
  startTracking: (orderId: number, activityId: number) => Promise<void>;
  stopTracking: (entryId: string) => Promise<void>;
  loadActivities: () => Promise<void>;
}

export const useTimeTrackingStore = create<TimeTrackingState>()(
  devtools(
    persist(
      (set, get) => ({
        runningEntry: null,
        activities: [],

        startTracking: async (orderId, activityId) => {
          const entry = await timeTrackingApi.start(orderId, activityId);
          set({ runningEntry: entry });
        },

        stopTracking: async (entryId) => {
          await timeTrackingApi.stop(entryId);
          set({ runningEntry: null });
        },

        loadActivities: async () => {
          const activities = await activitiesApi.getAll();
          set({ activities });
        },
      }),
      { name: 'time-tracking-store' }
    )
  )
);

// Usage in component
const { runningEntry, startTracking } = useTimeTrackingStore();
```

### 2.3 ⚠️ HIGH: Fehlende Error Boundaries

**Problem:** Fehler in einem Component crashen die gesamte App.

**Fix:**
```typescript
// components/ErrorBoundary.tsx
import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // ✅ Send to monitoring service (Sentry)
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="error-fallback">
          <h2>Etwas ist schiefgelaufen</h2>
          <details>
            <summary>Fehlerdetails</summary>
            <pre>{this.state.error?.message}</pre>
          </details>
          <button onClick={() => window.location.reload()}>
            Seite neu laden
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

// App.tsx
<ErrorBoundary>
  <OrderProvider>
    <Routes />
  </OrderProvider>
</ErrorBoundary>
```

---

## 3. Datenbank-Design

### 3.1 ⚠️ Medium: Fehlende Soft Deletes

**Problem:** `DELETE` löscht Daten permanent → Audit Trail verloren.

**Fix: Soft Delete Pattern**
```python
# models.py - Base Model mit Soft Delete
class SoftDeleteMixin:
    """Mixin für Soft Delete Funktionalität."""
    deleted_at = Column(DateTime, nullable=True, default=None)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    def soft_delete(self):
        """Mark as deleted without removing from database."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

class Order(Base, SoftDeleteMixin):
    __tablename__ = "orders"
    # ... existing fields ...

# Repository mit Soft Delete Support
class BaseRepository:
    async def delete(self, entity_id: int, hard: bool = False):
        """Soft delete by default, hard delete optional."""
        entity = await self.get_by_id(entity_id)
        if not entity:
            raise NotFoundError()

        if hard:
            await self.db.delete(entity)
        else:
            entity.soft_delete()

        await self.db.commit()

    async def get_all(self, include_deleted: bool = False):
        """Exclude deleted by default."""
        query = select(self.model_class)
        if not include_deleted:
            query = query.filter(self.model_class.is_deleted == False)

        result = await self.db.execute(query)
        return result.scalars().all()
```

### 3.2 ⚠️ Medium: Fehlende Database Indexes

**Problem:** Slow queries bei großen Datenmengen.

**Missing Indexes:**
```python
# Migration: add_missing_indexes.py
def upgrade() -> None:
    # ✅ Composite index für häufige Queries
    op.create_index(
        'ix_time_entries_order_user',
        'time_entries',
        ['order_id', 'user_id'],
        unique=False
    )

    # ✅ Index für Zeitbereich-Queries
    op.create_index(
        'ix_time_entries_start_time_order',
        'time_entries',
        ['start_time', 'order_id'],
        unique=False
    )

    # ✅ Index für ML Feature Extraction
    op.create_index(
        'ix_time_entries_activity_duration',
        'time_entries',
        ['activity_id', 'duration_minutes'],
        unique=False,
        postgresql_where=text('end_time IS NOT NULL')  # Partial index
    )

    # ✅ Full-text search index für Notizen
    op.execute("""
        CREATE INDEX ix_time_entries_notes_fts
        ON time_entries
        USING gin(to_tsvector('german', notes))
    """)
```

### 3.3 ❌ CRITICAL: Fehlende Database Constraints

**Problem:** Data Integrity kann verletzt werden.

**Fix: Add Constraints**
```python
# Migration: add_data_constraints.py
def upgrade() -> None:
    # ✅ Check Constraint: Ratings zwischen 1-5
    op.create_check_constraint(
        'ck_time_entries_complexity_rating',
        'time_entries',
        'complexity_rating IS NULL OR (complexity_rating >= 1 AND complexity_rating <= 5)'
    )

    # ✅ Check Constraint: end_time nach start_time
    op.create_check_constraint(
        'ck_time_entries_time_order',
        'time_entries',
        'end_time IS NULL OR end_time > start_time'
    )

    # ✅ Check Constraint: duration konsistent
    op.create_check_constraint(
        'ck_time_entries_duration_positive',
        'time_entries',
        'duration_minutes IS NULL OR duration_minutes > 0'
    )

    # ✅ Unique Constraint: Keine doppelten Running Entries
    op.create_index(
        'ix_time_entries_one_running_per_user',
        'time_entries',
        ['user_id'],
        unique=True,
        postgresql_where=text('end_time IS NULL')
    )
```

---

## 4. Security & Authentication

### 4.1 ❌ CRITICAL: Fehlende Input Validation

**Location:** `src/goldsmith_erp/api/routers/time_tracking.py`

**Problem:** User Input wird nicht validiert → SQL Injection möglich.

**Example:**
```python
@router.get("/order/{order_id}/total")
async def get_total_time_for_order(
    order_id: int,  # ❌ Nur Type-Check, keine Validation
    db: AsyncSession = Depends(get_db),
):
    # ❌ Was wenn order_id = -1? Oder 999999999999999?
    return await TimeTrackingService.get_total_time_for_order(db, order_id)
```

**Fix: Comprehensive Validation**
```python
from pydantic import Field, validator

class OrderIdParam(BaseModel):
    order_id: int = Field(gt=0, description="Order ID must be positive")

@router.get("/order/{order_id}/total")
async def get_total_time_for_order(
    params: OrderIdParam = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ✅ Validate user has access to this order
    order = await OrderService.get_order(db, params.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # ✅ Authorization check
    if not await has_order_access(current_user, order):
        raise HTTPException(status_code=403, detail="Access denied")

    return await TimeTrackingService.get_total_time_for_order(db, params.order_id)
```

### 4.2 ⚠️ HIGH: Fehlende Rate Limiting

**Problem:** API kann durch Brute-Force Angriffe überlastet werden.

**Fix: slowapi Integration**
```python
# main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# routers/auth.py
@router.post("/login/access-token")
@limiter.limit("5/minute")  # ✅ Max 5 Login-Versuche pro Minute
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    # ... authentication logic ...
```

### 4.3 ⚠️ HIGH: Fehlende RBAC (Role-Based Access Control)

**Problem:** Alle User haben gleiche Rechte.

**Fix: Implement RBAC**
```python
# models.py
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    GOLDSMITH = "goldsmith"
    VIEWER = "viewer"

class Permission(str, Enum):
    ORDER_CREATE = "order:create"
    ORDER_EDIT = "order:edit"
    ORDER_DELETE = "order:delete"
    TIME_TRACK = "time:track"
    REPORTS_VIEW = "reports:view"

class User(Base):
    role = Column(Enum(UserRole), default=UserRole.VIEWER)

# permissions.py
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [p for p in Permission],
    UserRole.GOLDSMITH: [
        Permission.ORDER_CREATE,
        Permission.ORDER_EDIT,
        Permission.TIME_TRACK,
    ],
    UserRole.VIEWER: [
        Permission.REPORTS_VIEW,
    ],
}

def require_permission(permission: Permission):
    """Decorator for permission checking."""
    def decorator(func):
        @wraps(func)
        async def wrapper(
            *args,
            current_user: User = Depends(get_current_user),
            **kwargs
        ):
            if permission not in ROLE_PERMISSIONS[current_user.role]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {permission}"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

# Usage
@router.delete("/{order_id}")
@require_permission(Permission.ORDER_DELETE)
async def delete_order(order_id: int, current_user: User = Depends()):
    # ...
```

---

## 5. Performance & Scalability

### 5.1 ⚠️ HIGH: Fehlende Caching Strategy

**Problem:** Gleiche Daten werden mehrfach aus DB geladen.

**Fix: Redis Caching mit Cache-Aside Pattern**
```python
# core/cache.py
from functools import wraps
import json
import hashlib

class CacheService:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def get(self, key: str):
        """Get cached value."""
        value = await self.redis.get(key)
        return json.loads(value) if value else None

    async def set(self, key: str, value: any, ttl: int = 300):
        """Cache value with TTL (default 5 min)."""
        await self.redis.setex(key, ttl, json.dumps(value))

    async def invalidate(self, pattern: str):
        """Invalidate cache by pattern."""
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

def cached(ttl: int = 300, key_prefix: str = ""):
    """Decorator for caching function results."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function + args
            cache_key = f"{key_prefix}:{func.__name__}:{hash_args(args, kwargs)}"

            # Try to get from cache
            cache_service = kwargs.get('cache', None)
            if cache_service:
                cached_value = await cache_service.get(cache_key)
                if cached_value:
                    return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            if cache_service:
                await cache_service.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator

# Usage in service
@cached(ttl=600, key_prefix="activities")
async def get_most_used_activities(
    db: AsyncSession,
    cache: CacheService,
    limit: int = 10
):
    # ... database query ...
    return activities

# Invalidate on update
async def create_time_entry(...):
    entry = await repo.create(...)

    # ✅ Invalidate related caches
    await cache.invalidate("activities:*")
    await cache.invalidate(f"order:{entry.order_id}:*")

    return entry
```

### 5.2 📊 Medium: Fehlende Database Connection Pooling Config

**Problem:** Default Pool-Size kann zu klein sein.

**Fix: Optimierte Pool Config**
```python
# db/session.py
engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,
    future=True,

    # ✅ Connection Pool Configuration
    pool_size=20,              # Base pool size
    max_overflow=30,           # Extra connections bei Last
    pool_timeout=30,           # Wait timeout (seconds)
    pool_recycle=3600,         # Recycle connections after 1h
    pool_pre_ping=True,        # Verify connection before using

    # ✅ Execution Options
    echo_pool=settings.DEBUG,  # Log pool events
    connect_args={
        "server_settings": {
            "application_name": "goldsmith_erp",
            "jit": "off",       # Disable JIT for consistent performance
        },
        "command_timeout": 60,  # Query timeout
    }
)
```

### 5.3 📊 Medium: Fehlende Pagination Default Limits

**Problem:** User kann unbegrenzt Daten abrufen → DoS.

**Fix: Pagination Limits**
```python
# api/pagination.py
from pydantic import BaseModel, Field

class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0, description="Offset")
    limit: int = Field(
        50,
        ge=1,
        le=100,  # ✅ Maximum 100 items per request
        description="Items per page"
    )

# Usage
@router.get("/", response_model=List[TimeEntryRead])
async def list_time_entries(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    return await TimeTrackingService.get_entries(
        db,
        skip=pagination.skip,
        limit=pagination.limit
    )
```

---

## 6. Monitoring & Observability

### 6.1 ❌ CRITICAL: Fehlende Structured Logging

**Problem:** Print-Statements statt Logging Framework.

**Current:**
```python
print("WebSocket disconnected")  # ❌ main.py:52
print(f"Redis subscription error: {exc}")  # ❌ pubsub.py:71
```

**Fix: Structured Logging**
```python
# core/logging_config.py
import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging(app_name: str = "goldsmith_erp"):
    """Configure structured JSON logging."""

    logger = logging.getLogger(app_name)
    logger.setLevel(logging.INFO)

    # JSON formatter for production
    formatter = jsonlogger.JsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s',
        rename_fields={'levelname': 'level', 'asctime': 'timestamp'}
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

# Usage
logger = setup_logging()

# ✅ Instead of print()
logger.info("websocket_disconnected", extra={
    "client_id": client_id,
    "duration_seconds": duration,
})

logger.error("redis_subscription_error", extra={
    "channel": channel,
    "error": str(exc),
    "traceback": traceback.format_exc(),
})
```

### 6.2 📊 Medium: Fehlende Metrics & Tracing

**Fix: OpenTelemetry Integration**
```python
# pyproject.toml
[tool.poetry.dependencies]
opentelemetry-api = "^1.20.0"
opentelemetry-sdk = "^1.20.0"
opentelemetry-instrumentation-fastapi = "^0.41b0"
opentelemetry-instrumentation-sqlalchemy = "^0.41b0"

# core/telemetry.py
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Setup tracing
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

# Setup metrics
metrics.set_meter_provider(MeterProvider())
meter = metrics.get_meter(__name__)

# Custom metrics
time_entry_counter = meter.create_counter(
    "time_entries_created",
    description="Number of time entries created"
)

activity_duration_histogram = meter.create_histogram(
    "activity_duration_minutes",
    description="Activity duration distribution"
)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Instrument SQLAlchemy
SQLAlchemyInstrumentor().instrument(engine=engine)

# Usage in service
async def start_time_entry(...):
    with tracer.start_as_current_span("start_time_tracking") as span:
        span.set_attribute("order_id", order_id)
        span.set_attribute("user_id", user_id)

        entry = await repo.create(...)

        # Record metrics
        time_entry_counter.add(1, {"activity": activity.name})

        return entry
```

### 6.3 📊 Medium: Fehlende Health Checks

**Fix: Comprehensive Health Endpoints**
```python
# api/routers/health.py
from fastapi import APIRouter, Depends
from sqlalchemy import text

router = APIRouter()

@router.get("/health")
async def health_check():
    """Basic liveness check."""
    return {"status": "ok"}

@router.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
):
    """Readiness check - verify dependencies."""
    checks = {}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check Redis
    try:
        async with get_redis_client() as redis:
            await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Overall status
    healthy = all(v == "ok" for v in checks.values())
    status_code = 200 if healthy else 503

    return JSONResponse(
        content={"status": "ready" if healthy else "not ready", "checks": checks},
        status_code=status_code
    )

# K8s config
# livenessProbe:
#   httpGet:
#     path: /health
#     port: 8000
# readinessProbe:
#   httpGet:
#     path: /health/ready
#     port: 8000
```

---

## 7. ML-Komponenten (Zukünftig)

### 7.1 ⚠️ HIGH: Fehlende ML Model Versioning

**Problem:** ML-Modelle werden direkt deployed ohne Versionierung.

**Fix: MLflow Integration**
```python
# ml/model_registry.py
import mlflow
from mlflow.tracking import MlflowClient

class ModelRegistry:
    def __init__(self, tracking_uri: str = "sqlite:///mlruns.db"):
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient()

    def register_model(
        self,
        model,
        name: str,
        metrics: dict,
        artifacts: dict = None
    ):
        """Register ML model with version tracking."""
        with mlflow.start_run():
            # Log parameters
            mlflow.log_params(model.get_params())

            # Log metrics
            for metric, value in metrics.items():
                mlflow.log_metric(metric, value)

            # Log model
            mlflow.sklearn.log_model(
                model,
                "model",
                registered_model_name=name
            )

            # Log artifacts (feature importance, etc.)
            if artifacts:
                for name, data in artifacts.items():
                    mlflow.log_artifact(data, name)

    def load_production_model(self, name: str):
        """Load production version of model."""
        model_uri = f"models:/{name}/Production"
        return mlflow.sklearn.load_model(model_uri)

# Usage
registry = ModelRegistry()

# Train model
model = train_duration_predictor(training_data)

# Evaluate
metrics = {
    "mae": mean_absolute_error(y_test, predictions),
    "r2": r2_score(y_test, predictions),
}

# Register
registry.register_model(
    model,
    name="activity_duration_predictor",
    metrics=metrics,
    artifacts={"feature_importance": importance_plot}
)

# Promote to production (manual step)
# mlflow.transition_model_version_stage(...)
```

### 7.2 ⚠️ HIGH: Fehlende Feature Store

**Problem:** Features werden jedes Mal neu berechnet.

**Fix: Feature Store mit Caching**
```python
# ml/feature_store.py
from dataclasses import dataclass
from typing import Dict, List
import pandas as pd

@dataclass
class FeatureDefinition:
    name: str
    dependencies: List[str]
    ttl_seconds: int
    compute_fn: callable

class FeatureStore:
    """Central feature computation and caching."""

    def __init__(self, cache: CacheService, db: AsyncSession):
        self.cache = cache
        self.db = db
        self.features: Dict[str, FeatureDefinition] = {}

    def register_feature(self, feature: FeatureDefinition):
        """Register a feature computation."""
        self.features[feature.name] = feature

    async def get_features(
        self,
        feature_names: List[str],
        entity_id: int
    ) -> Dict[str, float]:
        """Compute or retrieve features from cache."""
        result = {}

        for name in feature_names:
            cache_key = f"feature:{name}:{entity_id}"

            # Try cache first
            cached = await self.cache.get(cache_key)
            if cached is not None:
                result[name] = cached
                continue

            # Compute feature
            feature_def = self.features[name]
            value = await feature_def.compute_fn(self.db, entity_id)

            # Cache result
            await self.cache.set(cache_key, value, feature_def.ttl_seconds)
            result[name] = value

        return result

# Register features
feature_store = FeatureStore(cache, db)

# Example feature: Average activity duration for user
async def compute_avg_user_activity_duration(db, user_id):
    result = await db.execute(
        select(func.avg(TimeEntryModel.duration_minutes))
        .filter(TimeEntryModel.user_id == user_id)
    )
    return result.scalar() or 0

feature_store.register_feature(FeatureDefinition(
    name="user_avg_activity_duration",
    dependencies=["time_entries"],
    ttl_seconds=3600,  # Cache for 1 hour
    compute_fn=compute_avg_user_activity_duration
))

# Usage in ML pipeline
features = await feature_store.get_features(
    ["user_avg_activity_duration", "order_complexity", "material_hardness"],
    entity_id=user_id
)
prediction = model.predict([list(features.values())])
```

---

## 8. DevOps & Deployment

### 8.1 ⚠️ HIGH: Fehlende CI/CD Pipeline

**Fix: GitHub Actions Workflow**
```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: goldsmith_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install Poetry
        run: curl -sSL https://install.python-poetry.org | python3 -

      - name: Install dependencies
        run: poetry install

      - name: Run linters
        run: |
          poetry run black --check src/
          poetry run isort --check src/
          poetry run pylint src/
          poetry run mypy src/

      - name: Run security checks
        run: poetry run bandit -r src/

      - name: Run tests
        env:
          DATABASE_URL: postgresql://test:test@localhost/goldsmith_test
        run: poetry run pytest --cov=goldsmith_erp --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        working-directory: ./frontend
        run: yarn install

      - name: Run linter
        working-directory: ./frontend
        run: yarn lint

      - name: Run tests
        working-directory: ./frontend
        run: yarn test

      - name: Build
        working-directory: ./frontend
        run: yarn build

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'

  deploy-staging:
    needs: [test-backend, test-frontend, security-scan]
    if: github.ref == 'refs/heads/develop'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        run: |
          # Deploy logic here
          echo "Deploying to staging..."
```

### 8.2 📊 Medium: Fehlende Environment-Specific Configs

**Fix: Multi-Environment Setup**
```python
# core/config.py
from enum import Enum

class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class Settings(BaseSettings):
    ENVIRONMENT: Environment = Environment.DEVELOPMENT

    # Environment-specific overrides
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @property
    def DATABASE_POOL_SIZE(self) -> int:
        return {
            Environment.DEVELOPMENT: 5,
            Environment.STAGING: 10,
            Environment.PRODUCTION: 20,
        }[self.ENVIRONMENT]

    @property
    def REDIS_CACHE_TTL(self) -> int:
        return {
            Environment.DEVELOPMENT: 60,
            Environment.STAGING: 300,
            Environment.PRODUCTION: 600,
        }[self.ENVIRONMENT]

    @property
    def CORS_ORIGINS(self) -> List[str]:
        if self.is_production:
            return ["https://goldsmith-erp.com"]
        return ["http://localhost:3000", "http://localhost:8000"]
```

---

## 9. Testing Strategy

### 9.1 ❌ CRITICAL: Fehlende Tests

**Current:** 0 Tests vorhanden!

**Fix: Comprehensive Test Suite**
```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture
async def db_session():
    """Test database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()

@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return User(
        id=1,
        email="test@example.com",
        role=UserRole.GOLDSMITH,
        is_active=True
    )

# tests/services/test_time_tracking_service.py
@pytest.mark.asyncio
async def test_start_time_entry_success(db_session, mock_user):
    """Test starting time entry successfully."""
    # Arrange
    entry_in = TimeEntryStart(
        order_id=1,
        activity_id=1,
        user_id=mock_user.id,
    )

    # Act
    entry = await TimeTrackingService.start_time_entry(db_session, entry_in)

    # Assert
    assert entry.id is not None
    assert entry.order_id == 1
    assert entry.end_time is None

@pytest.mark.asyncio
async def test_start_time_entry_when_already_running(db_session, mock_user):
    """Test error when user already has running entry."""
    # Arrange
    await create_running_entry(db_session, mock_user.id)

    entry_in = TimeEntryStart(
        order_id=2,
        activity_id=1,
        user_id=mock_user.id,
    )

    # Act & Assert
    with pytest.raises(ValueError, match="already has running entry"):
        await TimeTrackingService.start_time_entry(db_session, entry_in)

# Integration tests
@pytest.mark.asyncio
async def test_time_tracking_full_workflow(client, db_session, auth_headers):
    """Test complete time tracking workflow."""
    # Start tracking
    response = await client.post(
        "/api/v1/time-tracking/start",
        json={"order_id": 1, "activity_id": 1},
        headers=auth_headers
    )
    assert response.status_code == 200
    entry_id = response.json()["id"]

    # Check running entry
    response = await client.get(
        "/api/v1/time-tracking/running",
        headers=auth_headers
    )
    assert response.json()["id"] == entry_id

    # Stop tracking
    response = await client.post(
        f"/api/v1/time-tracking/{entry_id}/stop",
        json={"complexity_rating": 3},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["duration_minutes"] > 0
```

---

## 10. Priority Roadmap

### Phase 1: Critical Fixes (Diese Woche)
```
□ Fix hardcoded SECRET_KEY
□ Implement proper transaction management
□ Fix Redis connection leak
□ Add N+1 query fixes
□ Add input validation
□ Move tokens to HttpOnly cookies
```

### Phase 2: High Priority (Nächste 2 Wochen)
```
□ Implement Repository Pattern
□ Add comprehensive error handling
□ Implement RBAC
□ Add rate limiting
□ Add structured logging
□ Write basic test suite (>70% coverage)
```

### Phase 3: Architecture Improvements (Monat 2)
```
□ Implement caching strategy
□ Add database constraints and indexes
□ Implement soft deletes
□ Add monitoring & tracing
□ Add CI/CD pipeline
□ Frontend: Zustand state management
```

### Phase 4: Advanced Features (Monat 3)
```
□ ML model registry (MLflow)
□ Feature store implementation
□ Advanced observability (Grafana dashboards)
□ Load testing & optimization
□ Security audit
```

---

## 11. Metrics & Success Criteria

### Performance Targets
- API Response Time: p95 < 200ms, p99 < 500ms
- Database Query Time: p95 < 50ms
- Cache Hit Rate: > 80%
- Error Rate: < 0.1%

### Quality Targets
- Test Coverage: > 80%
- Security Score: A+ (Sonar/OWASP)
- Code Quality: A (SonarQube)
- Documentation: 100% API endpoints documented

### Availability Targets
- Uptime: 99.9% (8.76 hours downtime/year)
- RTO (Recovery Time Objective): < 15 minutes
- RPO (Recovery Point Objective): < 5 minutes

---

## 12. Conclusion

**Das System hat eine solide Grundlage, aber signifikante Lücken in:**
1. ❌ Security (Secrets, Auth, Validation)
2. ❌ Error Handling & Transactions
3. ❌ Performance (Caching, N+1, Pooling)
4. ❌ Observability (Logging, Metrics, Tracing)
5. ❌ Testing (0% coverage)

**Quick Wins (1-2 Tage):**
- SECRET_KEY aus Environment
- Redis Connection Context Manager
- Structured Logging
- Health Checks
- Basic Input Validation

**Empfehlung:** Implementiere Phase 1 (Critical Fixes) VOR Phase 5.2 Frontend-Entwicklung. Security und Data Integrity sind wichtiger als neue Features.

---

**Nächste Schritte:**
1. Review dieses Dokument mit dem Team
2. Priorisiere Fixes basierend auf Business Impact
3. Erstelle Tasks in Jira/GitHub Issues
4. Starte mit Critical Fixes (P0)

**Fragen? Lass uns das gemeinsam durchgehen.**

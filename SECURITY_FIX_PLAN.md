# Security Fixes Implementation Plan
**Date**: 2025-11-15
**Priority**: P0 - CRITICAL
**Estimated Total Effort**: 2-3 days

---

## Executive Summary

This document outlines the implementation strategy for fixing 6 critical security vulnerabilities identified in ARCHITECTURE_REVIEW.md. These fixes are **MANDATORY** before production deployment.

**Risk Level**: 🚨 CRITICAL → After fixes: ✅ MEDIUM

---

## Fix Overview

| # | Issue | Severity | Effort | Order |
|---|-------|----------|--------|-------|
| 1 | Hardcoded SECRET_KEY | CRITICAL | 30 min | 1st |
| 2 | Redis Connection Leak | CRITICAL | 1 hour | 2nd |
| 3 | N+1 Query Problems | CRITICAL | 3 hours | 3rd |
| 4 | Transaction Management | CRITICAL | 4 hours | 4th |
| 5 | Input Validation | CRITICAL | 4 hours | 5th |
| 6 | LocalStorage Tokens (XSS) | HIGH | 3 hours | 6th |

**Total Estimated Time**: ~16 hours (2 working days)

---

## Fix #1: SECRET_KEY from Environment

### Current Problem
```python
# src/goldsmith_erp/core/config.py:25
SECRET_KEY: str = "change_this_to_a_secure_random_string"
```

**Risk**:
- Secret is committed in Git → anyone can decode JWT tokens
- All sessions can be hijacked
- Production system is completely compromised

### Solution Strategy

**Step 1**: Create `.env.example` template
```bash
# .env.example
SECRET_KEY=generate_with_openssl_rand_hex_32
DATABASE_URL=postgresql+asyncpg://user:password@localhost/goldsmith_erp
REDIS_URL=redis://localhost:6379/0
```

**Step 2**: Update `.env` (not committed)
```bash
# Generate secure key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
```

**Step 3**: Add validator to config.py
```python
from pydantic import Field, field_validator
import secrets

class Settings(BaseSettings):
    SECRET_KEY: str = Field(
        default="",
        min_length=32,
        description="JWT secret key - MUST be set in production"
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Ensure SECRET_KEY is secure."""
        # Reject common insecure values
        insecure_values = [
            "",
            "change_this_to_a_secure_random_string",
            "secret",
            "secretkey",
            "your-secret-key",
        ]

        if v.lower() in insecure_values:
            # In development, generate temporary key
            if cls.model_config.get("env_file") == ".env.dev":
                return secrets.token_urlsafe(64)

            raise ValueError(
                "SECRET_KEY must be changed from default! "
                "Generate with: python3 -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )

        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")

        return v
```

**Step 4**: Update `.gitignore`
```bash
# Ensure .env is ignored
.env
.env.local
.env.production
```

**Files to modify**:
- `src/goldsmith_erp/core/config.py` - Add validator
- `.env.example` - Create template
- `.gitignore` - Ensure .env ignored
- `README.md` - Add setup instructions

**Testing**:
```bash
# Should fail with insecure key
SECRET_KEY="secret" python -m goldsmith_erp

# Should work with secure key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))") python -m goldsmith_erp
```

---

## Fix #2: Redis Connection Pool Leak

### Current Problem
```python
# src/goldsmith_erp/core/pubsub.py:20-24
async def get_redis_connection() -> redis.Redis:
    """Acquire a Redis client instance from the connection pool."""
    return redis.Redis(connection_pool=_redis_pool)
    # ❌ Connection is NEVER closed!
```

**Risk**:
- Memory leak - connections never released
- Pool exhaustion after ~50 requests (default pool size)
- Server crashes under load

### Solution Strategy

**Step 1**: Implement async context manager
```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import redis.asyncio as redis

@asynccontextmanager
async def get_redis_client() -> AsyncGenerator[redis.Redis, None]:
    """
    Acquire Redis client with automatic cleanup.

    Usage:
        async with get_redis_client() as client:
            await client.set("key", "value")
    """
    client = redis.Redis(connection_pool=_redis_pool)
    try:
        yield client
    finally:
        await client.close()
```

**Step 2**: Update all usage sites
```python
# OLD (WRONG)
async def publish_event(channel: str, message: str) -> None:
    redis_client = await get_redis_connection()
    await redis_client.publish(channel, message)
    # ❌ Never closed!

# NEW (CORRECT)
async def publish_event(channel: str, message: str) -> None:
    """Publish event with automatic connection cleanup."""
    async with get_redis_client() as client:
        await client.publish(channel, message)
    # ✅ Automatically closed!
```

**Step 3**: Update WebSocket manager
```python
# src/goldsmith_erp/core/websocket.py
async def broadcast_message(self, message: str) -> None:
    """Broadcast with proper Redis cleanup."""
    async with get_redis_client() as client:
        await client.publish("order_updates", message)
```

**Files to modify**:
- `src/goldsmith_erp/core/pubsub.py` - Implement context manager
- All files using `get_redis_connection()`:
  - `src/goldsmith_erp/services/order_service.py`
  - `src/goldsmith_erp/core/websocket.py`
  - Any other usage sites

**Testing**:
```python
import asyncio
import psutil

async def test_no_leak():
    """Verify connections are released."""
    process = psutil.Process()
    initial_connections = len(process.connections())

    # Create 100 Redis operations
    for _ in range(100):
        async with get_redis_client() as client:
            await client.ping()

    final_connections = len(process.connections())

    # Should have same number of connections (pool reuse)
    assert final_connections - initial_connections < 5
```

---

## Fix #3: N+1 Query Problems

### Current Problem
```python
# src/goldsmith_erp/services/time_tracking_service.py:125-138
async def get_time_entries_for_order(db: AsyncSession, order_id: int):
    result = await db.execute(
        select(TimeEntryModel)
        .options(
            selectinload(TimeEntryModel.activity),
            selectinload(TimeEntryModel.user),
            # ❌ Missing: order, interruptions, photos!
        )
        .filter(TimeEntryModel.order_id == order_id)
    )
```

**Risk**:
- 100 time entries → 300+ database queries
- Slow API responses (>2 seconds)
- Database CPU spikes

### Solution Strategy

**Step 1**: Add comprehensive eager loading
```python
async def get_time_entries_for_order(
    db: AsyncSession,
    order_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[TimeEntryModel]:
    """Get time entries with complete eager loading (1-2 queries total)."""
    result = await db.execute(
        select(TimeEntryModel)
        .options(
            # Eager load all relationships
            selectinload(TimeEntryModel.activity),
            selectinload(TimeEntryModel.user),
            selectinload(TimeEntryModel.order),           # ✅ Added
            selectinload(TimeEntryModel.interruptions),   # ✅ Added
            selectinload(TimeEntryModel.photos),          # ✅ Added
        )
        .filter(TimeEntryModel.order_id == order_id)
        .order_by(TimeEntryModel.start_time.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
```

**Step 2**: Add query logging to verify
```python
# Test with query logging enabled
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Should see ~2 queries:
# 1. SELECT time_entries WHERE order_id = ?
# 2. SELECT activities, users, orders, etc. WHERE id IN (...)
```

**Step 3**: Fix all other N+1 problems
```python
# order_service.py - get_order with materials
async def get_order(db: AsyncSession, order_id: int):
    result = await db.execute(
        select(OrderModel)
        .options(
            selectinload(OrderModel.materials),   # ✅ Eager load
            selectinload(OrderModel.customer),    # ✅ Eager load
            selectinload(OrderModel.time_entries) # ✅ Eager load
                .selectinload(TimeEntryModel.activity),
        )
        .filter(OrderModel.id == order_id)
    )
    return result.scalar_one_or_none()
```

**Files to modify**:
- `src/goldsmith_erp/services/time_tracking_service.py`
- `src/goldsmith_erp/services/order_service.py`
- `src/goldsmith_erp/services/user_service.py`

**Testing**:
```python
# Enable query logging
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Before fix: 100+ queries
# After fix: 1-3 queries
response = await client.get(f"/api/v1/time-tracking/order/{order_id}")
```

---

## Fix #4: Transaction Management

### Current Problem
```python
# src/goldsmith_erp/services/order_service.py:33-70
async def create_order(db: AsyncSession, order_in: OrderCreate):
    db_order = OrderModel(**order_data)

    # ❌ No transaction - partial commits possible!
    if order_in.materials:
        materials = await db.execute(...)  # Can fail
        db_order.materials = materials

    db.add(db_order)
    await db.commit()  # ❌ Commits even if next step fails

    await publish_event(...)  # ❌ Can fail AFTER commit!
```

**Risk**:
- Data inconsistency (order without materials)
- Events published for failed operations
- No rollback on errors

### Solution Strategy

**Step 1**: Create transaction context manager
```python
# src/goldsmith_erp/core/database.py
from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError

@asynccontextmanager
async def transactional(db: AsyncSession):
    """
    Context manager for transactional operations.

    Automatically commits on success, rolls back on error.

    Usage:
        async with transactional(db):
            db.add(obj1)
            db.add(obj2)
            # Both committed together or both rolled back
    """
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
```

**Step 2**: Wrap all service methods
```python
async def create_order(db: AsyncSession, order_in: OrderCreate) -> OrderModel:
    """Create order with ACID guarantees."""
    try:
        async with transactional(db):
            # 1. Create order
            order_data = order_in.dict(exclude={"materials"})
            db_order = OrderModel(**order_data)

            # 2. Associate materials
            if order_in.materials:
                materials_result = await db.execute(
                    select(Material).filter(Material.id.in_(order_in.materials))
                )
                materials = materials_result.scalars().all()

                # ✅ Validate ALL materials exist
                if len(materials) != len(order_in.materials):
                    missing = set(order_in.materials) - {m.id for m in materials}
                    raise ValueError(f"Materials not found: {missing}")

                db_order.materials = materials

            db.add(db_order)
            await db.flush()  # ✅ Get ID without committing

            # 3. Publish event INSIDE transaction
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "create",
                    "order_id": db_order.id,
                    "status": db_order.status,
                })
            )

        # ✅ Transaction committed successfully
        await db.refresh(db_order)
        return db_order

    except ValueError as e:
        logger.warning(f"Validation error creating order: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Database error creating order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")
```

**Step 3**: Apply to all services
- `order_service.py` - create, update, delete
- `time_tracking_service.py` - start, stop
- `user_service.py` - create, update
- `material_service.py` - create, update, delete

**Files to modify**:
- `src/goldsmith_erp/core/database.py` - Add `transactional()`
- All service files - Wrap operations

**Testing**:
```python
async def test_transaction_rollback():
    """Verify rollback on error."""
    initial_count = await db.scalar(select(func.count(OrderModel.id)))

    # Try to create order with invalid material
    with pytest.raises(HTTPException):
        await create_order(db, OrderCreate(
            title="Test",
            materials=[99999]  # Doesn't exist
        ))

    final_count = await db.scalar(select(func.count(OrderModel.id)))

    # Should not have created order
    assert final_count == initial_count
```

---

## Fix #5: Input Validation

### Current Problem
```python
@router.get("/order/{order_id}/total")
async def get_total_time_for_order(
    order_id: int,  # ❌ Only type check, no validation
    db: AsyncSession = Depends(get_db),
):
    # ❌ What if order_id = -1? Or 999999999999?
    return await get_total_time_for_order(db, order_id)
```

**Risk**:
- SQL injection (mitigated by SQLAlchemy, but still risky)
- Invalid data causing crashes
- No authorization checks

### Solution Strategy

**Step 1**: Create validation models
```python
# src/goldsmith_erp/models/validators.py
from pydantic import BaseModel, Field, validator

class OrderIdParam(BaseModel):
    """Validated order ID parameter."""
    order_id: int = Field(
        ...,
        gt=0,
        le=2147483647,  # Max PostgreSQL int
        description="Order ID must be positive"
    )

class PaginationParams(BaseModel):
    """Standard pagination with limits."""
    skip: int = Field(0, ge=0, description="Offset")
    limit: int = Field(
        50,
        ge=1,
        le=100,  # ✅ Maximum 100 items per request
        description="Items per page"
    )

class TimeEntryIdParam(BaseModel):
    """Validated time entry UUID."""
    entry_id: str = Field(..., min_length=36, max_length=36)

    @validator("entry_id")
    def validate_uuid(cls, v):
        """Ensure valid UUID format."""
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("Invalid UUID format")
        return v
```

**Step 2**: Apply to all endpoints
```python
from fastapi import Depends

@router.get("/order/{order_id}/total")
async def get_total_time_for_order(
    order_id: int = Path(..., gt=0),  # ✅ Validate > 0
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ✅ Auth required
):
    # ✅ Verify order exists
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # ✅ Verify user has access (basic authorization)
    # TODO: Implement proper RBAC in next phase

    return await time_tracking_service.get_total_time_for_order(db, order_id)
```

**Step 3**: Add request size limits
```python
# src/goldsmith_erp/main.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS."""
    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB

    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.MAX_REQUEST_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"}
                )
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware)
```

**Files to modify**:
- Create `src/goldsmith_erp/models/validators.py`
- Update all router files:
  - `api/routers/time_tracking.py`
  - `api/routers/orders.py`
  - `api/routers/users.py`
  - `api/routers/materials.py`
  - `api/routers/activities.py`
- `src/goldsmith_erp/main.py` - Add middleware

**Testing**:
```python
# Should reject negative IDs
response = await client.get("/api/v1/orders/-1")
assert response.status_code == 422

# Should reject huge limits
response = await client.get("/api/v1/orders?limit=10000")
assert response.status_code == 422

# Should reject invalid UUIDs
response = await client.get("/api/v1/time-tracking/invalid-uuid")
assert response.status_code == 422
```

---

## Fix #6: HttpOnly Cookies (XSS Protection)

### Current Problem
```typescript
// frontend/src/api/client.ts:19
const token = localStorage.getItem('access_token');
```

**Risk**:
- XSS attack can steal token via JavaScript
- Token persists across browser sessions
- No CSRF protection

### Solution Strategy

**Step 1**: Update backend to use cookies
```python
# src/goldsmith_erp/api/routers/auth.py
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
        httponly=True,      # ✅ Not accessible via JavaScript
        secure=True,        # ✅ HTTPS only (disable in dev)
        samesite="strict",  # ✅ CSRF protection
        max_age=60 * 60 * 24 * 8,  # 8 days
        path="/",
    )

    # Return success message only
    return {"message": "Login successful", "user": user.dict()}

@router.post("/logout")
async def logout(response: Response):
    """Logout by clearing cookie."""
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logged out"}
```

**Step 2**: Update dependency to read from cookies
```python
# src/goldsmith_erp/core/security.py
from fastapi import Cookie

async def get_current_user(
    access_token: str = Cookie(None, alias="access_token"),  # ✅ Read from cookie
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from cookie token."""
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )

    # ... decode token and get user ...
```

**Step 3**: Update frontend to use credentials
```typescript
// frontend/src/api/client.ts
const apiClient = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,  // ✅ Send cookies with requests
    headers: {
        'Content-Type': 'application/json',
    },
});

// ✅ Remove token interceptor - cookies sent automatically
// No need to manually attach Authorization header
```

**Step 4**: Update AuthContext
```typescript
// frontend/src/contexts/AuthContext.tsx
const login = async (email: string, password: string) => {
    const response = await authApi.login(email, password);

    // ✅ No need to store token - it's in HttpOnly cookie
    setUser(response.user);
    setIsAuthenticated(true);
};

const logout = async () => {
    await authApi.logout();

    // ✅ Cookie cleared by backend
    setUser(null);
    setIsAuthenticated(false);
};
```

**Step 5**: Update CORS for credentials
```python
# src/goldsmith_erp/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        # Add production URLs
    ],
    allow_credentials=True,  # ✅ Required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Files to modify**:
- Backend:
  - `src/goldsmith_erp/api/routers/auth.py` - Cookie handling
  - `src/goldsmith_erp/core/security.py` - Read from cookie
  - `src/goldsmith_erp/main.py` - CORS credentials
- Frontend:
  - `frontend/src/api/client.ts` - Remove localStorage
  - `frontend/src/contexts/AuthContext.tsx` - Remove token storage
  - `frontend/src/api/auth.ts` - Update login/logout

**Testing**:
```python
# Backend test
async def test_login_sets_cookie():
    response = await client.post("/api/v1/auth/login/access-token", data={
        "username": "test@example.com",
        "password": "password"
    })

    assert response.status_code == 200

    # ✅ Cookie should be set
    cookies = response.cookies
    assert "access_token" in cookies

    # ✅ Should have HttpOnly flag
    cookie = cookies["access_token"]
    assert cookie.httponly is True
    assert cookie.secure is True
    assert cookie.samesite == "strict"

# Frontend test - verify no localStorage usage
async def test_no_localstorage_usage():
    await login("test@example.com", "password")

    # ✅ Should NOT be in localStorage
    assert localStorage.getItem("access_token") is None
```

---

## Implementation Order & Checklist

### Day 1 - Morning (4 hours)
- [x] Plan created (this document)
- [ ] Fix #1: SECRET_KEY (30 min)
  - [ ] Update config.py with validator
  - [ ] Create .env.example
  - [ ] Update .gitignore
  - [ ] Test with secure/insecure keys
- [ ] Fix #2: Redis Connection Leak (1 hour)
  - [ ] Implement context manager
  - [ ] Update all usage sites
  - [ ] Test for memory leaks
- [ ] Fix #3: N+1 Queries (2.5 hours)
  - [ ] Add eager loading to time_tracking_service
  - [ ] Add eager loading to order_service
  - [ ] Enable query logging and verify
  - [ ] Performance test (should see 90%+ reduction)

### Day 1 - Afternoon (4 hours)
- [ ] Fix #4: Transaction Management (4 hours)
  - [ ] Create transactional() context manager
  - [ ] Update order_service
  - [ ] Update time_tracking_service
  - [ ] Update user_service
  - [ ] Update material_service
  - [ ] Test rollback scenarios

### Day 2 - Morning (4 hours)
- [ ] Fix #5: Input Validation (4 hours)
  - [ ] Create validators.py
  - [ ] Update time_tracking router
  - [ ] Update orders router
  - [ ] Update users router
  - [ ] Update materials router
  - [ ] Add request size middleware
  - [ ] Test validation errors

### Day 2 - Afternoon (4 hours)
- [ ] Fix #6: HttpOnly Cookies (3 hours)
  - [ ] Update backend auth router
  - [ ] Update security.py dependency
  - [ ] Update CORS configuration
  - [ ] Update frontend API client
  - [ ] Update AuthContext
  - [ ] Remove all localStorage usage
  - [ ] Test login/logout flow
- [ ] Final Testing & Documentation (1 hour)
  - [ ] Run full test suite
  - [ ] Update SECURITY.md
  - [ ] Update README.md
  - [ ] Create migration guide

---

## Verification & Testing

### Security Checklist
After implementation, verify:

- [ ] SECRET_KEY validation works (rejects insecure keys)
- [ ] Redis connections are properly closed (no memory leak)
- [ ] Database queries reduced (N+1 fixed)
- [ ] Transactions rollback on errors
- [ ] Invalid inputs are rejected (400/422 errors)
- [ ] Tokens in HttpOnly cookies (not accessible via JS)
- [ ] CORS allows credentials
- [ ] No localStorage usage for tokens

### Performance Benchmarks
Measure improvements:

```bash
# Before fixes
- API response time: ~2000ms (N+1 queries)
- Memory usage: 500MB → 2GB (Redis leak)
- Queries per request: 100+

# After fixes (targets)
- API response time: <200ms
- Memory usage: stable at 500MB
- Queries per request: 1-3
```

### Security Scan
```bash
# Run security audit
bandit -r src/goldsmith_erp/

# Should have 0 HIGH/MEDIUM issues
```

---

## Rollback Plan

If issues occur during deployment:

1. **SECRET_KEY issue**: Temporarily use old key (accept the risk)
2. **Redis issue**: Revert pubsub.py to old version
3. **N+1 issue**: Remove selectinload() calls
4. **Transaction issue**: Remove transactional() wrapper
5. **Validation issue**: Remove validation, log warnings instead
6. **Cookie issue**: Revert to localStorage (document security risk)

---

## Post-Implementation

### Documentation Updates
- [ ] Update ARCHITECTURE_REVIEW.md (mark issues as fixed)
- [ ] Create SECURITY.md with best practices
- [ ] Update README.md setup instructions
- [ ] Add to CHANGELOG.md

### Monitoring
- [ ] Set up alerts for Redis connection count
- [ ] Monitor API response times
- [ ] Track validation errors
- [ ] Monitor failed login attempts

### Next Phase
After these fixes, proceed to:
1. Backend testing infrastructure (Week 2)
2. Domain-specific features (Week 3-4)
3. Production monitoring (Week 7-8)

---

**Status**: Ready for implementation
**Risk Assessment**: Medium → Low (after fixes)
**Production Ready**: NO → YES (after these fixes + testing)

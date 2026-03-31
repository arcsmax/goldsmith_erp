# Auth & User Service Tests - Detailed Implementation Plan
**Created:** 2025-11-10
**Estimated Time:** 6-8 hours
**Priority:** High (Critical for production security)

---

## Overview

Testing authentication and authorization is critical for security. We need to ensure:
- Passwords are never stored in plain text
- JWT tokens are secure and properly validated
- Permission system works correctly
- Users can't access resources they shouldn't
- Inactive users are properly blocked

---

## Architecture Analysis

### Components to Test

**1. UserService (`services/user_service.py`)**
- User CRUD operations
- Password hashing (never store plain text)
- Soft delete (is_active=False)
- Hard delete (permanent removal)
- User activation/deactivation

**2. Security Functions (`core/security.py`)**
- `get_password_hash()` - Hash passwords with bcrypt
- `verify_password()` - Verify plain password against hash
- `create_access_token()` - Generate JWT tokens with expiration

**3. Authentication (`api/routers/auth.py`)**
- Login endpoint with rate limiting
- Token generation and cookie setting
- Logout (cookie clearing)
- Email/password validation

**4. Authorization (`api/deps.py`)**
- `get_current_user()` - Extract user from JWT token
- `get_current_admin_user()` - Ensure user is admin
- `require_permission()` - Permission-based access control
- `has_permission()` - Check if user has specific permission
- Permission system (15+ permissions across Orders, Customers, Time, Materials, Admin)

---

## Test Plan Structure

### Part 1: UserService Tests (20 tests)

**File:** `tests/unit/test_user_service.py`

#### 1.1 User Creation (5 tests)
- ✅ Create user with valid data
- ✅ Password is hashed (never plain text)
- ✅ Default role is USER
- ✅ Default is_active is True
- ✅ Created_at timestamp is set

**Implementation Details:**
```python
async def test_create_user_password_is_hashed():
    """Test that passwords are NEVER stored in plain text"""
    user_data = UserCreate(
        email="test@example.com",
        password="Test1234",
        first_name="Test",
        last_name="User"
    )
    user = await UserService.create_user(db_session, user_data)

    # Critical security check: password must be hashed
    assert user.hashed_password != "Test1234"
    assert len(user.hashed_password) > 50  # bcrypt hashes are long
    assert user.hashed_password.startswith("$2b$")  # bcrypt identifier
```

#### 1.2 User Retrieval (4 tests)
- ✅ Get user by ID (found/not found)
- ✅ Get user by email (found/not found)
- ✅ List users with pagination
- ✅ Users ordered by created_at DESC

#### 1.3 User Updates (5 tests)
- ✅ Update email, names
- ✅ Update password (gets hashed)
- ✅ Update is_active status
- ✅ Partial update (only changed fields)
- ✅ Non-existent user returns None

**Critical Security Test:**
```python
async def test_update_user_password_is_hashed():
    """Test that password updates are also hashed"""
    user = await UserService.create_user(db_session, user_data)

    update_data = UserUpdate(password="NewPass123")
    updated = await UserService.update_user(db_session, user.id, update_data)

    # New password must be hashed
    assert updated.hashed_password != "NewPass123"
    assert updated.hashed_password != user.hashed_password  # Different hash
```

#### 1.4 User Deletion (4 tests)
- ✅ Soft delete (sets is_active=False)
- ✅ Soft delete preserves user data
- ✅ Hard delete (permanent removal)
- ✅ Activate deactivated user

#### 1.5 User Validation (2 tests)
- ✅ Email format validation
- ✅ Name character validation (only letters, spaces, hyphens, apostrophes)

---

### Part 2: Security & Auth Tests (25 tests)

**File:** `tests/unit/test_auth_security.py`

#### 2.1 Password Hashing (5 tests)
- ✅ `get_password_hash()` produces bcrypt hash
- ✅ Same password produces different hashes (salt)
- ✅ `verify_password()` works with correct password
- ✅ `verify_password()` fails with wrong password
- ✅ Hash format is valid bcrypt ($2b$...)

**Implementation:**
```python
def test_password_hashing():
    """Test password hashing with bcrypt"""
    password = "SecurePass123"
    hashed = get_password_hash(password)

    # Verify bcrypt format
    assert hashed.startswith("$2b$")
    assert len(hashed) >= 59  # bcrypt min length

    # Verify password matches
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

def test_same_password_different_hashes():
    """Test that same password produces different hashes (salt)"""
    password = "Test1234"
    hash1 = get_password_hash(password)
    hash2 = get_password_hash(password)

    # Different hashes due to salt
    assert hash1 != hash2

    # Both verify correctly
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True
```

#### 2.2 JWT Token Creation (8 tests)
- ✅ `create_access_token()` generates valid JWT
- ✅ Token contains user_id in "sub" claim
- ✅ Token has expiration time
- ✅ Token uses HS256 algorithm
- ✅ Token is signed with SECRET_KEY
- ✅ Default expiration is ACCESS_TOKEN_EXPIRE_MINUTES
- ✅ Custom expiration works
- ✅ Token can be decoded and validated

**Implementation:**
```python
def test_create_access_token():
    """Test JWT token creation"""
    user_id = 123
    token = create_access_token(data={"sub": str(user_id)})

    # Decode and verify
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])

    assert payload["sub"] == "123"
    assert "exp" in payload  # Expiration time
    assert payload["exp"] > datetime.utcnow().timestamp()

def test_token_expiration():
    """Test token expiration"""
    token = create_access_token(
        data={"sub": "123"},
        expires_delta=timedelta(minutes=1)
    )

    # Should decode successfully
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "123"

    # Expired token should fail (simulate by decoding with past time)
    # Note: Actual expiration test requires time.sleep() or mocking
```

#### 2.3 Authentication (Login) (7 tests)
- ✅ Login with valid credentials returns token
- ✅ Login with invalid email returns 401
- ✅ Login with invalid password returns 401
- ✅ Login with inactive user returns 400
- ✅ Token is set in HttpOnly cookie
- ✅ Token is also returned in response body
- ✅ Rate limiting blocks excessive login attempts (5/min)

**Implementation:**
```python
async def test_login_success(client, sample_user):
    """Test successful login"""
    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={
            "username": sample_user.email,
            "password": "Test1234"  # Known password from fixture
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify HttpOnly cookie is set
    assert "access_token" in response.cookies

async def test_login_invalid_email(client):
    """Test login with non-existent email"""
    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={
            "username": "nonexistent@example.com",
            "password": "Test1234"
        }
    )

    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]
```

#### 2.4 Token Validation (5 tests)
- ✅ Valid token extracts user correctly
- ✅ Invalid token returns 401
- ✅ Expired token returns 401
- ✅ Token with invalid signature returns 401
- ✅ Token for non-existent user returns 401

---

### Part 3: Authorization & Permissions Tests (15 tests)

**File:** `tests/unit/test_auth_permissions.py`

#### 3.1 get_current_user (5 tests)
- ✅ Extract user from valid JWT token
- ✅ Extract user from HttpOnly cookie
- ✅ Extract user from Authorization header
- ✅ Inactive user raises 400
- ✅ Invalid token raises 401

#### 3.2 get_current_admin_user (3 tests)
- ✅ Admin user passes check
- ✅ Regular USER raises 403
- ✅ Inactive admin raises 400 (checked by get_current_user)

#### 3.3 Permission System (7 tests)
- ✅ Admin has ALL permissions
- ✅ USER has limited permissions (ORDER_VIEW, CUSTOMER_VIEW, etc.)
- ✅ USER doesn't have admin permissions (USER_MANAGE, SYSTEM_CONFIG)
- ✅ `has_permission()` returns True for allowed permissions
- ✅ `has_permission()` returns False for denied permissions
- ✅ Inactive user has NO permissions
- ✅ `require_permission()` dependency blocks unauthorized users

**Implementation:**
```python
def test_admin_has_all_permissions(admin_user):
    """Test that admin has all permissions"""
    for permission in Permission:
        assert has_permission(admin_user, permission) is True

def test_user_has_limited_permissions(sample_user):
    """Test that USER role has limited permissions"""
    # Allowed permissions
    assert has_permission(sample_user, Permission.ORDER_VIEW) is True
    assert has_permission(sample_user, Permission.CUSTOMER_VIEW) is True
    assert has_permission(sample_user, Permission.TIME_TRACK) is True

    # Denied permissions
    assert has_permission(sample_user, Permission.USER_MANAGE) is False
    assert has_permission(sample_user, Permission.SYSTEM_CONFIG) is False
    assert has_permission(sample_user, Permission.ORDER_DELETE) is False

async def test_require_permission_blocks_unauthorized(client, sample_user_token):
    """Test that require_permission blocks users without permission"""
    response = await client.delete(
        f"{settings.API_V1_STR}/users/123",
        headers={"Authorization": f"Bearer {sample_user_token}"}
    )

    assert response.status_code == 403
    assert "Permission denied" in response.json()["detail"]
```

---

## Test Fixtures Required

### New Fixtures (add to `conftest.py`)

```python
@pytest_asyncio.fixture
async def sample_user_password() -> str:
    """Known password for test users"""
    return "Test1234"

@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession, sample_user_password: str) -> User:
    """Create a regular USER for testing"""
    from goldsmith_erp.services.user_service import UserService
    from goldsmith_erp.models.user import UserCreate

    user_data = UserCreate(
        email="testuser@example.com",
        password=sample_user_password,
        first_name="Test",
        last_name="User"
    )
    user = await UserService.create_user(db_session, user_data)
    return user

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, sample_user_password: str) -> User:
    """Create an ADMIN user for testing"""
    from goldsmith_erp.services.user_service import UserService
    from goldsmith_erp.models.user import UserCreate
    from goldsmith_erp.db.models import UserRole

    user_data = UserCreate(
        email="admin@example.com",
        password=sample_user_password,
        first_name="Admin",
        last_name="User"
    )
    user = await UserService.create_user(db_session, user_data)

    # Manually set role to ADMIN
    user.role = UserRole.ADMIN
    await db_session.commit()
    await db_session.refresh(user)

    return user

@pytest_asyncio.fixture
async def sample_user_token(sample_user) -> str:
    """Generate JWT token for sample_user"""
    from goldsmith_erp.core.security import create_access_token
    from datetime import timedelta

    token = create_access_token(
        data={"sub": str(sample_user.id)},
        expires_delta=timedelta(hours=1)
    )
    return token

@pytest_asyncio.fixture
async def admin_user_token(admin_user) -> str:
    """Generate JWT token for admin_user"""
    from goldsmith_erp.core.security import create_access_token
    from datetime import timedelta

    token = create_access_token(
        data={"sub": str(admin_user.id)},
        expires_delta=timedelta(hours=1)
    )
    return token

@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession, sample_user_password: str) -> User:
    """Create an inactive user for testing"""
    from goldsmith_erp.services.user_service import UserService
    from goldsmith_erp.models.user import UserCreate

    user_data = UserCreate(
        email="inactive@example.com",
        password=sample_user_password,
        first_name="Inactive",
        last_name="User"
    )
    user = await UserService.create_user(db_session, user_data)

    # Deactivate
    user.is_active = False
    await db_session.commit()
    await db_session.refresh(user)

    return user
```

---

## Password Validation Tests

**File:** `tests/unit/test_password_validation.py` (5 tests)

- ✅ Password must be at least 8 characters
- ✅ Password must contain at least one number
- ✅ Password must contain at least one letter
- ✅ Password can't exceed 128 characters
- ✅ Valid passwords pass all checks

```python
def test_password_too_short():
    """Test that short passwords fail validation"""
    with pytest.raises(ValueError, match="at least 8 characters"):
        UserCreate(
            email="test@example.com",
            password="Short1",  # Only 6 chars
            first_name="Test",
            last_name="User"
        )

def test_password_no_number():
    """Test that passwords without numbers fail"""
    with pytest.raises(ValueError, match="contain at least one number"):
        UserCreate(
            email="test@example.com",
            password="NoNumbersHere",
            first_name="Test",
            last_name="User"
        )
```

---

## Implementation Order

### Phase 1: UserService Tests (2-3 hours)
1. Create `test_user_service.py`
2. Implement user CRUD tests (20 tests)
3. Focus on password hashing security tests

### Phase 2: Security & Auth Tests (2-3 hours)
1. Create `test_auth_security.py`
2. Implement password hashing tests (5 tests)
3. Implement JWT token tests (8 tests)
4. Implement login/authentication tests (7 tests)
5. Implement token validation tests (5 tests)

### Phase 3: Authorization & Permissions (2 hours)
1. Create `test_auth_permissions.py`
2. Implement current user extraction tests (5 tests)
3. Implement admin checks (3 tests)
4. Implement permission system tests (7 tests)

### Phase 4: Password Validation (30 minutes)
1. Create `test_password_validation.py`
2. Implement password strength tests (5 tests)

### Phase 5: Fixtures & Integration (30 minutes)
1. Add new fixtures to `conftest.py`
2. Run all tests and fix any issues

---

## Success Criteria

**All tests must pass:**
- ✅ 20 UserService tests
- ✅ 25 Security & Auth tests
- ✅ 15 Permission tests
- ✅ 5 Password validation tests

**Total: 65 tests covering authentication and authorization**

**Critical Security Checks:**
- ✅ Passwords NEVER stored in plain text
- ✅ JWT tokens properly signed and validated
- ✅ Inactive users cannot access system
- ✅ Permission checks prevent unauthorized access
- ✅ Rate limiting prevents brute force attacks

---

## Testing Strategy

**Unit Tests:**
- Test individual functions (hash, verify, create_token)
- Mock database sessions where needed
- Fast execution (<1 second per test)

**Integration Tests:**
- Test API endpoints (login, logout)
- Test authentication flow end-to-end
- Use real database with test data

**Security Tests:**
- Password hashing verification
- JWT token tampering detection
- Permission boundary testing
- Inactive user blocking

---

**Estimated Total Time:** 6-8 hours
**Priority:** HIGH - Security is critical for production
**Next Step:** Implement fixtures first, then start with UserService tests

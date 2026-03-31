"""
Unit tests for Authorization & Permissions

Tests cover:
- get_current_user (JWT token extraction and validation)
- get_current_admin_user (admin role verification)
- Permission system (RBAC checks)
- Token validation edge cases
- User activation status
"""
import pytest
from datetime import timedelta
from jose import jwt, JWTError
from fastapi import HTTPException

from goldsmith_erp.api.deps import (
    get_current_user,
    get_current_admin_user,
    has_permission,
    require_permission,
    Permission
)
from goldsmith_erp.core.security import create_access_token, ALGORITHM
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import User, UserRole


@pytest.mark.asyncio
class TestGetCurrentUser:
    """Test get_current_user JWT token extraction"""

    async def test_get_current_user_with_valid_token(self, db_session, sample_user):
        """Test extracting user from valid JWT token"""
        # Create valid token
        token = create_access_token(
            data={"sub": str(sample_user.id)},
            expires_delta=timedelta(hours=1)
        )

        # Extract user (pass db and token as keyword args)
        user = await get_current_user(db=db_session, token=token)

        assert user.id == sample_user.id
        assert user.email == sample_user.email
        assert user.is_active is True

    async def test_get_current_user_with_invalid_token(self, db_session):
        """Test that invalid token raises HTTPException"""
        invalid_token = "this.is.not.a.valid.jwt.token"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=invalid_token)

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in str(exc_info.value.detail)

    async def test_get_current_user_with_expired_token(self, db_session, sample_user):
        """Test that expired token raises HTTPException"""
        # Create expired token (expired 1 hour ago)
        token = create_access_token(
            data={"sub": str(sample_user.id)},
            expires_delta=timedelta(hours=-1)
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=token)

        assert exc_info.value.status_code == 401

    async def test_get_current_user_with_nonexistent_user(self, db_session):
        """Test that token with non-existent user_id raises HTTPException"""
        # Create token with non-existent user ID
        token = create_access_token(
            data={"sub": "999999"},  # User doesn't exist
            expires_delta=timedelta(hours=1)
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=token)

        assert exc_info.value.status_code == 401

    async def test_get_current_user_with_inactive_user(self, db_session, inactive_user):
        """Test that inactive user cannot authenticate"""
        # Create token for inactive user
        token = create_access_token(
            data={"sub": str(inactive_user.id)},
            expires_delta=timedelta(hours=1)
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=token)

        assert exc_info.value.status_code == 400
        assert "Inactive user" in str(exc_info.value.detail)


@pytest.mark.asyncio
class TestGetCurrentAdminUser:
    """Test get_current_admin_user admin verification"""

    async def test_admin_user_passes_admin_check(self, db_session, admin_user):
        """Test that admin user passes admin check"""
        # Should not raise exception (pass user directly)
        user = await get_current_admin_user(current_user=admin_user)

        assert user.id == admin_user.id
        assert user.role == UserRole.ADMIN

    async def test_regular_user_fails_admin_check(self, db_session, sample_user):
        """Test that regular user fails admin check"""
        # Pass user directly
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(current_user=sample_user)

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)

    async def test_inactive_admin_cannot_authenticate(self, db_session, inactive_user):
        """Test that inactive admin cannot authenticate via get_current_user"""
        # Make inactive user an admin
        inactive_user.role = UserRole.ADMIN
        db_session.add(inactive_user)
        await db_session.commit()

        token = create_access_token(
            data={"sub": str(inactive_user.id)},
            expires_delta=timedelta(hours=1)
        )

        # Should fail at get_current_user level (inactive check)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=token)

        assert exc_info.value.status_code == 400
        assert "Inactive user" in str(exc_info.value.detail)


@pytest.mark.asyncio
class TestPermissionSystem:
    """Test RBAC permission system"""

    def test_admin_has_all_permissions(self, admin_user):
        """Test that admin has all permissions"""
        # Admin should have every permission
        for permission in Permission:
            assert has_permission(admin_user, permission) is True

    def test_user_has_limited_permissions(self, sample_user):
        """Test that USER role has limited permissions"""
        # Allowed permissions (view permissions)
        assert has_permission(sample_user, Permission.ORDER_VIEW) is True
        assert has_permission(sample_user, Permission.CUSTOMER_VIEW) is True
        assert has_permission(sample_user, Permission.MATERIAL_VIEW) is True

        # Denied permissions (management/admin permissions)
        assert has_permission(sample_user, Permission.USER_MANAGE) is False
        assert has_permission(sample_user, Permission.SYSTEM_CONFIG) is False
        assert has_permission(sample_user, Permission.ORDER_DELETE) is False

    def test_user_can_create_orders(self, sample_user):
        """Test that regular users can create orders"""
        assert has_permission(sample_user, Permission.ORDER_CREATE) is True

    def test_user_can_edit_orders(self, sample_user):
        """Test that regular users can edit orders"""
        assert has_permission(sample_user, Permission.ORDER_EDIT) is True

    def test_user_cannot_delete_orders(self, sample_user):
        """Test that regular users cannot delete orders"""
        assert has_permission(sample_user, Permission.ORDER_DELETE) is False

    def test_user_cannot_manage_users(self, sample_user):
        """Test that regular users cannot manage users"""
        assert has_permission(sample_user, Permission.USER_MANAGE) is False

    async def test_require_permission_passes_with_permission(self, admin_user):
        """Test require_permission allows access when user has permission"""
        # require_permission is a factory, so call it to get the checker
        checker = require_permission(Permission.ORDER_DELETE)
        # Call the checker with admin user (should not raise)
        result = await checker(current_user=admin_user)
        assert result.id == admin_user.id

        # Test other permissions
        checker2 = require_permission(Permission.USER_MANAGE)
        result2 = await checker2(current_user=admin_user)
        assert result2.id == admin_user.id

    async def test_require_permission_raises_without_permission(self, sample_user):
        """Test require_permission denies access when user lacks permission"""
        # require_permission is a factory
        checker = require_permission(Permission.USER_MANAGE)

        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=sample_user)

        assert exc_info.value.status_code == 403
        assert "permission" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
class TestTokenEdgeCases:
    """Test edge cases in token validation"""

    async def test_token_without_sub_claim(self, db_session):
        """Test that token without 'sub' claim raises HTTPException"""
        # Create token without 'sub' claim
        token = create_access_token(
            data={"email": "test@example.com"},  # No 'sub'!
            expires_delta=timedelta(hours=1)
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=token)

        assert exc_info.value.status_code == 401

    async def test_token_with_wrong_signature(self, db_session, sample_user):
        """Test that token with wrong signature fails validation"""
        # Create token with wrong key
        wrong_token = jwt.encode(
            {"sub": str(sample_user.id), "exp": 9999999999},
            "wrong-secret-key",
            algorithm=ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=wrong_token)

        assert exc_info.value.status_code == 401

    async def test_token_with_invalid_user_id_format(self, db_session):
        """Test that token with invalid user_id format raises HTTPException"""
        # Create token with non-numeric user ID
        token = create_access_token(
            data={"sub": "not-a-number"},
            expires_delta=timedelta(hours=1)
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=token)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
class TestUserActivation:
    """Test user activation status checks"""

    async def test_active_user_can_authenticate(self, db_session, sample_user):
        """Test that active user can authenticate"""
        token = create_access_token(
            data={"sub": str(sample_user.id)},
            expires_delta=timedelta(hours=1)
        )

        user = await get_current_user(db=db_session, token=token)

        assert user.id == sample_user.id
        assert user.is_active is True

    async def test_deactivated_user_cannot_authenticate(self, db_session, sample_user):
        """Test that deactivating user blocks authentication"""
        # Deactivate user
        sample_user.is_active = False
        db_session.add(sample_user)
        await db_session.commit()

        token = create_access_token(
            data={"sub": str(sample_user.id)},
            expires_delta=timedelta(hours=1)
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=db_session, token=token)

        assert exc_info.value.status_code == 400
        assert "Inactive user" in str(exc_info.value.detail)

    async def test_reactivated_user_can_authenticate(self, db_session, inactive_user):
        """Test that reactivating user restores authentication"""
        # Reactivate user
        inactive_user.is_active = True
        db_session.add(inactive_user)
        await db_session.commit()

        token = create_access_token(
            data={"sub": str(inactive_user.id)},
            expires_delta=timedelta(hours=1)
        )

        user = await get_current_user(db=db_session, token=token)

        assert user.id == inactive_user.id
        assert user.is_active is True

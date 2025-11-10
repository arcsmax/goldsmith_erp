"""
Unit tests for UserService

Tests cover:
- User creation with password hashing
- User retrieval (by ID, email, listing)
- User updates (including password changes)
- User deletion (soft and hard delete)
- User activation/deactivation
- Password security validation
- Name validation
"""
import pytest
from sqlalchemy import select

from goldsmith_erp.services.user_service import UserService
from goldsmith_erp.models.user import UserCreate, UserUpdate
from goldsmith_erp.db.models import User, UserRole
from goldsmith_erp.core.security import verify_password


@pytest.mark.asyncio
class TestUserCreation:
    """Test user creation with security validation"""

    async def test_create_user_success(self, db_session):
        """Test successful user creation"""
        user_data = UserCreate(
            email="newuser@example.com",
            password="SecurePass123",
            first_name="John",
            last_name="Doe"
        )

        user = await UserService.create_user(db_session, user_data)

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.is_active is True
        assert user.role == UserRole.USER  # Default role
        assert user.created_at is not None

    async def test_create_user_password_is_hashed(self, db_session):
        """CRITICAL SECURITY TEST: Passwords must NEVER be stored in plain text"""
        plain_password = "MySecretPass123"
        user_data = UserCreate(
            email="secure@example.com",
            password=plain_password,
            first_name="Secure",
            last_name="User"
        )

        user = await UserService.create_user(db_session, user_data)

        # Password must be hashed, not plain text
        assert user.hashed_password != plain_password
        # bcrypt hashes are long (usually 59-60 chars)
        assert len(user.hashed_password) > 50
        # bcrypt identifier
        assert user.hashed_password.startswith("$2b$")
        # Verify the password works
        assert verify_password(plain_password, user.hashed_password) is True

    async def test_create_user_default_role_is_user(self, db_session):
        """Test that new users default to USER role"""
        user_data = UserCreate(
            email="regular@example.com",
            password="Pass1234",
            first_name="Regular",
            last_name="User"
        )

        user = await UserService.create_user(db_session, user_data)

        assert user.role == UserRole.USER

    async def test_create_user_default_is_active_true(self, db_session):
        """Test that new users are active by default"""
        user_data = UserCreate(
            email="active@example.com",
            password="Pass1234",
            first_name="Active",
            last_name="User"
        )

        user = await UserService.create_user(db_session, user_data)

        assert user.is_active is True

    async def test_create_user_with_german_characters(self, db_session):
        """Test that German characters in names are supported"""
        user_data = UserCreate(
            email="deutsch@example.com",
            password="Pass1234",
            first_name="Jürgen",
            last_name="Müller-Schmidt"
        )

        user = await UserService.create_user(db_session, user_data)

        assert user.first_name == "Jürgen"
        assert user.last_name == "Müller-Schmidt"


@pytest.mark.asyncio
class TestUserRetrieval:
    """Test user retrieval operations"""

    async def test_get_user_by_id_success(self, db_session, sample_user):
        """Test getting user by ID"""
        user = await UserService.get_user_by_id(db_session, sample_user.id)

        assert user is not None
        assert user.id == sample_user.id
        assert user.email == sample_user.email

    async def test_get_user_by_id_not_found(self, db_session):
        """Test getting non-existent user returns None"""
        user = await UserService.get_user_by_id(db_session, 99999)

        assert user is None

    async def test_get_user_by_email_success(self, db_session, sample_user):
        """Test getting user by email"""
        user = await UserService.get_user_by_email(db_session, sample_user.email)

        assert user is not None
        assert user.id == sample_user.id
        assert user.email == sample_user.email

    async def test_get_user_by_email_not_found(self, db_session):
        """Test getting user by non-existent email returns None"""
        user = await UserService.get_user_by_email(db_session, "nonexistent@example.com")

        assert user is None

    async def test_get_users_all(self, db_session, sample_user, admin_user):
        """Test getting all users"""
        users = await UserService.get_users(db_session)

        assert len(users) >= 2
        user_emails = [u.email for u in users]
        assert sample_user.email in user_emails
        assert admin_user.email in user_emails

    async def test_get_users_pagination(self, db_session):
        """Test user pagination"""
        # Create 5 users
        for i in range(5):
            user_data = UserCreate(
                email=f"user{i}@example.com",
                password="Pass1234",
                first_name=f"User{i}",
                last_name="Test"
            )
            await UserService.create_user(db_session, user_data)

        # Get first 2
        page1 = await UserService.get_users(db_session, skip=0, limit=2)
        assert len(page1) == 2

        # Get next 2
        page2 = await UserService.get_users(db_session, skip=2, limit=2)
        assert len(page2) == 2

        # Ensure different users
        assert page1[0].id != page2[0].id

    async def test_get_users_ordered_by_created_at_desc(self, db_session):
        """Test that users are returned newest first"""
        # Create 3 users
        user_ids = []
        for i in range(3):
            user_data = UserCreate(
                email=f"ordered{i}@example.com",
                password="Pass1234",
                first_name=f"Ordered{i}",
                last_name="Test"
            )
            user = await UserService.create_user(db_session, user_data)
            user_ids.append(user.id)

        # Get all users
        users = await UserService.get_users(db_session, limit=10)

        # Newest should be first
        assert users[0].created_at >= users[-1].created_at


@pytest.mark.asyncio
class TestUserUpdate:
    """Test user update operations"""

    async def test_update_user_email(self, db_session, sample_user):
        """Test updating user email"""
        update_data = UserUpdate(email="newemail@example.com")

        updated = await UserService.update_user(db_session, sample_user.id, update_data)

        assert updated.email == "newemail@example.com"

    async def test_update_user_names(self, db_session, sample_user):
        """Test updating user names"""
        update_data = UserUpdate(
            first_name="NewFirst",
            last_name="NewLast"
        )

        updated = await UserService.update_user(db_session, sample_user.id, update_data)

        assert updated.first_name == "NewFirst"
        assert updated.last_name == "NewLast"

    async def test_update_user_password_is_hashed(self, db_session, sample_user):
        """CRITICAL SECURITY TEST: Password updates must also be hashed"""
        new_password = "NewSecurePass456"
        update_data = UserUpdate(password=new_password)

        original_hash = sample_user.hashed_password
        updated = await UserService.update_user(db_session, sample_user.id, update_data)

        # New password must be hashed
        assert updated.hashed_password != new_password
        assert updated.hashed_password != original_hash  # Different hash
        assert len(updated.hashed_password) > 50
        assert updated.hashed_password.startswith("$2b$")

        # Verify new password works
        assert verify_password(new_password, updated.hashed_password) is True
        # Old password should not work
        assert verify_password("testpassword123", updated.hashed_password) is False

    async def test_update_user_is_active(self, db_session, sample_user):
        """Test updating user active status"""
        update_data = UserUpdate(is_active=False)

        updated = await UserService.update_user(db_session, sample_user.id, update_data)

        assert updated.is_active is False

    async def test_update_user_partial_update(self, db_session, sample_user):
        """Test partial update (only changed fields)"""
        original_email = sample_user.email
        original_first_name = sample_user.first_name

        update_data = UserUpdate(last_name="OnlyLastNameChanged")

        updated = await UserService.update_user(db_session, sample_user.id, update_data)

        # Changed field
        assert updated.last_name == "OnlyLastNameChanged"
        # Unchanged fields
        assert updated.email == original_email
        assert updated.first_name == original_first_name

    async def test_update_non_existent_user(self, db_session):
        """Test updating non-existent user returns None"""
        update_data = UserUpdate(first_name="New Name")

        result = await UserService.update_user(db_session, 99999, update_data)

        assert result is None


@pytest.mark.asyncio
class TestUserDeletion:
    """Test user deletion operations"""

    async def test_soft_delete_user(self, db_session, sample_user):
        """Test soft delete (sets is_active=False)"""
        user_id = sample_user.id

        result = await UserService.delete_user(db_session, user_id)

        assert result["success"] is True
        assert "deactivated" in result["message"].lower()

        # User still exists but is inactive
        user = await UserService.get_user_by_id(db_session, user_id)
        assert user is not None
        assert user.is_active is False

    async def test_soft_delete_preserves_user_data(self, db_session, sample_user):
        """Test that soft delete preserves all user data"""
        user_id = sample_user.id
        original_email = sample_user.email
        original_name = sample_user.first_name

        await UserService.delete_user(db_session, user_id)

        # User data should be preserved
        user = await UserService.get_user_by_id(db_session, user_id)
        assert user.email == original_email
        assert user.first_name == original_name

    async def test_soft_delete_non_existent_user(self, db_session):
        """Test soft deleting non-existent user"""
        result = await UserService.delete_user(db_session, 99999)

        assert result["success"] is False
        assert "not found" in result["message"].lower()

    async def test_hard_delete_user(self, db_session, sample_user):
        """Test hard delete (permanent removal)"""
        user_id = sample_user.id

        result = await UserService.hard_delete_user(db_session, user_id)

        assert result["success"] is True
        assert "permanently deleted" in result["message"].lower()

        # User should not exist
        user = await UserService.get_user_by_id(db_session, user_id)
        assert user is None

    async def test_hard_delete_non_existent_user(self, db_session):
        """Test hard deleting non-existent user"""
        result = await UserService.hard_delete_user(db_session, 99999)

        assert result["success"] is False
        assert "not found" in result["message"].lower()

    async def test_activate_deactivated_user(self, db_session, inactive_user):
        """Test activating a deactivated user"""
        assert inactive_user.is_active is False

        activated = await UserService.activate_user(db_session, inactive_user.id)

        assert activated is not None
        assert activated.is_active is True

    async def test_activate_non_existent_user(self, db_session):
        """Test activating non-existent user returns None"""
        result = await UserService.activate_user(db_session, 99999)

        assert result is None


@pytest.mark.asyncio
class TestUserValidation:
    """Test user input validation"""

    async def test_invalid_email_format_fails(self, db_session):
        """Test that invalid email format fails validation"""
        with pytest.raises(ValueError):
            user_data = UserCreate(
                email="not-an-email",  # Invalid format
                password="Pass1234",
                first_name="Test",
                last_name="User"
            )

    async def test_name_with_invalid_characters_fails(self, db_session):
        """Test that names with invalid characters fail validation"""
        with pytest.raises(ValueError, match="invalid characters"):
            user_data = UserCreate(
                email="test@example.com",
                password="Pass1234",
                first_name="John123",  # Numbers not allowed
                last_name="Doe"
            )

    async def test_name_with_special_chars_fails(self, db_session):
        """Test that names with special characters fail validation"""
        with pytest.raises(ValueError, match="invalid characters"):
            user_data = UserCreate(
                email="test@example.com",
                password="Pass1234",
                first_name="John",
                last_name="Doe@Email"  # @ not allowed
            )

    async def test_empty_name_after_strip_fails(self, db_session):
        """Test that empty names (after stripping) fail validation"""
        # Note: This test depends on Pydantic min_length validation
        with pytest.raises(ValueError):
            user_data = UserCreate(
                email="test@example.com",
                password="Pass1234",
                first_name="   ",  # Only whitespace
                last_name="Doe"
            )


@pytest.mark.asyncio
class TestPasswordSecurity:
    """Test password security requirements"""

    async def test_password_too_short_fails(self, db_session):
        """Test that short passwords fail validation"""
        with pytest.raises(ValueError, match="at least 8 characters"):
            user_data = UserCreate(
                email="test@example.com",
                password="Short1",  # Only 6 chars
                first_name="Test",
                last_name="User"
            )

    async def test_password_no_number_fails(self, db_session):
        """Test that passwords without numbers fail"""
        with pytest.raises(ValueError, match="contain at least one number"):
            user_data = UserCreate(
                email="test@example.com",
                password="NoNumbersHere",
                first_name="Test",
                last_name="User"
            )

    async def test_password_no_letter_fails(self, db_session):
        """Test that passwords without letters fail"""
        with pytest.raises(ValueError, match="contain at least one letter"):
            user_data = UserCreate(
                email="test@example.com",
                password="12345678",  # Only numbers
                first_name="Test",
                last_name="User"
            )

    async def test_password_too_long_fails(self, db_session):
        """Test that very long passwords fail validation"""
        with pytest.raises(ValueError, match="at most 128 characters"):
            user_data = UserCreate(
                email="test@example.com",
                password="a" * 129 + "1",  # 130 chars
                first_name="Test",
                last_name="User"
            )

    async def test_valid_passwords_pass(self, db_session):
        """Test that valid passwords pass all checks"""
        valid_passwords = [
            "Password123",
            "SecurePass1",
            "MyP@ssw0rd",
            "Test1234567890",
        ]

        for i, password in enumerate(valid_passwords):
            user_data = UserCreate(
                email=f"valid{i}@example.com",
                password=password,
                first_name="Valid",
                last_name="User"
            )
            user = await UserService.create_user(db_session, user_data)
            assert user.id is not None
            assert verify_password(password, user.hashed_password) is True

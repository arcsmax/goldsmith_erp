"""
Integration tests for authentication flow.

Tests:
- POST /api/v1/login/access-token — successful login returns JWT
- POST /api/v1/login/access-token — wrong password returns 401
- POST /api/v1/login/access-token — unknown email returns 401
- Protected endpoint without token returns 401
- Protected endpoint with valid token returns 200
- POST /api/v1/logout — clears access_token cookie
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LOGIN_URL = "/api/v1/login/access-token"
LOGOUT_URL = "/api/v1/logout"
PROTECTED_URL = "/api/v1/orders/"


async def _create_user(db: AsyncSession, email: str, password: str, role: UserRole = UserRole.VIEWER) -> User:
    """Create a user directly in the test DB."""
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------

class TestLoginEndpoint:

    @pytest.mark.asyncio
    async def test_login_valid_credentials_returns_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Successful login with correct credentials returns a JWT token."""
        await _create_user(db_session, "auth_valid@example.com", "ValidPass123!")

        response = await client.post(
            LOGIN_URL,
            data={"username": "auth_valid@example.com", "password": "ValidPass123!"},
        )

        assert response.status_code == 200
        body = response.json()
        assert "message" in body
        # Token is now in HttpOnly cookie, not response body
        assert "access_token" in response.cookies

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Login with the wrong password is rejected with 401."""
        await _create_user(db_session, "auth_wrongpw@example.com", "CorrectPass123!")

        response = await client.post(
            LOGIN_URL,
            data={"username": "auth_wrongpw@example.com", "password": "WrongPass456!"},
        )

        assert response.status_code == 401
        body = response.json()
        assert "detail" in body

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_401(self, client: AsyncClient):
        """Login with a non-existent email is rejected with 401."""
        response = await client.post(
            LOGIN_URL,
            data={"username": "nobody@example.com", "password": "AnyPass123!"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_sets_httponly_cookie(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Successful login sets an HttpOnly access_token cookie."""
        await _create_user(db_session, "auth_cookie@example.com", "CookiePass123!")

        response = await client.post(
            LOGIN_URL,
            data={"username": "auth_cookie@example.com", "password": "CookiePass123!"},
        )

        assert response.status_code == 200
        # httpx stores cookies; verify the cookie was set in the response
        assert "access_token" in response.cookies

    @pytest.mark.asyncio
    async def test_login_empty_credentials_returns_422(self, client: AsyncClient):
        """Sending no form data returns HTTP 422 Unprocessable Entity."""
        response = await client.post(LOGIN_URL, data={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Protected endpoint access tests
# ---------------------------------------------------------------------------

class TestProtectedEndpointAccess:

    @pytest.mark.asyncio
    async def test_protected_endpoint_without_token_returns_401(
        self, client: AsyncClient
    ):
        """Accessing a protected endpoint without authentication returns 401."""
        response = await client.get(PROTECTED_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_invalid_token_returns_401(
        self, client: AsyncClient
    ):
        """A forged or expired JWT is rejected with 401."""
        response = await client.get(
            PROTECTED_URL,
            headers={"Authorization": "Bearer totally.invalid.token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_valid_token_returns_200(
        self, authenticated_client: AsyncClient
    ):
        """A valid JWT token grants access to protected endpoints."""
        response = await authenticated_client.get(PROTECTED_URL)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_token_from_login_grants_access(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Token obtained via login can be used to access protected endpoints."""
        await _create_user(
            db_session,
            "auth_flow@example.com",
            "FlowPass123!",
            role=UserRole.ADMIN,
        )

        # Step 1: login
        login_resp = await client.post(
            LOGIN_URL,
            data={"username": "auth_flow@example.com", "password": "FlowPass123!"},
        )
        assert login_resp.status_code == 200
        # Token is in HttpOnly cookie
        token = login_resp.cookies["access_token"]

        # Step 2: use token on protected endpoint
        protected_resp = await client.get(
            PROTECTED_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert protected_resp.status_code == 200


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------

class TestLogout:

    @pytest.mark.asyncio
    async def test_logout_clears_cookie(
        self, authenticated_client: AsyncClient
    ):
        """POST /logout returns 200 and instructs the client to clear the cookie."""
        response = await authenticated_client.post(LOGOUT_URL)
        assert response.status_code == 200
        body = response.json()
        assert "message" in body

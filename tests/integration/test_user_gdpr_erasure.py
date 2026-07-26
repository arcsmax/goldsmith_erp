"""Router-level integration tests for GDPR Art. 17 employee erasure.

Covers ``POST /api/v1/users/{id}/gdpr-erase`` (production-readiness finding
1.4): the ADMIN-only endpoint that wires the previously-orphaned
``UserService.anonymize_user`` into the HTTP surface.

What is pinned here (router level — the service contract itself is unit-
tested in ``tests/unit/test_user_anonymization.py``):

  * ADMIN can erase → 200, non-PII response shape, the target row is
    actually anonymised in the DB, a ``gdpr_requests`` audit row and a
    ``customer_audit_logs`` ``gdpr_erased`` row are written, and the
    denormalised ``customer_audit_logs.user_email`` plaintext copy is
    scrubbed to the ``deleted_user_{hmac}`` sentinel.
  * Non-ADMIN (VIEWER, GOLDSMITH) → 403; unauthenticated → 401.
  * Last-admin protection surfaces as a 409 (a 4xx, never a 500).
  * An erased user can no longer log in.
  * Unknown id → 404; a second call is an idempotent 200 no-op.

The test DB is the per-test SQLite session from ``tests/integration/
conftest.py`` (tables truncated after every test), so each test starts
with an empty ``users`` table — a fixture-created ADMIN is therefore the
only active admin unless the test adds another.
"""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from goldsmith_erp.core.security import create_access_token, get_password_hash
from goldsmith_erp.db.models import CustomerAuditLog, GDPRRequest
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.models import UserRole
from goldsmith_erp.services.user_service import _compute_tracking_hmac

pytestmark = pytest.mark.asyncio


def _erase_url(user_id: int) -> str:
    return f"/api/v1/users/{user_id}/gdpr-erase"


LOGIN_URL = "/api/v1/login/access-token"


def _bearer(user: UserModel) -> dict:
    """Bearer-token headers for an arbitrary user (mirrors conftest helper)."""
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(hours=1),
    )
    return {"Authorization": f"Bearer {token}"}


async def _make_user(
    db_session,
    *,
    role: UserRole,
    password: str = "TargetPass123!",
    email: str | None = None,
) -> UserModel:
    """Create and persist a user with a known plaintext password."""
    user = UserModel(
        email=email
        or f"target_{role.value}_{datetime.utcnow().timestamp()}@example.com",
        hashed_password=get_password_hash(password),
        first_name="Target",
        last_name="Person",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Happy path — ADMIN erases another user
# ---------------------------------------------------------------------------


class TestAdminCanErase:
    async def test_admin_erase_returns_200_and_non_pii_shape(
        self, client: AsyncClient, db_session, admin_user, admin_auth_headers
    ):
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)
        original_email = target.email

        resp = await client.post(
            _erase_url(target.id),
            headers=admin_auth_headers,
            json={"reason": "employee-left-workshop"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Response shape — non-PII summary only.
        assert body["user_id"] == target.id
        assert body["sentinel_user_id"] != target.id
        assert len(body["tracking_hmac"]) == 16
        assert body["already_anonymized"] is False
        assert body["gdpr_request_id"] > 0
        assert isinstance(body["fk_updates"], dict)
        assert isinstance(body["audit_email_scrubs"], int)
        assert "detail" in body
        # No PII may leak into the response.
        assert original_email not in resp.text
        assert "Target" not in resp.text

    async def test_admin_erase_anonymizes_row_in_db(
        self, client: AsyncClient, db_session, admin_user, admin_auth_headers
    ):
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)
        original_email = target.email
        target_id = target.id

        resp = await client.post(
            _erase_url(target_id), headers=admin_auth_headers, json={}
        )
        assert resp.status_code == 200, resp.text

        # Raw SQL to bypass the identity map (anonymize_user uses UPDATE stmts).
        row = (
            await db_session.execute(
                text(
                    "SELECT email, hashed_password, is_deleted, is_active, "
                    "first_name FROM users WHERE id = :id"
                ),
                {"id": target_id},
            )
        ).first()
        email, hashed_password, is_deleted, is_active, first_name = row

        assert email != original_email
        assert email == f"deleted_{target_id}@anonymized.local"
        assert hashed_password == "!"  # bcrypt-invalid — cannot authenticate
        assert bool(is_deleted) is True
        assert bool(is_active) is False
        assert first_name == "<deleted>"

    async def test_admin_erase_writes_audit_rows(
        self, client: AsyncClient, db_session, admin_user, admin_auth_headers
    ):
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)
        target_id = target.id

        resp = await client.post(
            _erase_url(target_id), headers=admin_auth_headers, json={"reason": "audit"}
        )
        assert resp.status_code == 200, resp.text

        # GDPRRequest row (the primary Art. 17 audit record).
        gdpr_rows = (
            (
                await db_session.execute(
                    select(GDPRRequest).filter(
                        GDPRRequest.request_type == "erasure_user"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(gdpr_rows) == 1
        assert gdpr_rows[0].status == "completed"

        # CustomerAuditLog "gdpr_erased" row (the regulated-resource action row).
        audit_rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog)
                    .filter(CustomerAuditLog.action == "gdpr_erased")
                    .filter(CustomerAuditLog.entity == "user")
                    .filter(CustomerAuditLog.entity_id == target_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) == 1
        audit = audit_rows[0]
        # Actor referenced by id; subject e-mail never stored on this row.
        assert audit.user_id == admin_user.id
        assert audit.user_email is None
        assert audit.details["legal_basis"].startswith("GDPR Article 17")

    async def test_erase_scrubs_customer_audit_log_user_email(
        self, client: AsyncClient, db_session, admin_user, admin_auth_headers
    ):
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)
        target_id = target.id
        original_email = target.email

        # Seed a pre-existing audit row that carries the target's plaintext
        # e-mail (the denormalised copy finding 1.4 is about).
        seeded = CustomerAuditLog(
            customer_id=None,
            action="accessed",
            entity="customer",
            entity_id=123,
            user_id=target_id,
            user_email=original_email,
            timestamp=datetime.utcnow(),
        )
        db_session.add(seeded)
        await db_session.commit()
        seeded_id = seeded.id

        resp = await client.post(
            _erase_url(target_id), headers=admin_auth_headers, json={}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["audit_email_scrubs"] >= 1

        scrubbed_email = (
            await db_session.execute(
                text("SELECT user_email FROM customer_audit_logs WHERE id = :id"),
                {"id": seeded_id},
            )
        ).scalar_one()

        expected_hmac = _compute_tracking_hmac(target_id)
        assert scrubbed_email == f"deleted_user_{expected_hmac}"
        assert scrubbed_email != original_email

        # The plaintext e-mail must not survive anywhere in that table.
        remaining = (
            await db_session.execute(
                text(
                    "SELECT COUNT(*) FROM customer_audit_logs "
                    "WHERE user_email = :email"
                ),
                {"email": original_email},
            )
        ).scalar_one()
        assert remaining == 0


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestErasureAuthorization:
    async def test_viewer_forbidden(
        self, client: AsyncClient, db_session, viewer_auth_headers
    ):
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)
        resp = await client.post(
            _erase_url(target.id), headers=viewer_auth_headers, json={}
        )
        assert resp.status_code == 403, resp.text

    async def test_goldsmith_forbidden(
        self, client: AsyncClient, db_session, goldsmith_auth_headers
    ):
        target = await _make_user(db_session, role=UserRole.VIEWER)
        resp = await client.post(
            _erase_url(target.id), headers=goldsmith_auth_headers, json={}
        )
        assert resp.status_code == 403, resp.text

    async def test_unauthenticated_401(self, client: AsyncClient, db_session):
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)
        resp = await client.post(_erase_url(target.id), json={})
        assert resp.status_code == 401, resp.text

    async def test_forbidden_role_does_not_anonymize(
        self, client: AsyncClient, db_session, viewer_auth_headers
    ):
        """A 403 must be a true no-op — the target row stays intact."""
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)
        original_email = target.email

        resp = await client.post(
            _erase_url(target.id), headers=viewer_auth_headers, json={}
        )
        assert resp.status_code == 403

        row = (
            await db_session.execute(
                text("SELECT email, is_deleted FROM users WHERE id = :id"),
                {"id": target.id},
            )
        ).first()
        assert row[0] == original_email
        assert bool(row[1]) is False


# ---------------------------------------------------------------------------
# Guard rails + edge cases
# ---------------------------------------------------------------------------


class TestErasureGuardRails:
    async def test_last_admin_returns_409_not_500(
        self, client: AsyncClient, db_session
    ):
        """The lone active ADMIN erasing itself is a 409 — never a 500."""
        lone_admin = await _make_user(db_session, role=UserRole.ADMIN)

        resp = await client.post(
            _erase_url(lone_admin.id),
            headers=_bearer(lone_admin),
            json={"reason": "self-erase-last-admin"},
        )

        assert resp.status_code == 409, resp.text
        assert resp.status_code != 500
        # Row must be untouched.
        row = (
            await db_session.execute(
                text("SELECT is_deleted FROM users WHERE id = :id"),
                {"id": lone_admin.id},
            )
        ).scalar_one()
        assert bool(row) is False

    async def test_admin_can_self_erase_when_another_admin_exists(
        self, client: AsyncClient, db_session, admin_user, admin_auth_headers
    ):
        """Self-erasure is allowed when the workshop keeps another admin."""
        second_admin = await _make_user(db_session, role=UserRole.ADMIN)

        resp = await client.post(
            _erase_url(second_admin.id),
            headers=_bearer(second_admin),  # second admin erases itself
            json={},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["already_anonymized"] is False

    async def test_unknown_user_returns_404(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.post(
            _erase_url(999_999), headers=admin_auth_headers, json={}
        )
        assert resp.status_code == 404, resp.text

    async def test_second_call_is_idempotent_200(
        self, client: AsyncClient, db_session, admin_user, admin_auth_headers
    ):
        target = await _make_user(db_session, role=UserRole.GOLDSMITH)

        first = await client.post(
            _erase_url(target.id), headers=admin_auth_headers, json={}
        )
        assert first.status_code == 200
        assert first.json()["already_anonymized"] is False

        second = await client.post(
            _erase_url(target.id), headers=admin_auth_headers, json={}
        )
        assert second.status_code == 200, second.text
        assert second.json()["already_anonymized"] is True
        assert second.json()["tracking_hmac"] == first.json()["tracking_hmac"]


# ---------------------------------------------------------------------------
# Post-erasure: the subject can no longer authenticate
# ---------------------------------------------------------------------------


class TestErasedUserCannotLogin:
    async def test_erased_user_cannot_login(
        self, client: AsyncClient, db_session, admin_user, admin_auth_headers
    ):
        password = "KnownPass123!"
        target = await _make_user(
            db_session, role=UserRole.GOLDSMITH, password=password
        )
        original_email = target.email

        # Sanity: the credentials work before erasure.
        pre = await client.post(
            LOGIN_URL, data={"username": original_email, "password": password}
        )
        assert pre.status_code == 200, pre.text

        # The successful login above set an HttpOnly access_token cookie for
        # the target on the shared client; clear it so the erase call below
        # authenticates purely via the ADMIN Bearer header (the cookie would
        # otherwise take precedence and the erase would 403 as the target).
        client.cookies.clear()

        # Erase (by the separate fixture admin — no last-admin conflict).
        erase = await client.post(
            _erase_url(target.id), headers=admin_auth_headers, json={}
        )
        assert erase.status_code == 200, erase.text

        # The original credentials must now be rejected.
        post = await client.post(
            LOGIN_URL, data={"username": original_email, "password": password}
        )
        assert post.status_code == 401, post.text

"""
Unit tests for ActivityService.

Covers the V1.3 estimator Task 1 addition: ``Activity.hourly_rate``
(per-activity labor rate) persists correctly through the update path, with
NULL staying NULL — the shop-default rate fallback itself lives in
``CostCalculationService`` (see test_cost_calculation_service.py).

Also covers the Task 1 follow-up fix: the ``GET /activities/`` and
``GET /activities/{id}`` router handlers must project ``hourly_rate`` out
of the response for non-financial roles (VIEWER), since
``Permission.ACTIVITY_VIEW`` is granted to VIEWER too but ``hourly_rate``
is financial data (CLAUDE.md: pricing visible only to ADMIN/GOLDSMITH).
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from goldsmith_erp.api.routers.activities import get_activity, list_activities
from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.db.models import User, UserRole
from goldsmith_erp.models.activity import ActivityCreate, ActivityUpdate
from goldsmith_erp.services.activity_service import ActivityService


@pytest_asyncio.fixture
async def viewer_user(db_session) -> User:
    """A VIEWER-role user — must never see financial fields."""
    user = User(
        email=f"viewer_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("viewerpassword123"),
        first_name="View",
        last_name="Only",
        role=UserRole.VIEWER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def test_activity_model_has_hourly_rate_column():
    """Migration round-trip fallback (no local Postgres/alembic in this env):
    assert the mapped column exists, mirroring what ``Base.metadata.create_all``
    produces for the SQLite test DB (see tests/conftest.py's session-scoped
    ``create_tables`` fixture)."""
    columns = {c.name for c in ActivityModel.__table__.columns}
    assert "hourly_rate" in columns


@pytest.mark.asyncio
class TestActivityHourlyRate:
    """Task 1 (V1.3 estimator) — per-activity hourly_rate persistence."""

    async def test_create_activity_defaults_hourly_rate_to_none(self, db_session):
        """ActivityCreate has no hourly_rate field — new activities start unset."""
        activity_in = ActivityCreate(name="Loeten", category="fabrication")
        activity = await ActivityService.create_activity(db_session, activity_in)

        assert activity.hourly_rate is None

    async def test_update_activity_persists_hourly_rate(self, db_session):
        """Updating an activity with hourly_rate=90.00 persists it to the DB."""
        activity_in = ActivityCreate(name="Fassen", category="fabrication")
        activity = await ActivityService.create_activity(db_session, activity_in)

        updated = await ActivityService.update_activity(
            db_session, activity.id, ActivityUpdate(hourly_rate=Decimal("90.00"))
        )

        assert updated is not None
        assert updated.hourly_rate == Decimal("90.00")

        # Re-fetch independently — confirms it was actually persisted, not
        # just reflected on the in-memory object returned above.
        refetched = await ActivityService.get_activity(db_session, activity.id)
        assert refetched is not None
        assert refetched.hourly_rate == Decimal("90.00")

    async def test_update_activity_hourly_rate_none_stays_none(self, db_session):
        """Explicitly setting hourly_rate=None persists NULL (shop-default fallback)."""
        activity_in = ActivityCreate(name="Polieren", category="fabrication")
        activity = await ActivityService.create_activity(db_session, activity_in)

        # First set a rate...
        await ActivityService.update_activity(
            db_session, activity.id, ActivityUpdate(hourly_rate=Decimal("100.00"))
        )
        # ...then explicitly clear it back to None.
        cleared = await ActivityService.update_activity(
            db_session, activity.id, ActivityUpdate(hourly_rate=None)
        )

        assert cleared is not None
        assert cleared.hourly_rate is None

    async def test_update_activity_omitting_hourly_rate_leaves_it_untouched(
        self, db_session
    ):
        """Omitting the field entirely (exclude_unset semantics) must not reset it."""
        activity_in = ActivityCreate(name="Schleifen", category="fabrication")
        activity = await ActivityService.create_activity(db_session, activity_in)

        await ActivityService.update_activity(
            db_session, activity.id, ActivityUpdate(hourly_rate=Decimal("65.00"))
        )

        # Update a different field only — hourly_rate is not mentioned at all.
        updated = await ActivityService.update_activity(
            db_session, activity.id, ActivityUpdate(color="#112233")
        )

        assert updated is not None
        assert updated.hourly_rate == Decimal("65.00")
        assert updated.color == "#112233"

    async def test_update_activity_rejects_negative_hourly_rate(self, db_session):
        """Pydantic validation (ge=0) rejects a negative rate before it ever
        reaches the service/DB layer."""
        with pytest.raises(ValueError):
            ActivityUpdate(hourly_rate=Decimal("-1.00"))


@pytest.mark.asyncio
class TestActivityHourlyRateProjection:
    """Financial-data exposure fix — ``hourly_rate`` must be projected out
    of ``GET /activities/`` and ``GET /activities/{id}`` for VIEWER, while
    ADMIN/GOLDSMITH still see the real value. Router functions are called
    directly (as ``@require_permission`` calls them internally via kwargs),
    mirroring the direct-service-call pattern used in test_scanner_service.py
    for role-filtered projections.
    """

    async def _priced_activity(self, db_session) -> ActivityModel:
        """An activity with a real, non-default hourly_rate set."""
        activity_in = ActivityCreate(name="Giessen", category="fabrication")
        activity = await ActivityService.create_activity(db_session, activity_in)
        updated = await ActivityService.update_activity(
            db_session, activity.id, ActivityUpdate(hourly_rate=Decimal("120.00"))
        )
        assert updated is not None
        return updated

    async def test_list_activities_viewer_gets_hourly_rate_none(
        self, db_session, viewer_user
    ):
        await self._priced_activity(db_session)

        # category filter bypasses the Redis default-list cache path so this
        # test exercises the real ORM objects, not a cached serialisation.
        results = await list_activities(
            category="fabrication",
            sort_by_usage=False,
            skip=0,
            limit=100,
            db=db_session,
            current_user=viewer_user,
        )

        assert len(results) >= 1
        assert all(r.hourly_rate is None for r in results)

    async def test_list_activities_admin_gets_real_hourly_rate(
        self, db_session, admin_user
    ):
        priced = await self._priced_activity(db_session)

        results = await list_activities(
            category="fabrication",
            sort_by_usage=False,
            skip=0,
            limit=100,
            db=db_session,
            current_user=admin_user,
        )

        match = next(r for r in results if r.id == priced.id)
        assert match.hourly_rate == Decimal("120.00")

    async def test_list_activities_goldsmith_gets_real_hourly_rate(
        self, db_session, sample_user
    ):
        """``sample_user`` (conftest.py) is GOLDSMITH-role."""
        priced = await self._priced_activity(db_session)

        results = await list_activities(
            category="fabrication",
            sort_by_usage=False,
            skip=0,
            limit=100,
            db=db_session,
            current_user=sample_user,
        )

        match = next(r for r in results if r.id == priced.id)
        assert match.hourly_rate == Decimal("120.00")

    async def test_get_activity_viewer_gets_hourly_rate_none(
        self, db_session, viewer_user
    ):
        priced = await self._priced_activity(db_session)

        result = await get_activity(
            activity_id=priced.id, db=db_session, current_user=viewer_user
        )

        assert result.hourly_rate is None

    async def test_get_activity_admin_gets_real_hourly_rate(
        self, db_session, admin_user
    ):
        priced = await self._priced_activity(db_session)

        result = await get_activity(
            activity_id=priced.id, db=db_session, current_user=admin_user
        )

        assert result.hourly_rate == Decimal("120.00")

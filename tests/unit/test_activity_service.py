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

import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from goldsmith_erp.api.routers.activities import (
    get_activity,
    get_most_used_activities,
    list_activities,
)
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

    async def test_most_used_activities_viewer_gets_hourly_rate_none(
        self, db_session, viewer_user
    ):
        """Defect A — ``GET /activities/most-used`` is also gated only by
        ``ACTIVITY_VIEW`` (VIEWER holds it) and returned ``ActivityRead``
        without ever routing through ``_project_activity``."""
        priced = await self._priced_activity(db_session)
        # usage_count starts at 0 for every activity — bump it so this one
        # is guaranteed to surface in the (small) most-used result set.
        await ActivityService.increment_usage(db_session, priced.id)

        results = await get_most_used_activities(
            limit=10, db=db_session, current_user=viewer_user
        )

        assert len(results) >= 1
        assert all(r.hourly_rate is None for r in results)

    async def test_most_used_activities_admin_gets_real_hourly_rate(
        self, db_session, admin_user
    ):
        priced = await self._priced_activity(db_session)
        await ActivityService.increment_usage(db_session, priced.id)

        results = await get_most_used_activities(
            limit=10, db=db_session, current_user=admin_user
        )

        match = next(r for r in results if r.id == priced.id)
        assert match.hourly_rate == Decimal("120.00")

    async def test_most_used_activities_goldsmith_gets_real_hourly_rate(
        self, db_session, sample_user
    ):
        """``sample_user`` (conftest.py) is GOLDSMITH-role."""
        priced = await self._priced_activity(db_session)
        await ActivityService.increment_usage(db_session, priced.id)

        results = await get_most_used_activities(
            limit=10, db=db_session, current_user=sample_user
        )

        match = next(r for r in results if r.id == priced.id)
        assert match.hourly_rate == Decimal("120.00")


async def _simulate_redis_cache_hit(key, ttl, fetch_fn, serialise, deserialise):
    """Stand in for ``get_cached`` under a real Redis HIT, without needing a
    live Redis instance.

    Runs the exact same serialise → deserialise round trip ``get_cached``
    would perform when writing to and then reading back from Redis (see
    ``core/cache.py``): fetch once, serialise the result to the JSON string
    that would be stored, then deserialise it, and return *that* — never the
    original in-memory ORM objects. This is what actually exercises whether
    the cached payload shape round-trips ``hourly_rate`` correctly, which a
    cache-bypass mock (see test_materials_list_zero_price.py) would not
    catch.
    """
    value = await fetch_fn()
    return deserialise(serialise(value))


@pytest.mark.asyncio
class TestActivitiesCacheHourlyRateRoundTrip:
    """Defect B — the Redis-backed ``activities:list`` cache serialised
    activities WITHOUT ``hourly_rate``, so even ADMIN/GOLDSMITH got
    ``hourly_rate: null`` back on a cache HIT (only a cache MISS, which
    re-reads real ORM objects, ever returned the true value). Verifies the
    fixed ``_serialise`` closure in ``ActivityService.get_activities`` round
    -trips ``hourly_rate`` through a simulated cache hit, and that role
    projection (applied by the router, post-cache) still filters it out for
    VIEWER even when the data came from cache.
    """

    async def _priced_activity(self, db_session) -> ActivityModel:
        activity_in = ActivityCreate(name="Schmelzen", category="fabrication")
        activity = await ActivityService.create_activity(db_session, activity_in)
        updated = await ActivityService.update_activity(
            db_session, activity.id, ActivityUpdate(hourly_rate=Decimal("77.50"))
        )
        assert updated is not None
        return updated

    async def test_admin_served_from_cache_still_gets_real_hourly_rate(
        self, db_session, admin_user
    ):
        priced = await self._priced_activity(db_session)

        with patch(
            "goldsmith_erp.services.activity_service.get_cached",
            new=AsyncMock(side_effect=_simulate_redis_cache_hit),
        ):
            results = await list_activities(
                category=None,
                sort_by_usage=False,
                skip=0,
                limit=100,
                db=db_session,
                current_user=admin_user,
            )

        match = next(r for r in results if r.id == priced.id)
        assert match.hourly_rate == Decimal("77.50")

    async def test_viewer_served_from_cache_still_gets_hourly_rate_none(
        self, db_session, viewer_user
    ):
        await self._priced_activity(db_session)

        with patch(
            "goldsmith_erp.services.activity_service.get_cached",
            new=AsyncMock(side_effect=_simulate_redis_cache_hit),
        ):
            results = await list_activities(
                category=None,
                sort_by_usage=False,
                skip=0,
                limit=100,
                db=db_session,
                current_user=viewer_user,
            )

        assert len(results) >= 1
        assert all(r.hourly_rate is None for r in results)

    async def test_serialised_cache_payload_contains_hourly_rate_field(
        self, db_session
    ):
        """Direct check on the wire format: the JSON actually stored in
        Redis must contain the field at all — this is the literal bug
        (the old ``_serialise`` dict never had a ``hourly_rate`` key, so no
        role's projection could ever recover it from a cache hit)."""
        priced = await self._priced_activity(db_session)
        captured: dict = {}

        async def _capture_and_hit(key, ttl, fetch_fn, serialise, deserialise):
            value = await fetch_fn()
            raw_json = serialise(value)
            captured["raw"] = json.loads(raw_json)
            return deserialise(raw_json)

        with patch(
            "goldsmith_erp.services.activity_service.get_cached",
            new=AsyncMock(side_effect=_capture_and_hit),
        ):
            await ActivityService.get_activities(db_session)

        entry = next(a for a in captured["raw"] if a["id"] == priced.id)
        assert "hourly_rate" in entry
        assert entry["hourly_rate"] == "77.50"

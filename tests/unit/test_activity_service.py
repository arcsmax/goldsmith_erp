"""
Unit tests for ActivityService.

Covers the V1.3 estimator Task 1 addition: ``Activity.hourly_rate``
(per-activity labor rate) persists correctly through the update path, with
NULL staying NULL — the shop-default rate fallback itself lives in
``CostCalculationService`` (see test_cost_calculation_service.py).
"""
import pytest
from decimal import Decimal

from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.models.activity import ActivityCreate, ActivityUpdate
from goldsmith_erp.services.activity_service import ActivityService


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

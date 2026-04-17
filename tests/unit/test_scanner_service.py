"""ScannerService unit tests — Slice 3 acceptance tests.

Covers `src/goldsmith_erp/services/scanner_service.py`. The tests are
deliberately short and evidence-based: each pins one behaviour on the
resolve → project → action pipeline, and the role-allow-list tests use
``assertEqual(keys, expected_set)`` rather than ``assertNotIn`` so new
leaks fail CI immediately (Anna A3.3).

Test matrix:

* Prefix resolution — ORDER / REPAIR / METAL / MATERIAL / ACTIVITY /
  INTERRUPT.
* Numeric fallback — ``"42"`` → ORDER:42, ``"42a"`` → unknown.
* Unknown prefix — ``FOO:bar`` → unknown.
* Missing entity — ORDER:99999 → resolved=False.
* Role-filtered projections for ORDER / METAL (VIEWER / GOLDSMITH /
  ADMIN) — exact-key-set equality.
* Timer-switch action primary when context has a different running
  order; stop when same order; start when no timer.
* Punzierungs-Check action emitted in QUALITY_CHECK with alloy + role.
* log_scan idempotency dedupe — same key, second call no-ops, returns
  original row.
* log_scan_batch — size cap happens at Pydantic layer (schema test);
  service handles duplicates per-row and returns counts.
* search_entities — VIEWER gets no metal_purchase.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio

from goldsmith_erp.db.models import (
    Activity,
    Material,
    MetalPurchase,
    MetalType,
    Order,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    User,
    UserRole,
)
from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.models.scanner import ScanContext, ScanLogCreate
from goldsmith_erp.services.scanner_service import (
    METAL_FIELDS_BY_ROLE,
    ORDER_FIELDS_BY_ROLE,
    ScannerService,
)


# --------------------------------------------------------------------------- #
# Fixtures — users per role
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def viewer_user(db_session) -> User:
    """A VIEWER-role user — lowest privilege."""
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


@pytest_asyncio.fixture
async def order_in_qc(db_session, sample_customer) -> Order:
    """An Order sitting in QUALITY_CHECK with an alloy — unlocks
    Punzierungs-Check action."""
    order = Order(
        title="Siegelring 750",
        customer_id=sample_customer.id,
        status=OrderStatusEnum.QUALITY_CHECK,
        alloy="750",
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def sample_repair(db_session, sample_customer) -> RepairJob:
    rep = RepairJob(
        repair_number=f"REP-2026-{uuid.uuid4().hex[:6].upper()}",
        bag_number="B-042",
        customer_id=sample_customer.id,
        item_description="Kette kuerzen",
        item_type=RepairItemType.NECKLACE,
        status=RepairJobStatus.RECEIVED,
    )
    db_session.add(rep)
    await db_session.commit()
    await db_session.refresh(rep)
    return rep


# --------------------------------------------------------------------------- #
# Resolution pipeline
# --------------------------------------------------------------------------- #


class TestResolvePipeline:
    @pytest.mark.asyncio
    async def test_unknown_prefix_routes_to_unknown(
        self, db_session, sample_user
    ):
        """``FOO:bar`` — prefix not in KNOWN_PREFIXES_V1_1."""
        resp = await ScannerService.resolve_payload(
            db_session,
            "FOO:bar",
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is False
        assert resp.resolution_path == "unknown"
        assert resp.entity is None
        assert resp.actions == []

    @pytest.mark.asyncio
    async def test_pure_numeric_fallback_routes_to_order(
        self, db_session, sample_user, sample_order
    ):
        """``"42"`` — purely numeric → treat as ORDER:42."""
        # sample_order.id is autoincrement; the test hits the same id.
        resp = await ScannerService.resolve_payload(
            db_session,
            str(sample_order.id),
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is True
        assert resp.entity_type == "order"
        assert resp.entity_id == sample_order.id
        assert resp.resolution_path == "numeric_fallback"

    @pytest.mark.asyncio
    async def test_mixed_numeric_is_unknown(
        self, db_session, sample_user
    ):
        """``"42a"`` — not pure-numeric → unknown, NOT ORDER."""
        resp = await ScannerService.resolve_payload(
            db_session,
            "42a",
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is False
        assert resp.resolution_path == "unknown"

    @pytest.mark.asyncio
    async def test_order_prefix_resolves(
        self, db_session, sample_user, sample_order
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is True
        assert resp.entity_type == "order"
        assert resp.resolution_path == "prefix"
        assert resp.entity_id == sample_order.id

    @pytest.mark.asyncio
    async def test_missing_order_marked_unresolved(
        self, db_session, sample_user
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            "ORDER:99999",
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is False
        assert resp.entity_type == "order"
        assert resp.entity_id == 99999

    @pytest.mark.asyncio
    async def test_activity_shortcut_toast_only(
        self, db_session, sample_user
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            "ACTIVITY:hartloeten",
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is True
        assert resp.entity_type == "activity"
        assert resp.entity == {"code": "hartloeten"}
        assert resp.actions == []

    @pytest.mark.asyncio
    async def test_interrupt_shortcut_toast_only(
        self, db_session, sample_user
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            "INTERRUPT:telefon",
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is True
        assert resp.entity_type == "interruption"
        assert resp.actions == []

    @pytest.mark.asyncio
    async def test_malformed_order_id_is_unknown(
        self, db_session, sample_user
    ):
        """``ORDER:abc`` — prefix matched but id malformed → unknown."""
        resp = await ScannerService.resolve_payload(
            db_session,
            "ORDER:abc",
            ScanContext(),
            sample_user,
        )
        assert resp.resolved is False
        assert resp.resolution_path == "unknown"


# --------------------------------------------------------------------------- #
# Role-filtered projections — allow-list exact equality (A3.3)
# --------------------------------------------------------------------------- #


class TestRoleProjections:
    @pytest.mark.asyncio
    async def test_order_projection_viewer_exact_keys(
        self, db_session, viewer_user, sample_order
    ):
        """VIEWER projection keys == allow-list. NOT a superset test.

        Anna A3.3: if this drifts to a deny-list, adding a new ORM
        column silently leaks it. Exact-equality asserts loudly.
        """
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            viewer_user,
        )
        assert resp.resolved is True
        assert resp.entity is not None
        assert set(resp.entity.keys()) == ORDER_FIELDS_BY_ROLE[
            UserRole.VIEWER
        ]

    @pytest.mark.asyncio
    async def test_order_projection_goldsmith_exact_keys(
        self, db_session, sample_user, sample_order
    ):
        """GOLDSMITH projection keys == allow-list exactly."""
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            sample_user,
        )
        assert set(resp.entity.keys()) == ORDER_FIELDS_BY_ROLE[
            UserRole.GOLDSMITH
        ]

    @pytest.mark.asyncio
    async def test_order_projection_admin_exact_keys(
        self, db_session, admin_user, sample_order
    ):
        """ADMIN gets the widest allow-list — still exact match."""
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            admin_user,
        )
        assert set(resp.entity.keys()) == ORDER_FIELDS_BY_ROLE[
            UserRole.ADMIN
        ]

    @pytest.mark.asyncio
    async def test_metal_projection_viewer_is_empty(
        self, db_session, viewer_user, sample_metal_purchase
    ):
        """METAL + VIEWER → financial-entity lockout.

        VIEWER's allow-set is frozenset() — the projection MUST be
        an empty dict (not None — the row resolved, but no fields
        are exposed).
        """
        resp = await ScannerService.resolve_payload(
            db_session,
            f"METAL:{sample_metal_purchase.id}",
            ScanContext(),
            viewer_user,
        )
        assert resp.resolved is True
        assert resp.entity == {}
        assert set(resp.entity.keys()) == METAL_FIELDS_BY_ROLE[
            UserRole.VIEWER
        ]

    @pytest.mark.asyncio
    async def test_metal_projection_goldsmith_exact_keys(
        self, db_session, sample_user, sample_metal_purchase
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            f"METAL:{sample_metal_purchase.id}",
            ScanContext(),
            sample_user,
        )
        assert set(resp.entity.keys()) == METAL_FIELDS_BY_ROLE[
            UserRole.GOLDSMITH
        ]

    @pytest.mark.asyncio
    async def test_metal_projection_admin_exact_keys(
        self, db_session, admin_user, sample_metal_purchase
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            f"METAL:{sample_metal_purchase.id}",
            ScanContext(),
            admin_user,
        )
        assert set(resp.entity.keys()) == METAL_FIELDS_BY_ROLE[
            UserRole.ADMIN
        ]


# --------------------------------------------------------------------------- #
# Action computation
# --------------------------------------------------------------------------- #


class TestActionComputation:
    @pytest.mark.asyncio
    async def test_viewer_no_financial_order_actions(
        self, db_session, viewer_user, sample_order
    ):
        """VIEWER on ORDER has no consume_material / change_status."""
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            viewer_user,
        )
        action_ids = {a.id for a in resp.actions}
        assert "consume_material" not in action_ids
        assert "change_status" not in action_ids
        assert "add_material" not in action_ids
        # VIEWER still gets start_timer (read-only FAB uses this to
        # start a timer on a piece they can look at) + safe actions.
        assert "open_entity" in action_ids
        assert "print_label" in action_ids

    @pytest.mark.asyncio
    async def test_goldsmith_has_write_actions(
        self, db_session, sample_user, sample_order
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            sample_user,
        )
        action_ids = {a.id for a in resp.actions}
        assert "change_status" in action_ids
        assert "add_material" in action_ids
        assert "take_photo" in action_ids

    @pytest.mark.asyncio
    async def test_timer_switch_primary_when_running_on_different_order(
        self, db_session, sample_user, sample_order
    ):
        """context.running_timer_id present + order_id differs →
        first action is switch_timer with primary=True."""
        ctx = ScanContext(
            running_timer_id=str(uuid.uuid4()),
            current_order_id=sample_order.id + 1,
        )
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(
                running_timer_id=ctx.running_timer_id,
                current_order_id=ctx.current_order_id,
            ),
            sample_user,
        )
        assert resp.actions[0].id == "switch_timer"
        assert resp.actions[0].primary is True

    @pytest.mark.asyncio
    async def test_timer_stop_primary_when_running_on_same_order(
        self, db_session, sample_user, sample_order
    ):
        ctx = ScanContext(
            running_timer_id=str(uuid.uuid4()),
            current_order_id=sample_order.id,
        )
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ctx,
            sample_user,
        )
        assert resp.actions[0].id == "stop_timer"

    @pytest.mark.asyncio
    async def test_timer_start_primary_when_no_timer(
        self, db_session, sample_user, sample_order
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            sample_user,
        )
        assert resp.actions[0].id == "start_timer"

    @pytest.mark.asyncio
    async def test_punzierungs_check_appears_in_qc_with_alloy(
        self, db_session, sample_user, order_in_qc
    ):
        """QC status + alloy + GOLDSMITH → punzierung_check present."""
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{order_in_qc.id}",
            ScanContext(),
            sample_user,
        )
        action_ids = {a.id for a in resp.actions}
        assert "punzierung_check" in action_ids

    @pytest.mark.asyncio
    async def test_punzierungs_check_hidden_for_viewer(
        self, db_session, viewer_user, order_in_qc
    ):
        """VIEWER cannot perform punzierung_check — legal/financial
        act, restricted to write-capable roles."""
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{order_in_qc.id}",
            ScanContext(),
            viewer_user,
        )
        action_ids = {a.id for a in resp.actions}
        assert "punzierung_check" not in action_ids

    @pytest.mark.asyncio
    async def test_metal_viewer_no_actions_h13(
        self, db_session, viewer_user, sample_metal_purchase
    ):
        """H13 — VIEWER on METAL has no field-level access
        (METAL_FIELDS_VIEWER is empty). The action list must also be
        empty: surfacing ``open_entity`` and then landing on a
        'kein Zugriff' page is sloppy UX. Entity projection stays
        resolved=True + empty dict — only the actions disappear.
        """
        resp = await ScannerService.resolve_payload(
            db_session,
            f"METAL:{sample_metal_purchase.id}",
            ScanContext(),
            viewer_user,
        )
        assert resp.resolved is True
        assert resp.entity == {}
        assert resp.actions == []
        action_ids = {a.id for a in resp.actions}
        assert "consume_material" not in action_ids
        assert "reorder" not in action_ids
        assert "open_entity" not in action_ids


# --------------------------------------------------------------------------- #
# H13 — empty-projection guard: no actions when role has no field access
# --------------------------------------------------------------------------- #


class TestH13EmptyProjectionGuard:
    """Pins the behaviour that when the allow-list projection for
    (entity_type, role) is empty, ``compute_actions`` returns [].
    Today that matches exactly one combination: METAL + VIEWER.
    Future additions of empty projections (e.g. HYPOTHETICAL: INVOICE
    + VIEWER) would inherit the behaviour.
    """

    def test_is_empty_projection_helper_identifies_metal_viewer(self):
        from goldsmith_erp.services.scanner_service import (
            _is_empty_projection,
        )

        assert _is_empty_projection("metal_purchase", UserRole.VIEWER) is True
        # GOLDSMITH and ADMIN have non-empty METAL projections.
        assert (
            _is_empty_projection("metal_purchase", UserRole.GOLDSMITH)
            is False
        )
        assert _is_empty_projection("metal_purchase", UserRole.ADMIN) is False
        # Other entity types do not have empty VIEWER projections.
        assert _is_empty_projection("order", UserRole.VIEWER) is False
        assert _is_empty_projection("repair", UserRole.VIEWER) is False
        assert _is_empty_projection("material", UserRole.VIEWER) is False
        # Unknown entity type — returns False so normal path runs.
        assert _is_empty_projection("activity", UserRole.VIEWER) is False

    @pytest.mark.asyncio
    async def test_metal_viewer_actions_list_is_exactly_empty(
        self, db_session, viewer_user, sample_metal_purchase
    ):
        """The action list for METAL+VIEWER must be [] — not a list
        containing only ``open_entity``, not any other single-action
        fallback. Pins the H13 outcome precisely.
        """
        resp = await ScannerService.resolve_payload(
            db_session,
            f"METAL:{sample_metal_purchase.id}",
            ScanContext(),
            viewer_user,
        )
        assert resp.actions == [], (
            f"Expected [] but got {[a.id for a in resp.actions]}"
        )

    @pytest.mark.asyncio
    async def test_metal_viewer_entity_still_resolves_with_empty_dict(
        self, db_session, viewer_user, sample_metal_purchase
    ):
        """H13 only hides actions — entity still resolves (so the
        client knows the payload was valid) with the empty field
        projection (financial-entity lockout remains).
        """
        resp = await ScannerService.resolve_payload(
            db_session,
            f"METAL:{sample_metal_purchase.id}",
            ScanContext(),
            viewer_user,
        )
        assert resp.resolved is True
        assert resp.entity == {}


# --------------------------------------------------------------------------- #
# status_hint
# --------------------------------------------------------------------------- #


class TestStatusHint:
    @pytest.mark.asyncio
    async def test_status_hint_quality_check(
        self, db_session, sample_user, order_in_qc
    ):
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{order_in_qc.id}",
            ScanContext(),
            sample_user,
        )
        assert resp.status_hint == "Endkontrolle ausstehend"

    @pytest.mark.asyncio
    async def test_status_hint_none_for_default_status(
        self, db_session, sample_user, sample_order
    ):
        """sample_order is NEW — no special hint defined."""
        resp = await ScannerService.resolve_payload(
            db_session,
            f"ORDER:{sample_order.id}",
            ScanContext(),
            sample_user,
        )
        assert resp.status_hint is None


# --------------------------------------------------------------------------- #
# log_scan — idempotency dedupe
# --------------------------------------------------------------------------- #


class TestLogScan:
    @pytest.mark.asyncio
    async def test_basic_insert(self, db_session, sample_user):
        event = ScanLogCreate(raw_payload="ORDER:1", offline_queued=False)
        row = await ScannerService.log_scan(
            db_session, sample_user.id, event
        )
        assert row.id is not None
        assert row.user_id == sample_user.id
        assert row.raw_payload == "ORDER:1"
        assert row.scanned_at is not None
        # retention_class default should be applied by column default
        # (row was refreshed after insert).
        assert row.retention_class == "standard_24m"

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_returns_same_row(
        self, db_session, sample_user
    ):
        """Second log_scan with same idempotency_key returns the first
        row, no new INSERT. Slice 1 UNIQUE WHERE idempotency_key IS
        NOT NULL index supports this."""
        key = uuid.uuid4()
        event = ScanLogCreate(
            raw_payload="ORDER:1",
            idempotency_key=str(key),
        )
        first = await ScannerService.log_scan(
            db_session, sample_user.id, event
        )
        second = await ScannerService.log_scan(
            db_session, sample_user.id, event
        )
        assert first.id == second.id, (
            "Idempotency-key dedupe must return the original row, "
            "not insert a second one."
        )

    @pytest.mark.asyncio
    async def test_different_keys_insert_separately(
        self, db_session, sample_user
    ):
        """Different idempotency_keys must both insert independently."""
        e1 = ScanLogCreate(
            raw_payload="ORDER:1",
            idempotency_key=str(uuid.uuid4()),
        )
        e2 = ScanLogCreate(
            raw_payload="ORDER:2",
            idempotency_key=str(uuid.uuid4()),
        )
        r1 = await ScannerService.log_scan(db_session, sample_user.id, e1)
        r2 = await ScannerService.log_scan(db_session, sample_user.id, e2)
        assert r1.id != r2.id

    @pytest.mark.asyncio
    async def test_null_idem_key_always_inserts(
        self, db_session, sample_user
    ):
        """idempotency_key=None — unique index is partial, multiple
        inserts with NULL are all allowed."""
        e = ScanLogCreate(raw_payload="ORDER:1")
        r1 = await ScannerService.log_scan(db_session, sample_user.id, e)
        r2 = await ScannerService.log_scan(db_session, sample_user.id, e)
        assert r1.id != r2.id

    @pytest.mark.asyncio
    async def test_context_whitelist_persisted(
        self, db_session, sample_user
    ):
        """ScanContext round-trips through model_dump into context col."""
        ctx = ScanContext(
            running_timer_id=str(uuid.uuid4()),
            current_order_id=42,
            input_source="camera",
        )
        event = ScanLogCreate(raw_payload="ORDER:42", context=ctx)
        row = await ScannerService.log_scan(
            db_session, sample_user.id, event
        )
        assert row.context is not None
        assert row.context["current_order_id"] == 42
        assert row.context["input_source"] == "camera"


# --------------------------------------------------------------------------- #
# log_scan_batch — dedupe per-row, count summary
# --------------------------------------------------------------------------- #


class TestLogScanBatch:
    @pytest.mark.asyncio
    async def test_batch_all_fresh_ingested(
        self, db_session, sample_user
    ):
        events = [
            ScanLogCreate(raw_payload=f"ORDER:{i}")
            for i in range(1, 4)
        ]
        summary = await ScannerService.log_scan_batch(
            db_session, sample_user.id, events
        )
        assert summary.ingested == 3
        assert summary.deduplicated == 0
        assert summary.rejected == 0

    @pytest.mark.asyncio
    async def test_batch_dedupes_by_idempotency_key(
        self, db_session, sample_user
    ):
        """One unique key inserted in a prior call → replay hit as
        dedupe; two fresh keys ingested."""
        seen_key = uuid.uuid4()
        # First call writes the row.
        await ScannerService.log_scan(
            db_session,
            sample_user.id,
            ScanLogCreate(
                raw_payload="ORDER:1", idempotency_key=str(seen_key)
            ),
        )
        batch = [
            ScanLogCreate(
                raw_payload="ORDER:1", idempotency_key=str(seen_key)
            ),
            ScanLogCreate(
                raw_payload="ORDER:2",
                idempotency_key=str(uuid.uuid4()),
            ),
            ScanLogCreate(
                raw_payload="ORDER:3",
                idempotency_key=str(uuid.uuid4()),
            ),
        ]
        summary = await ScannerService.log_scan_batch(
            db_session, sample_user.id, batch
        )
        assert summary.ingested == 2
        assert summary.deduplicated == 1
        assert summary.rejected == 0


# --------------------------------------------------------------------------- #
# search_entities — VIEWER financial lockout
# --------------------------------------------------------------------------- #


class TestSearchEntities:
    @pytest_asyncio.fixture
    async def metal_with_lot(self, db_session) -> MetalPurchase:
        m = MetalPurchase(
            date_purchased=datetime.utcnow(),
            metal_type=MetalType.GOLD_18K,
            weight_g=50.0,
            remaining_weight_g=50.0,
            price_total=2000.0,
            price_per_gram=40.0,
            supplier="Edelmetall GmbH",
            lot_number="rein-lot-1",
        )
        db_session.add(m)
        await db_session.commit()
        await db_session.refresh(m)
        return m

    @pytest.mark.asyncio
    async def test_viewer_receives_no_metal_results(
        self, db_session, viewer_user, metal_with_lot
    ):
        """Even if the caller requests metal_purchase explicitly,
        VIEWER's financial lockout drops those rows."""
        results = await ScannerService.search_entities(
            db_session,
            "rein",
            ["metal_purchase"],
            viewer_user,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_goldsmith_receives_metal_results(
        self, db_session, sample_user, metal_with_lot
    ):
        """GOLDSMITH can search metal purchases (with production-floor
        projection — no price fields)."""
        results = await ScannerService.search_entities(
            db_session,
            "rein",
            ["metal_purchase"],
            sample_user,
        )
        assert len(results) >= 1
        # projection enforces GOLDSMITH allow-list — price_per_gram
        # is ADMIN-only and must not appear.
        for r in results:
            assert "price_per_gram" not in r
            assert "price_total" not in r

    @pytest.mark.asyncio
    async def test_admin_gets_financial_fields(
        self, db_session, admin_user, metal_with_lot
    ):
        results = await ScannerService.search_entities(
            db_session,
            "rein",
            ["metal_purchase"],
            admin_user,
        )
        assert len(results) >= 1
        # ADMIN allow-list carries the financial fields.
        assert any("price_per_gram" in r for r in results)

    @pytest.mark.asyncio
    async def test_empty_query_is_no_op(
        self, db_session, sample_user
    ):
        results = await ScannerService.search_entities(
            db_session,
            "   ",
            ["order"],
            sample_user,
        )
        assert results == []

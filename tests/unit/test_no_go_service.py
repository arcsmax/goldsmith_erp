"""Unit tests for NoGoService — V1.1 consultation module.

Covers the brief's three scenarios (add/list/delete roundtrip, duplicate guard,
bidirectional substring conflict matching) plus the legacy-field sync: adding
an ALLERGY no-go must also append to the legacy ``Customer.allergies`` string
(dedup case-insensitively, never truncate existing user data past the 500-char
column limit).
"""

import logging
import sys
import traceback
from unittest import mock

import pytest

import goldsmith_erp.db.transaction as transaction_module
import goldsmith_erp.services.no_go_service as no_go_service_module
from goldsmith_erp.db.models import CustomerNoGo, NoGoCategory
from goldsmith_erp.models.consultation import NoGoCreate
from goldsmith_erp.services.no_go_service import DuplicateNoGoError, NoGoService


@pytest.mark.asyncio
async def test_add_list_delete_roundtrip(db_session, sample_customer):
    ng = await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="allergy", value="Nickel")
    )
    assert [
        n.value for n in await NoGoService.list_no_gos(db_session, sample_customer.id)
    ] == ["Nickel"]
    await NoGoService.delete_no_go(db_session, sample_customer.id, ng.id)
    assert await NoGoService.list_no_gos(db_session, sample_customer.id) == []


@pytest.mark.asyncio
async def test_duplicate_no_go_rejected(db_session, sample_customer):
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="allergy", value="Nickel")
    )
    # Typed exception (subclasses ValueError for backwards compatibility);
    # message is generic and must never embed the submitted value.
    with pytest.raises(DuplicateNoGoError, match="existiert bereits") as exc_info:
        await NoGoService.add_no_go(
            db_session,
            sample_customer.id,
            NoGoCreate(category="allergy", value="nickel"),
        )
    assert "nickel" not in str(exc_info.value).casefold()


@pytest.mark.asyncio
async def test_duplicate_rejection_never_logs_raw_value(
    db_session, sample_customer, caplog
):
    """SECURITY: no-go values are health-adjacent data (e.g. allergies).

    A duplicate submission must not write the raw value to ANY log record —
    neither via the exception message (DuplicateNoGoError is generic) nor via
    db/transaction.py's error logger (the duplicate check raises BEFORE the
    transactional block, so that logger never sees business rejections).
    """
    secret_value = "Nickelsulfat-Allergie-XYZ"
    await NoGoService.add_no_go(
        db_session,
        sample_customer.id,
        NoGoCreate(category="allergy", value=secret_value),
    )

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(DuplicateNoGoError):
            await NoGoService.add_no_go(
                db_session,
                sample_customer.id,
                NoGoCreate(category="allergy", value=secret_value),
            )

    assert secret_value not in caplog.text


@pytest.mark.asyncio
async def test_check_conflicts_bidirectional_substring(db_session, sample_customer):
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="metal", value="Weißgold")
    )
    # candidate contains no-go
    hits = await NoGoService.check_conflicts(
        db_session, sample_customer.id, ["Weißgold 585 rhodiniert"]
    )
    assert len(hits) == 1 and hits[0].value == "Weißgold"
    # no-go contains candidate
    await NoGoService.add_no_go(
        db_session,
        sample_customer.id,
        NoGoCreate(category="stone", value="synthetischer Rubin"),
    )
    hits = await NoGoService.check_conflicts(db_session, sample_customer.id, ["Rubin"])
    assert any(h.category.value == "stone" for h in hits)
    # no match
    assert (
        await NoGoService.check_conflicts(db_session, sample_customer.id, ["Gelbgold"])
        == []
    )


@pytest.mark.asyncio
async def test_add_no_go_unknown_customer_raises(db_session):
    with pytest.raises(ValueError, match="Customer 99999 not found"):
        await NoGoService.add_no_go(
            db_session, 99999, NoGoCreate(category="allergy", value="Nickel")
        )


@pytest.mark.asyncio
async def test_delete_no_go_not_found_raises(db_session, sample_customer):
    with pytest.raises(ValueError):
        await NoGoService.delete_no_go(db_session, sample_customer.id, 99999)


# ── Legacy-field sync (Customer.allergies) ─────────────────────────────────


@pytest.mark.asyncio
async def test_add_allergy_no_go_syncs_legacy_field(db_session, sample_customer):
    assert sample_customer.allergies is None
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="allergy", value="Nickel")
    )
    assert "Nickel" in sample_customer.allergies


@pytest.mark.asyncio
async def test_add_allergy_no_go_does_not_duplicate_existing_legacy_value(
    db_session, sample_customer
):
    sample_customer.allergies = "Nickel"
    await db_session.commit()

    await NoGoService.add_no_go(
        db_session,
        sample_customer.id,
        NoGoCreate(category="allergy", value="nickel"),  # different casing
    )

    assert sample_customer.allergies == "Nickel"
    assert sample_customer.allergies.count("Nickel") == 1


@pytest.mark.asyncio
async def test_add_allergy_no_go_skips_legacy_sync_when_over_500_chars(
    db_session, sample_customer
):
    """Appending must never truncate existing user data — skip instead and warn.

    Uses a spy on the module logger instead of caplog: root-handler capture
    proved environment-dependent in CI (setup_logging() reconfigures the root
    logger at app import), while the spy asserts the same contract anywhere.
    """
    sample_customer.allergies = "A" * 495
    await db_session.commit()

    with mock.patch.object(no_go_service_module.logger, "warning") as warn_spy:
        await NoGoService.add_no_go(
            db_session,
            sample_customer.id,
            NoGoCreate(category="allergy", value="Nickel"),
        )

    assert sample_customer.allergies == "A" * 495  # untouched, not truncated
    assert warn_spy.called
    template = warn_spy.call_args.args[0]
    rendered = template % tuple(warn_spy.call_args.args[1:])
    assert "500" in rendered


@pytest.mark.asyncio
async def test_add_non_allergy_no_go_does_not_touch_legacy_field(
    db_session, sample_customer
):
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="metal", value="Nickel")
    )
    assert sample_customer.allergies is None


# ── DB-level unique index (issue #12 — TOCTOU backstop) ────────────────────
#
# The app-side pre-check in add_no_go (test_duplicate_no_go_rejected, above)
# already rejects same-request duplicates. These tests target the DB-level
# functional unique index on (customer_id, category, lower(value)) that now
# backstops a genuinely raced request — one where the pre-check's read ran
# BEFORE a concurrent request's conflicting row committed, so the read
# itself never saw it. A real race is hard to reproduce deterministically
# in a unit test, so `NoGoService.list_no_gos` is monkeypatched to return an
# empty list for the call inside `add_no_go`, reproducing exactly what a
# genuinely concurrent caller would observe: a pre-check that finds nothing,
# followed by an insert that collides anyway.


async def _add_no_go_bypassing_app_check(
    db_session, monkeypatch, customer_id, no_go_in
):
    """Call add_no_go with its app-side pre-check forced to see no rows.

    Used to reach the DB-level unique-index path directly, without a real
    concurrent second request.
    """

    async def _empty_list_no_gos(db, cid):
        return []

    monkeypatch.setattr(NoGoService, "list_no_gos", staticmethod(_empty_list_no_gos))
    return await NoGoService.add_no_go(db_session, customer_id, no_go_in)


@pytest.mark.asyncio
async def test_db_unique_index_catches_raced_duplicate_app_check_missed(
    db_session, sample_customer, monkeypatch
):
    """A conflicting row already committed in the DB, invisible to the
    (monkeypatched-empty) app-side pre-check, must still be rejected — via
    the new DB-level unique index — as the typed DuplicateNoGoError, never
    a raw IntegrityError leaking out of the service."""
    existing = CustomerNoGo(
        customer_id=sample_customer.id, category=NoGoCategory.ALLERGY, value="Nickel"
    )
    db_session.add(existing)
    await db_session.commit()

    with pytest.raises(DuplicateNoGoError, match="existiert bereits"):
        await _add_no_go_bypassing_app_check(
            db_session,
            monkeypatch,
            sample_customer.id,
            NoGoCreate(category="allergy", value="nickel"),  # case variant
        )


@pytest.mark.asyncio
async def test_db_conflict_duplicate_never_logs_raw_value(
    db_session, sample_customer, monkeypatch
):
    """SECURITY: on the DB-level (raced) duplicate path, the submitted
    no-go value must never reach ANY log — including db/transaction.py's
    generic error logger, which logs str(exc) at ERROR for every exception
    that escapes a `transactional()` block. SQLAlchemy's IntegrityError
    embeds the failed INSERT's bound parameters (i.e. the raw value) in
    its str() — verified empirically for this exact index/table shape —
    so add_no_go must catch it and swap it for the generic
    DuplicateNoGoError INSIDE the transactional block, before that logger
    ever sees it. Uses logger spies rather than caplog: root-handler
    capture proved environment-dependent in CI (see the 500-char legacy
    sync test above)."""
    secret_value = "Nickelsulfat-Allergie-XYZ"
    existing = CustomerNoGo(
        customer_id=sample_customer.id,
        category=NoGoCategory.ALLERGY,
        value=secret_value,
    )
    db_session.add(existing)
    await db_session.commit()

    # transactional() calls logger.error(..., exc_info=True) — capturing
    # only the mock's call_args would miss anything a real log handler
    # renders FROM exc_info (the active exception + its __cause__/
    # __context__ chain). Render that chain the same way a formatter
    # would, via a side_effect, so the test also proves `raise ... from
    # None` in add_no_go actually suppresses the original IntegrityError
    # (and its bound-parameter-laden str()) from that chain.
    rendered_tracebacks: list[str] = []

    def _record_rendered_traceback(*args, **kwargs):
        rendered_tracebacks.append("".join(traceback.format_exception(*sys.exc_info())))

    with (
        mock.patch.object(
            transaction_module.logger, "error", side_effect=_record_rendered_traceback
        ) as tx_error_spy,
        mock.patch.object(no_go_service_module.logger, "info") as service_info_spy,
    ):
        with pytest.raises(DuplicateNoGoError):
            await _add_no_go_bypassing_app_check(
                db_session,
                monkeypatch,
                sample_customer.id,
                NoGoCreate(category="allergy", value=secret_value.lower()),
            )

    # The rejection still passes through transactional()'s except-clause
    # (DuplicateNoGoError is raised INSIDE the block), so it does still log
    # an error — the point is that neither the log call's args/kwargs nor
    # the rendered exc_info traceback (chained exceptions included) carries
    # the secret value.
    assert tx_error_spy.called
    for call in tx_error_spy.call_args_list:
        assert secret_value not in str(call)
        assert secret_value.lower() not in str(call).lower()
    assert rendered_tracebacks
    for rendered in rendered_tracebacks:
        assert secret_value not in rendered
        assert secret_value.lower() not in rendered.lower()

    # The success-path "Customer no-go added" info log must never fire for
    # a rejected duplicate.
    assert not service_info_spy.called

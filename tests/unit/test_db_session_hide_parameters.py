# tests/unit/test_db_session_hide_parameters.py
"""
Regression test for the ``hide_parameters=True`` engine setting
(db/session.py, review fix).

SQLAlchemy's DBAPIError.__str__ embeds the failing statement's bound
PARAMETER VALUES by default. Any IntegrityError that escapes a
``transactional()`` block (db/transaction.py) is logged via
``logger.error(..., extra={"error": str(e)}, ...)`` — without
``hide_parameters=True`` that would write the raw bound values (customer
free-text, PII) straight into application logs. This test forces a real
IntegrityError (a CustomerUpdate NOT NULL violation) against the actual
test engine and asserts a sentinel value bound in the same failing INSERT
statement never appears in the exception's string representation.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from goldsmith_erp.db.models import CustomerUpdate, CustomerUpdateKind

pytestmark = pytest.mark.asyncio


async def test_integrity_error_does_not_echo_bound_parameters(db_session, sample_user):
    sentinel = "SENTINEL-CUSTOMER-FREE-TEXT-should-never-leak-4f8b21"

    bad_update = CustomerUpdate(
        order_id=None,
        repair_job_id=None,
        kind=CustomerUpdateKind.CUSTOM,
        subject=None,  # NOT NULL violation — triggers the IntegrityError.
        body=sentinel,  # Bound in the SAME failing INSERT statement.
        sent_by=sample_user.id,
    )
    db_session.add(bad_update)

    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()

    assert sentinel not in str(exc_info.value)
    assert "hidden due to hide_parameters" in str(exc_info.value)

    await db_session.rollback()

"""
Measurement Service — business logic for the customer Massbibliothek.

All measurement data is customer PII.  Log only anonymized IDs — never names,
finger positions, or raw measurement values in log messages at INFO or above.
Audit logging for financial/sensitive access is handled at the router layer.
"""
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Customer as CustomerModel,
    CustomerMeasurement as MeasurementModel,
    FingerPosition,
    HandSide,
    MeasurementType,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.measurement import MeasurementCreate, MeasurementUpdate

logger = logging.getLogger(__name__)


class MeasurementService:
    """Service layer for the customer Massbibliothek (measurement library)."""

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    @staticmethod
    async def get_measurements(
        db: AsyncSession,
        customer_id: int,
        measurement_type: Optional[MeasurementType] = None,
    ) -> List[MeasurementModel]:
        """
        Return all measurements for a customer, newest first.

        Optionally filtered by measurement_type (e.g. return only ring sizes).
        Uses selectinload to avoid N+1 when callers later access .goldsmith.
        """
        query = (
            select(MeasurementModel)
            .options(selectinload(MeasurementModel.goldsmith))
            .filter(MeasurementModel.customer_id == customer_id)
        )
        if measurement_type is not None:
            query = query.filter(
                MeasurementModel.measurement_type == measurement_type
            )
        query = query.order_by(MeasurementModel.measured_at.desc())

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_measurement(
        db: AsyncSession, measurement_id: int
    ) -> Optional[MeasurementModel]:
        """Get a single measurement by its primary key."""
        result = await db.execute(
            select(MeasurementModel)
            .options(selectinload(MeasurementModel.goldsmith))
            .filter(MeasurementModel.id == measurement_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_ring_size(
        db: AsyncSession,
        customer_id: int,
        hand: HandSide,
        finger: FingerPosition,
    ) -> Optional[MeasurementModel]:
        """
        Quick lookup: return the most recent ring-size measurement for a
        specific hand/finger combination.

        Returns None when no measurement is on record — the goldsmith must
        measure the customer before proceeding.
        """
        result = await db.execute(
            select(MeasurementModel)
            .filter(
                and_(
                    MeasurementModel.customer_id == customer_id,
                    MeasurementModel.measurement_type == MeasurementType.RING_SIZE,
                    MeasurementModel.hand == hand,
                    MeasurementModel.finger == finger,
                )
            )
            .order_by(MeasurementModel.measured_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    @staticmethod
    async def add_measurement(
        db: AsyncSession,
        customer_id: int,
        measurement_in: MeasurementCreate,
        measured_by_user_id: Optional[int] = None,
    ) -> MeasurementModel:
        """
        Add a measurement to a customer's Massbibliothek.

        Validates customer exists before inserting.  The measured_at timestamp
        defaults to the current server time when the caller does not supply one.
        """
        async with transactional(db):
            # Verify customer exists — fail loudly, not silently
            customer_exists = await db.execute(
                select(CustomerModel.id).filter(CustomerModel.id == customer_id)
            )
            if customer_exists.scalar_one_or_none() is None:
                raise ValueError(f"Customer {customer_id} not found")

            measured_at = measurement_in.measured_at or datetime.utcnow()

            db_measurement = MeasurementModel(
                customer_id=customer_id,
                measured_by=measured_by_user_id,
                measurement_type=measurement_in.measurement_type,
                value=measurement_in.value,
                unit=measurement_in.unit,
                hand=measurement_in.hand,
                finger=measurement_in.finger,
                notes=measurement_in.notes,
                measured_at=measured_at,
            )
            db.add(db_measurement)
            await db.flush()
            await db.refresh(db_measurement)

        logger.info(
            "Customer measurement added",
            extra={
                "customer_id": customer_id,
                "measurement_id": db_measurement.id,
                "measurement_type": db_measurement.measurement_type.value,
            },
        )
        return db_measurement

    @staticmethod
    async def update_measurement(
        db: AsyncSession,
        measurement_id: int,
        update_data: MeasurementUpdate,
    ) -> Optional[MeasurementModel]:
        """
        Update a measurement record.

        Only fields explicitly provided in the payload are changed.
        Returns None when the measurement does not exist.
        """
        async with transactional(db):
            db_measurement = await MeasurementService.get_measurement(
                db, measurement_id
            )
            if db_measurement is None:
                return None

            update_fields = update_data.model_dump(exclude_unset=True)
            for field, value in update_fields.items():
                setattr(db_measurement, field, value)

            db_measurement.updated_at = datetime.utcnow()
            await db.flush()
            await db.refresh(db_measurement)

        logger.info(
            "Customer measurement updated",
            extra={
                "measurement_id": measurement_id,
                "updated_fields": list(update_fields.keys()),
            },
        )
        return db_measurement

    @staticmethod
    async def delete_measurement(
        db: AsyncSession, measurement_id: int
    ) -> bool:
        """
        Hard-delete a single measurement record.

        Measurements are not orders — they carry no financial history and do
        not need a soft-delete grace period.  Returns False if not found.
        """
        async with transactional(db):
            db_measurement = await MeasurementService.get_measurement(
                db, measurement_id
            )
            if db_measurement is None:
                return False

            customer_id = db_measurement.customer_id
            await db.delete(db_measurement)

        logger.info(
            "Customer measurement deleted",
            extra={
                "measurement_id": measurement_id,
                "customer_id": customer_id,
            },
        )
        return True

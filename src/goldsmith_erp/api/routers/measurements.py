"""
Measurements API — customer Massbibliothek endpoints.

All endpoints require authentication.  Measurement data is customer PII and
is audit-logged on every access (read and write).

Route structure:
    GET    /api/v1/customers/{id}/measurements
    POST   /api/v1/customers/{id}/measurements
    GET    /api/v1/customers/{id}/ring-size       (convenience)
    GET    /api/v1/measurements/{id}
    PUT    /api/v1/measurements/{id}
    DELETE /api/v1/measurements/{id}
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import Permission, get_db, require_permission
from goldsmith_erp.db.models import FingerPosition, HandSide, User
from goldsmith_erp.models.measurement import (
    MeasurementCreate,
    MeasurementResponse,
    MeasurementUpdate,
    RingSizeLookupResponse,
)
from goldsmith_erp.services.customer_service import CustomerService
from goldsmith_erp.services.measurement_service import MeasurementService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["measurements"])


# ---------------------------------------------------------------------------
# Customer-scoped routes
# ---------------------------------------------------------------------------


@router.get(
    "/customers/{customer_id}/measurements",
    response_model=List[MeasurementResponse],
)
async def list_customer_measurements(
    customer_id: int,
    measurement_type: Optional[str] = Query(
        None,
        description=(
            "Filter by type: ring_size, chain_length, wrist_circumference, "
            "finger_circumference, neck_circumference, ankle_circumference"
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    List all measurements in a customer's Massbibliothek.

    Returns measurements newest-first.  Optionally filter by measurement_type.

    Permissions: CUSTOMER_VIEW
    """
    # Verify customer exists
    customer = await CustomerService.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    # Parse optional filter
    from goldsmith_erp.db.models import MeasurementType
    m_type = None
    if measurement_type:
        try:
            m_type = MeasurementType(measurement_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid measurement_type '{measurement_type}'",
            )

    logger.info(
        "Customer measurements accessed",
        extra={"customer_id": customer_id, "accessed_by": current_user.id},
    )

    try:
        measurements = await MeasurementService.get_measurements(
            db, customer_id, measurement_type=m_type
        )
        return measurements
    except Exception:
        logger.error(
            "Error listing measurements",
            extra={"customer_id": customer_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve measurements",
        )


@router.post(
    "/customers/{customer_id}/measurements",
    response_model=MeasurementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_customer_measurement(
    customer_id: int,
    measurement_in: MeasurementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_EDIT)),
):
    """
    Add a measurement to a customer's Massbibliothek.

    The recording goldsmith is automatically set to the authenticated user.

    Ring size example (EU inner circumference 54 mm, left ring finger):
    ```json
    {
      "measurement_type": "ring_size",
      "value": 54.0,
      "unit": "mm",
      "hand": "left",
      "finger": "ring",
      "notes": "Knöchel etwas breiter, Weitungsring empfohlen"
    }
    ```

    Chain length example:
    ```json
    {
      "measurement_type": "chain_length",
      "value": 45.0,
      "unit": "cm"
    }
    ```

    Permissions: CUSTOMER_EDIT
    """
    logger.info(
        "Customer measurement being added",
        extra={
            "customer_id": customer_id,
            "measurement_type": measurement_in.measurement_type.value,
            "added_by": current_user.id,
        },
    )

    try:
        measurement = await MeasurementService.add_measurement(
            db,
            customer_id=customer_id,
            measurement_in=measurement_in,
            measured_by_user_id=current_user.id,
        )
        return measurement
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(exc).lower()
            else status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception:
        logger.error(
            "Error adding measurement",
            extra={"customer_id": customer_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add measurement",
        )


@router.get(
    "/customers/{customer_id}/ring-size",
    response_model=RingSizeLookupResponse,
)
async def get_ring_size(
    customer_id: int,
    hand: HandSide = Query(..., description="LEFT or RIGHT"),
    finger: FingerPosition = Query(..., description="thumb, index, middle, ring, pinky"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Convenience endpoint: look up the most recent ring size for a customer's
    specific hand and finger.

    Returns ring_size_eu = null when no measurement is on record.
    The goldsmith must then measure the customer before creating the order.

    Permissions: CUSTOMER_VIEW
    """
    # Verify customer exists
    customer = await CustomerService.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    logger.info(
        "Ring size lookup",
        extra={
            "customer_id": customer_id,
            "hand": hand.value,
            "finger": finger.value,
            "accessed_by": current_user.id,
        },
    )

    try:
        measurement = await MeasurementService.get_ring_size(
            db, customer_id=customer_id, hand=hand, finger=finger
        )

        if measurement is None:
            # No measurement on record — return empty lookup, not 404
            return RingSizeLookupResponse(
                customer_id=customer_id,
                hand=hand,
                finger=finger,
                ring_size_eu=None,
            )

        return RingSizeLookupResponse(
            customer_id=customer_id,
            hand=hand,
            finger=finger,
            ring_size_eu=measurement.value,
            unit=measurement.unit,
            notes=measurement.notes,
            measured_at=measurement.measured_at,
            measured_by=measurement.measured_by,
        )
    except Exception:
        logger.error(
            "Error looking up ring size",
            extra={"customer_id": customer_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ring size",
        )


# ---------------------------------------------------------------------------
# Individual measurement routes
# ---------------------------------------------------------------------------


@router.get(
    "/measurements/{measurement_id}",
    response_model=MeasurementResponse,
)
async def get_measurement(
    measurement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get a single measurement by ID.

    Permissions: CUSTOMER_VIEW
    """
    measurement = await MeasurementService.get_measurement(db, measurement_id)
    if not measurement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Measurement {measurement_id} not found",
        )
    logger.info(
        "Measurement accessed",
        extra={"measurement_id": measurement_id, "accessed_by": current_user.id},
    )
    return measurement


@router.put(
    "/measurements/{measurement_id}",
    response_model=MeasurementResponse,
)
async def update_measurement(
    measurement_id: int,
    update_data: MeasurementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_EDIT)),
):
    """
    Update a measurement record.

    Only supplied fields are changed.  Use this when a re-measurement
    reveals a different size — e.g. after pregnancy or significant weight
    change.  The original measured_at can be backdated to reflect when the
    physical measurement was taken.

    Permissions: CUSTOMER_EDIT
    """
    logger.info(
        "Measurement update requested",
        extra={"measurement_id": measurement_id, "updated_by": current_user.id},
    )

    try:
        updated = await MeasurementService.update_measurement(
            db, measurement_id=measurement_id, update_data=update_data
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Measurement {measurement_id} not found",
            )
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "Error updating measurement",
            extra={"measurement_id": measurement_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update measurement",
        )


@router.delete(
    "/measurements/{measurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_measurement(
    measurement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_DELETE)),
):
    """
    Delete a measurement from the Massbibliothek.

    This is a hard delete — measurement data carries no financial history.
    Deleting is appropriate when a measurement was recorded in error or the
    customer explicitly requests erasure (GDPR Art. 17).

    Permissions: CUSTOMER_DELETE (Admin only)
    """
    logger.info(
        "Measurement deletion requested",
        extra={"measurement_id": measurement_id, "deleted_by": current_user.id},
    )

    try:
        success = await MeasurementService.delete_measurement(db, measurement_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Measurement {measurement_id} not found",
            )
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "Error deleting measurement",
            extra={"measurement_id": measurement_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete measurement",
        )

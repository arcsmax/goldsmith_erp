# src/goldsmith_erp/api/routers/imports.py
"""
Data import endpoints — CSV upload for bulk customer onboarding.

All endpoints require ADMIN role.  GOLDSMITH role intentionally excluded:
bulk imports can overwrite existing data and bypass the normal per-record
validation flow, so only administrators should perform them.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_admin_user, get_db
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.services.import_service import (
    CSV_HEADERS,
    SAMPLE_CSV_ROWS,
    ImportResult,
    ImportRowError,
    import_customers_csv,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])

# Maximum CSV file size: 5 MB (5 * 1024 * 1024 bytes)
_MAX_CSV_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------


class ImportRowErrorOut(BaseModel):
    row_number: int
    field: Optional[str]
    message: str


class ImportResultOut(BaseModel):
    imported_count: int
    skipped_count: int
    error_count: int
    total_rows: int
    errors: list[ImportRowErrorOut]


def _serialize_result(result: ImportResult) -> ImportResultOut:
    return ImportResultOut(
        imported_count=result.imported_count,
        skipped_count=result.skipped_count,
        error_count=len(result.errors),
        total_rows=result.total_rows,
        errors=[
            ImportRowErrorOut(
                row_number=e.row_number,
                field=e.field,
                message=e.message,
            )
            for e in result.errors
        ],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/customers",
    response_model=ImportResultOut,
    status_code=status.HTTP_200_OK,
    summary="Kundendaten aus CSV-Datei importieren",
    description=(
        "Importiert Kundendatensätze aus einer hochgeladenen CSV-Datei (UTF-8, "
        "Komma-getrennt). Doppelte Einträge (gleiche E-Mail-Adresse) werden "
        "übersprungen. Ungültige Zeilen werden protokolliert; der Import läuft "
        "trotzdem weiter. ADMIN-only.\n\n"
        "Pflichtfelder: ``first_name``, ``last_name``, ``email``.\n\n"
        "Optionale Felder: ``phone``, ``street``, ``city``, ``postal_code``, "
        "``customer_type`` (``private``/``business``), ``birthday`` (YYYY-MM-DD), "
        "``ring_size`` (Dezimalzahl), ``notes``."
    ),
)
async def import_customers(
    file: UploadFile = File(..., description="CSV-Datei (UTF-8, Komma-getrennt, max. 5 MB)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user),
) -> ImportResultOut:
    """
    Upload a CSV file and bulk-import customer records.

    The endpoint is transactional: all successfully parsed rows are committed
    together.  If a database error occurs during the commit, the entire batch
    is rolled back and a 500 is returned.  Per-row validation errors do NOT
    abort the import — they are collected and returned in the response body.
    """
    if file.content_type not in (
        "text/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Nur CSV-Dateien werden unterstützt. "
                f"Empfangen: {file.content_type or 'unbekannt'}"
            ),
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV-Datei zu groß. Maximum: 5 MB.",
        )

    try:
        csv_text = raw_bytes.decode("utf-8-sig")  # utf-8-sig strips BOM if present
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "CSV-Datei konnte nicht als UTF-8 dekodiert werden. "
                "Bitte speichern Sie die Datei als UTF-8 (mit oder ohne BOM)."
            ),
        )

    try:
        result = await import_customers_csv(
            db=db,
            csv_content=csv_text,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "CSV customer import: DB commit failed — rollback performed",
            extra={"user_id": current_user.id, "error": str(exc)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Datenbankfehler beim Speichern der importierten Kunden. "
                "Kein Datensatz wurde gespeichert. Bitte Logs prüfen."
            ),
        ) from exc

    return _serialize_result(result)


@router.get(
    "/customers/template",
    summary="CSV-Vorlage mit Beispieldaten herunterladen",
    description=(
        "Gibt eine CSV-Datei mit Kopfzeile und einer Beispielzeile zurück. "
        "Dient als Vorlage für den Massenimport von Kundendaten. ADMIN-only."
    ),
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "CSV template file",
        }
    },
)
async def download_customer_csv_template(
    _current_user: UserModel = Depends(get_current_admin_user),
) -> Response:
    """Return a downloadable CSV template with headers and one sample row."""
    header_line = ",".join(CSV_HEADERS)
    sample_line = ",".join(SAMPLE_CSV_ROWS[0].get(h, "") for h in CSV_HEADERS)
    csv_body = f"{header_line}\n{sample_line}\n"

    return Response(
        content=csv_body.encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="kunden-import-vorlage.csv"',
            "Content-Type": "text/csv; charset=utf-8",
        },
    )

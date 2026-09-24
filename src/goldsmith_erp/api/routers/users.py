# src/goldsmith_erp/api/routers/users.py

import logging
from typing import List, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.core.security import verify_password
from goldsmith_erp.core.token_revocation import invalidate_user_tokens
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.user import (
    LastAdminError,
    SentinelMissing,
    User,
    UserAdminUpdate,
    UserCreate,
    UserErasureRequest,
    UserErasureResponse,
    UserNotFound,
    UserSelfUpdate,
    UserUpdate,
)
from goldsmith_erp.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== ADMIN-GATED REGISTRATION ====================
# As of fix A3 (2026-04-23) /users/register is no longer a public
# self-service endpoint. It is now ADMIN-invitation-only, matching
# POST /users/. The legacy /register path is preserved for back-compat
# with existing admin tooling; both routes are guarded by the same
# permission and perform the same work.


@router.post(
    "/register",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,  # R2: admin-only; not part of public API surface
)
@require_permission(Permission.USER_CREATE)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    **Admin-Registrierung**: Admin legt einen neuen Benutzer-Account an.

    - **Admin-Berechtigung erforderlich** (`USER_CREATE`)
    - Erstellt einen neuen Benutzer-Account
    - E-Mail muss eindeutig sein

    **Use Case**: Admin trägt einen neuen Mitarbeiter oder Kunden ein.

    **Security note (A3):** Previously a public self-service endpoint,
    this route leaked account existence via the 400 duplicate-email
    branch. Unauthenticated callers now hit the auth middleware first
    and receive 401 across all inputs — no oracle.
    """
    # Prüfen ob E-Mail bereits existiert
    existing_user = await UserService.get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Benutzer erstellen
    user = await UserService.create_user(db, user_in)
    return user


# ==================== AUTHENTICATED ENDPOINTS ====================


@router.get("/me", response_model=User)
async def get_current_user_profile(current_user: UserModel = Depends(get_current_user)):
    """
    Eigenes Benutzer-Profil abrufen.

    - **Authentifizierung erforderlich**
    - Gibt das Profil des eingeloggten Benutzers zurück

    **Use Case**: Benutzer möchte seine eigenen Profil-Daten sehen.
    """
    return current_user


# Either update schema carries an (optional) current_password field, used
# by both PUT /users/me (self-service) and, since SEC-11 finding B3.1/B3.2
# (2026-09-25), PUT /users/{user_id} when an ADMIN targets their own id.
_ReauthableUserUpdate = Union[UserSelfUpdate, UserAdminUpdate]


def _changes_credentials(
    user_in: _ReauthableUserUpdate, current_user: UserModel
) -> bool:
    """True if the update changes the password or the (login) email."""
    if user_in.password is not None:
        return True
    return user_in.email is not None and user_in.email != current_user.email


def _require_current_password(
    user_in: _ReauthableUserUpdate, current_user: UserModel
) -> None:
    """Re-authenticate a credential change (SEC-11). Raises on failure."""
    if not user_in.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="current_password is required to change email or password",
        )
    if not verify_password(user_in.current_password, current_user.hashed_password):
        # 403, not 401: the session is valid, and a 401 would make the frontend
        # interceptor treat it as an expired token.
        logger.warning(
            "Credential change rejected: wrong current password",
            extra={"user_id": current_user.id, "event": "credential_change_denied"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current password is incorrect",
        )


@router.put("/me", response_model=User)
async def update_current_user_profile(
    user_in: UserSelfUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Eigenes Benutzer-Profil aktualisieren.

    - **Authentifizierung erforderlich**
    - Benutzer kann nur sein eigenes Profil bearbeiten
    - E-Mail, Name und Passwort können geändert werden
    - E-Mail- oder Passwortänderung erfordert `current_password` (SEC-11)

    **Use Case**: Benutzer möchte seine Profil-Daten aktualisieren.
    """
    is_credential_change = _changes_credentials(user_in, current_user)
    is_email_change = user_in.email is not None and user_in.email != current_user.email
    if is_credential_change:
        _require_current_password(user_in, current_user)

    # Prüfen ob neue E-Mail bereits existiert (falls geändert)
    if user_in.email and user_in.email != current_user.email:
        existing_user = await UserService.get_user_by_email(db, user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use"
            )

    # Profil aktualisieren (current_password is verification only, never stored)
    profile_update = UserUpdate(
        **user_in.model_dump(exclude_unset=True, exclude={"current_password"})
    )
    updated_user = await UserService.update_user(db, current_user.id, profile_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if is_credential_change:
        logger.info(
            "Credentials changed by account owner",
            extra={
                "user_id": current_user.id,
                "event": "credential_change",
                "password_changed": user_in.password is not None,
                "email_changed": is_email_change,
            },
        )

    # Password change revokes all outstanding tokens for this user (finding 2.1):
    # set the per-user invalid-before mark so every token issued before now is
    # rejected by the auth dependency. Avoids tracking individual jtis.
    if user_in.password is not None:
        await invalidate_user_tokens(str(current_user.id))

    return updated_user


# ==================== ADMIN-ONLY ENDPOINTS ====================


@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
@require_permission(Permission.USER_CREATE)
async def create_user_by_admin(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    **Admin-Registration**: Goldschmied (Admin) trägt einen neuen Benutzer ein.

    - **Admin-Berechtigung erforderlich**
    - Erstellt einen neuen Benutzer-Account
    - E-Mail muss eindeutig sein

    **Use Case**: Goldschmied trägt einen neuen Mitarbeiter oder Kunden ein.
    """
    # Prüfen ob E-Mail bereits existiert
    existing_user = await UserService.get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Benutzer erstellen
    user = await UserService.create_user(db, user_in)
    return user


@router.get("/", response_model=List[User])
@require_permission(Permission.USER_VIEW)
async def list_all_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Alle Benutzer auflisten.

    - **Admin-Berechtigung erforderlich**
    - Gibt eine Liste aller Benutzer zurück (mit Pagination)

    **Use Case**: Admin möchte alle registrierten Benutzer sehen.
    """
    users = await UserService.get_users(db, skip, limit)
    return users


@router.get("/{user_id}", response_model=User)
@require_permission(Permission.USER_VIEW)
async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Benutzer über ID abrufen.

    - **Admin-Berechtigung erforderlich**
    - Gibt einen spezifischen Benutzer zurück

    **Use Case**: Admin möchte Details eines bestimmten Benutzers sehen.
    """
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.put("/{user_id}", response_model=User)
@require_permission(Permission.USER_EDIT)
async def update_user_by_admin(
    user_id: int,
    user_in: UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Benutzer durch Admin aktualisieren.

    - **Admin-Berechtigung erforderlich** (`USER_EDIT`, ADMIN only — see
      `core.permissions.ROLE_PERMISSIONS`)
    - Admin kann beliebige Benutzer-Daten ändern
    - Inkl. Aktivierungs-Status (is_active)
    - Inkl. Rolle (`role`, SEC-F6): nur ein ADMIN darf Rollen vergeben oder
      ändern; der letzte aktive ADMIN kann nicht herabgestuft werden (409)

    **Use Case**: Admin möchte Benutzer-Daten korrigieren, Status ändern
    oder einem Kollegen eine andere Rolle zuweisen.

    **Security note (SEC-11, adversarial finding B3.1/B3.2, 2026-09-25):**
    `USER_EDIT` is held unconditionally by ADMIN, including against their
    own `user_id` — without a check this route would let a hijacked/XSS'd
    ADMIN session, or an unattended unlocked session, silently take over
    the account by changing its own email/password here with zero
    re-authentication, completely bypassing the SEC-11 rule `PUT /users/me`
    enforces. When `user_id == current_user.id` and the payload changes
    email or password, `current_password` is required and verified exactly
    like `/users/me` (400 missing, 403 wrong). Changing another user's
    credentials as ADMIN is unaffected — that stays allowed and is
    audit-logged by the middleware.
    """
    is_self_edit = user_id == current_user.id
    if is_self_edit and _changes_credentials(user_in, current_user):
        _require_current_password(user_in, current_user)

    # Prüfen ob neue E-Mail bereits existiert (falls geändert)
    if user_in.email:
        user = await UserService.get_user_by_id(db, user_id)
        if user and user_in.email != user.email:
            existing_user = await UserService.get_user_by_email(db, user_in.email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use",
                )

    # Benutzer aktualisieren (current_password is verification only, never
    # persisted — UserService.update_user would otherwise try to write it
    # to a non-existent column).
    update_payload = UserAdminUpdate(
        **user_in.model_dump(exclude_unset=True, exclude={"current_password"})
    )
    try:
        updated_user = await UserService.update_user(db, user_id, update_payload)
    except LastAdminError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot change the role of the last active administrator.",
        )
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Admin password reset revokes the target user's outstanding tokens
    # (finding 2.1) — see the self-service handler above for the mechanism.
    if user_in.password is not None:
        await invalidate_user_tokens(str(user_id))

    if user_in.role is not None:
        logger.info(
            "User role changed by admin",
            extra={
                "user_id": user_id,
                "new_role": user_in.role.value,
                "changed_by": current_user.id,
                "event": "role_change",
            },
        )

    if is_self_edit and _changes_credentials(user_in, current_user):
        email_changed = user_in.email is not None
        logger.info(
            "Credentials changed by account owner via admin route",
            extra={
                "user_id": user_id,
                "event": "credential_change",
                "password_changed": user_in.password is not None,
                "email_changed": email_changed,
            },
        )

    return updated_user


@router.delete("/{user_id}")
@require_permission(Permission.USER_MANAGE)
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Benutzer deaktivieren (Soft Delete).

    - **Admin-Berechtigung erforderlich**
    - Setzt is_active auf False
    - Benutzer kann sich nicht mehr einloggen
    - Daten bleiben erhalten

    **Use Case**: Admin möchte einen Benutzer sperren, aber Daten behalten.
    """
    result = await UserService.delete_user(db, user_id)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=result["message"]
        )

    return result


@router.post("/{user_id}/gdpr-erase", response_model=UserErasureResponse)
@require_permission(Permission.USER_DELETE)
async def gdpr_erase_user(
    user_id: int,
    payload: Optional[UserErasureRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    **GDPR Art. 17 (Recht auf Löschung)** — Mitarbeiter-Konto anonymisieren.

    - **Admin-Berechtigung erforderlich** (`USER_DELETE`)
    - Ruft :meth:`UserService.anonymize_user` auf: überschreibt alle PII auf
      der ``users``-Zeile mit Sentinel-Werten, schreibt jede FK-Referenz auf
      den globalen Sentinel-User um und scrubbt die denormalisierte
      ``customer_audit_logs.user_email``-Kopie — alles in einer Transaktion.
    - Die Zeile wird **nicht** hart gelöscht: ``id`` und ``role`` bleiben
      erhalten, damit ``ON DELETE RESTRICT``-FKs weiter auflösen. §147 AO /
      §257 HGB Aufbewahrungspflichten bleiben dadurch gewahrt.
    - **Idempotent**: ein zweiter Aufruf gibt ``already_anonymized=True``
      zurück (kein Fehler).

    **Guard rails:**
    - Der Sentinel-User selbst kann nicht anonymisiert werden → 409.
    - Der **letzte aktive ADMIN** kann nicht anonymisiert werden → 409. Da
      dieser Endpunkt ADMIN-only ist, deckt genau diese Regel auch den
      Selbst-Löschungs-Fall ab: ein Admin darf sich selbst löschen, solange
      mindestens ein weiterer aktiver Admin existiert; ist er der letzte,
      schützt der Last-Admin-Guard den Workshop vor der Aussperrung.
    - Unbekannte ``user_id`` → 404.

    **Response** trägt ausschließlich nicht-re-identifizierbare Daten
    (ids, HMAC-Token, Zähler) — keine E-Mail, kein Name.

    **Use Case**: Ein ausgeschiedener Mitarbeiter verlangt Löschung seiner
    personenbezogenen Daten (GDPR Art. 17); Finanz-/Auftragshistorie bleibt
    pseudonymisiert erhalten.
    """
    reason = (
        payload.reason.strip()
        if payload is not None and payload.reason and payload.reason.strip()
        else "GDPR Art. 17 erasure (admin-initiated)"
    )

    try:
        result = await UserService.anonymize_user(
            db,
            user_id,
            reason=reason,
            requested_by=current_user.id,
        )
    except UserNotFound:
        # 404 — no PII in the message.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except LastAdminError:
        # 409 — target is the last active ADMIN or the GDPR sentinel. Covers
        # the self-erasure guard rail (an admin cannot erase themselves out
        # of the last admin seat). No PII in the message.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot erase the last active administrator or the GDPR "
                "sentinel user."
            ),
        )
    except SentinelMissing:
        # Bootstrap failure — the sentinel row could not be resolved/created.
        # A genuine server-side condition, surfaced without leaking detail.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GDPR erasure unavailable: sentinel user could not be resolved.",
        )

    detail = (
        "User was already anonymised (idempotent no-op)."
        if result.already_anonymized
        else "User anonymised under GDPR Art. 17."
    )

    return UserErasureResponse(
        user_id=result.user_id,
        sentinel_user_id=result.sentinel_user_id,
        tracking_hmac=result.tracking_hmac,
        gdpr_request_id=result.gdpr_request_id,
        already_anonymized=result.already_anonymized,
        fk_updates=result.fk_updates,
        audit_email_scrubs=result.audit_email_scrubs,
        detail=detail,
    )


@router.post("/{user_id}/activate", response_model=User)
@require_permission(Permission.USER_MANAGE)
async def activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Benutzer reaktivieren.

    - **Admin-Berechtigung erforderlich**
    - Setzt is_active auf True
    - Benutzer kann sich wieder einloggen

    **Use Case**: Admin möchte einen gesperrten Benutzer wieder aktivieren.
    """
    user = await UserService.activate_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user

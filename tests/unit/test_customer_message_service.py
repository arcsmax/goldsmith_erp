# tests/unit/test_customer_message_service.py
"""
Unit tests for CustomerMessageService (W6-01, Wave 6 phase 1).

The service is the single way a customer-facing message leaves the system.
Covers:
- the consent / legal-basis matrix per message kind (Art. 6(1)(b) vs 6(1)(a))
- price leakage guard (prices only in quote / cost-change messages)
- photo attachments: max 1200 px, EXIF stripped, only with PHOTO_USE consent
- dedupe key (one live row per key)
- PDF_MANUAL fallback when the customer has no email address
- Art. 21 opt-out ("Keine E-Mail-Updates") honoured, also by automated mails
- Art. 13 footer + reply-by-email line in every message
- one CustomerAuditLog row per sent message (ids and photo count, no body)
"""

import io
import uuid
from email import message_from_bytes

import pytest
from PIL import Image
from sqlalchemy import select

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CustomerAuditLog,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    NotificationTypeEnum,
    OrderPhoto,
    UpdateDeliveryMethod,
)
from goldsmith_erp.models.consent import ConsentMethod, ConsentPurpose
from goldsmith_erp.services import automated_customer_email
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.consent_service import ConsentService
from goldsmith_erp.services.customer_message_service import (
    MESSAGE_POLICIES,
    PHOTO_MAX_PX,
    CustomerMessageService,
    LegalBasis,
    MessageKind,
    PhotoConsentRequiredError,
    PriceNotAllowedError,
)
from goldsmith_erp.services.customer_update_service import DuplicateDedupeKeyError

# asyncio_mode = "auto" (pyproject.toml) runs the async tests.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


class _CapturingSend:
    def __init__(self) -> None:
        self.sent_messages: list = []

    async def __call__(self, msg, **kwargs):
        self.sent_messages.append(msg)
        return None


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> _CapturingSend:
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)
    return capture


async def _make_photo(db_session, tmp_path, order, user, size=(200, 100), exif=False):
    photo_dir = tmp_path / str(order.id)
    photo_dir.mkdir(parents=True, exist_ok=True)
    photo_path = photo_dir / f"{uuid.uuid4().hex}.jpg"
    img = Image.new("RGB", size, color=(120, 20, 30))
    if exif:
        exif_data = Image.Exif()
        exif_data[0x010F] = "SecretCameraMaker"  # Make
        exif_data[0x0110] = "SecretModel"  # Model
        img.save(photo_path, format="JPEG", exif=exif_data)
    else:
        img.save(photo_path, format="JPEG")
    photo = OrderPhoto(
        id=str(uuid.uuid4()),
        order_id=order.id,
        file_path=str(photo_path),
        taken_by=user.id,
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(photo)
    return photo


async def _grant(db_session, customer_id: int, purpose: ConsentPurpose) -> None:
    await ConsentService.grant(
        db_session,
        customer_id,
        purpose=purpose,
        method=ConsentMethod.IN_PERSON,
        recorded_by_user_id=None,
    )
    await db_session.commit()


def _html_part(msg) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode("utf-8")
    raise AssertionError("no html part")


def _plain_part(msg) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode("utf-8")
    raise AssertionError("no plain part")


def _jpeg_parts(msg) -> list[bytes]:
    return [
        part.get_payload(decode=True)
        for part in msg.walk()
        if part.get_content_type() == "image/jpeg"
    ]


# ---------------------------------------------------------------------------
# Policy table (Art. 6(1)(b) vs 6(1)(a))
# ---------------------------------------------------------------------------


class TestPolicyTable:
    def test_every_kind_has_a_policy(self):
        assert set(MESSAGE_POLICIES) == set(MessageKind)

    @pytest.mark.parametrize(
        "kind",
        [
            MessageKind.STATUS_UPDATE,
            MessageKind.QUESTION,
            MessageKind.PICKUP_READY,
            MessageKind.QUOTE_SENT,
            MessageKind.COST_CHANGE,
            MessageKind.APPOINTMENT,
        ],
    )
    def test_transactional_kinds_are_contractual(self, kind):
        policy = MESSAGE_POLICIES[kind]
        assert policy.legal_basis is LegalBasis.CONTRACT
        assert policy.required_consent is None

    def test_photo_update_needs_photo_consent(self):
        policy = MESSAGE_POLICIES[MessageKind.PHOTO_UPDATE]
        assert policy.legal_basis is LegalBasis.CONSENT
        assert policy.required_consent is ConsentPurpose.PHOTO_USE

    def test_only_quote_and_cost_change_may_carry_prices(self):
        price_kinds = {k for k, p in MESSAGE_POLICIES.items() if p.may_contain_prices}
        assert price_kinds == {MessageKind.QUOTE_SENT, MessageKind.COST_CHANGE}


# ---------------------------------------------------------------------------
# Consent matrix per kind
# ---------------------------------------------------------------------------


class TestConsentMatrix:
    @pytest.mark.parametrize(
        "kind",
        [
            MessageKind.STATUS_UPDATE,
            MessageKind.QUESTION,
            MessageKind.PICKUP_READY,
            MessageKind.APPOINTMENT,
        ],
    )
    async def test_contractual_kind_sends_without_any_consent(
        self, db_session, sample_order, sample_user, smtp, kind
    ):
        result = await CustomerMessageService.send_message(
            db_session,
            kind=kind,
            order_id=sample_order.id,
            subject="Ihr Auftrag",
            body="Kurzer Stand zu Ihrem Auftrag.",
            user_id=sample_user.id,
        )
        assert result.delivered is True
        assert result.method == UpdateDeliveryMethod.EMAIL
        assert len(smtp.sent_messages) == 1

    async def test_photo_update_without_photo_consent_is_refused_and_nothing_stored(
        self, db_session, sample_order, sample_user, smtp, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(tmp_path))
        photo = await _make_photo(db_session, tmp_path, sample_order, sample_user)

        with pytest.raises(PhotoConsentRequiredError) as excinfo:
            await CustomerMessageService.send_message(
                db_session,
                kind=MessageKind.PHOTO_UPDATE,
                order_id=sample_order.id,
                subject="Neue Fotos",
                body="Hier sehen Sie den Zwischenstand.",
                photo_ids=[photo.id],
                user_id=sample_user.id,
            )
        assert "Einwilligung" in str(excinfo.value)
        rows = (await db_session.execute(select(CustomerUpdate))).scalars().all()
        assert rows == []
        assert smtp.sent_messages == []

    async def test_photo_update_with_photo_consent_sends_photos(
        self, db_session, sample_order, sample_user, smtp, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(tmp_path))
        await _grant(db_session, sample_order.customer_id, ConsentPurpose.PHOTO_USE)
        photo = await _make_photo(db_session, tmp_path, sample_order, sample_user)

        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.PHOTO_UPDATE,
            order_id=sample_order.id,
            subject="Neue Fotos",
            body="Hier sehen Sie den Zwischenstand.",
            photo_ids=[photo.id],
            user_id=sample_user.id,
        )
        assert result.delivered is True
        assert len(_jpeg_parts(smtp.sent_messages[0])) == 1

    async def test_status_update_with_photos_also_needs_photo_consent(
        self, db_session, sample_order, sample_user, smtp, tmp_path, monkeypatch
    ):
        """Photos are gated by PHOTO_USE whatever kind the caller picked."""
        monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(tmp_path))
        photo = await _make_photo(db_session, tmp_path, sample_order, sample_user)
        with pytest.raises(PhotoConsentRequiredError):
            await CustomerMessageService.send_message(
                db_session,
                kind=MessageKind.STATUS_UPDATE,
                order_id=sample_order.id,
                subject="Stand",
                body="Text",
                photo_ids=[photo.id],
                user_id=sample_user.id,
            )

    async def test_photo_consent_revoked_after_draft_blocks_the_send(
        self, db_session, sample_order, sample_user, smtp, tmp_path, monkeypatch
    ):
        from goldsmith_erp.models.customer_update import CustomerUpdateCreate
        from goldsmith_erp.services.customer_update_service import CustomerUpdateService

        monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(tmp_path))
        await _grant(db_session, sample_order.customer_id, ConsentPurpose.PHOTO_USE)
        photo = await _make_photo(db_session, tmp_path, sample_order, sample_user)
        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(
                kind=CustomerUpdateKind.PROGRESS, photo_ids=[photo.id]
            ),
            user_id=sample_user.id,
        )
        await ConsentService.revoke(
            db_session,
            sample_order.customer_id,
            ConsentPurpose.PHOTO_USE,
            revoked_by_user_id=None,
        )
        await db_session.commit()

        with pytest.raises(PhotoConsentRequiredError):
            await CustomerUpdateService.send(db_session, draft.id, sample_user.id)
        await db_session.refresh(draft)
        assert draft.status == CustomerUpdateStatus.DRAFT
        assert smtp.sent_messages == []


# ---------------------------------------------------------------------------
# Price leakage
# ---------------------------------------------------------------------------


class TestNoPriceLeakage:
    @pytest.mark.parametrize(
        "body",
        [
            "Der Ring kostet 450,00 €.",
            "Neuer Preis: 1.200 EUR",
            "Gesamt € 99",
            "Das macht 80 Euro.",
        ],
    )
    async def test_status_update_with_price_is_refused(
        self, db_session, sample_order, sample_user, smtp, body
    ):
        with pytest.raises(PriceNotAllowedError):
            await CustomerMessageService.send_message(
                db_session,
                kind=MessageKind.STATUS_UPDATE,
                order_id=sample_order.id,
                subject="Stand",
                body=body,
                user_id=sample_user.id,
            )
        assert smtp.sent_messages == []

    async def test_price_in_subject_is_refused(
        self, db_session, sample_order, sample_user, smtp
    ):
        with pytest.raises(PriceNotAllowedError):
            await CustomerMessageService.send_message(
                db_session,
                kind=MessageKind.QUESTION,
                order_id=sample_order.id,
                subject="Aufpreis 30 €?",
                body="Passt das?",
                user_id=sample_user.id,
            )

    async def test_quote_message_may_carry_a_price(
        self, db_session, sample_order, sample_user, smtp
    ):
        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.QUOTE_SENT,
            order_id=sample_order.id,
            subject="Ihr Kostenvoranschlag",
            body="Der Kostenvoranschlag beträgt 1.190,00 €.",
            user_id=sample_user.id,
        )
        assert result.delivered is True

    async def test_plain_numbers_are_not_prices(
        self, db_session, sample_order, sample_user, smtp
    ):
        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject="Stand",
            body="Ringgröße 54, 750er Gold, fertig am 12.10.",
            user_id=sample_user.id,
        )
        assert result.delivered is True

    async def test_rendered_status_email_has_no_currency(
        self, db_session, sample_order, sample_user, smtp
    ):
        await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject="Stand",
            body="Wir sind beim Polieren.",
            user_id=sample_user.id,
        )
        html = _html_part(smtp.sent_messages[0])
        assert "€" not in html
        assert "EUR" not in html


# ---------------------------------------------------------------------------
# Photo attachments: resized + EXIF-free
# ---------------------------------------------------------------------------


class TestPhotoAttachments:
    async def test_attachment_is_resized_to_1200_and_exif_free(
        self, db_session, sample_order, sample_user, smtp, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(tmp_path))
        await _grant(db_session, sample_order.customer_id, ConsentPurpose.PHOTO_USE)
        photo = await _make_photo(
            db_session,
            tmp_path,
            sample_order,
            sample_user,
            size=(3000, 1500),
            exif=True,
        )

        await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.PHOTO_UPDATE,
            order_id=sample_order.id,
            subject="Fotos",
            body="Zwischenstand",
            photo_ids=[photo.id],
            user_id=sample_user.id,
        )

        assert PHOTO_MAX_PX == 1200
        (jpeg,) = _jpeg_parts(smtp.sent_messages[0])
        with Image.open(io.BytesIO(jpeg)) as out:
            assert max(out.size) == 1200
            assert out.size == (1200, 600)
            assert len(out.getexif()) == 0
            assert "exif" not in out.info
        assert b"SecretCameraMaker" not in jpeg


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


class TestDedupe:
    async def test_second_message_with_same_key_is_rejected(
        self, db_session, sample_order, sample_user, smtp
    ):
        key = f"test:order:{sample_order.id}:pickup"
        first = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.PICKUP_READY,
            order_id=sample_order.id,
            user_id=sample_user.id,
            dedupe_key=key,
        )
        assert first.delivered is True
        with pytest.raises(DuplicateDedupeKeyError):
            await CustomerMessageService.send_message(
                db_session,
                kind=MessageKind.PICKUP_READY,
                order_id=sample_order.id,
                user_id=sample_user.id,
                dedupe_key=key,
            )
        rows = (
            (
                await db_session.execute(
                    select(CustomerUpdate).where(CustomerUpdate.dedupe_key == key)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert len(smtp.sent_messages) == 1


# ---------------------------------------------------------------------------
# PDF_MANUAL fallback + opt-out
# ---------------------------------------------------------------------------


class TestPdfManualFallback:
    async def test_customer_without_email_gets_pdf_manual(
        self, db_session, sample_order, sample_customer, sample_user, smtp
    ):
        sample_customer.email = None
        await db_session.commit()

        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject="Stand",
            body="Text",
            user_id=sample_user.id,
        )
        assert result.delivered is False
        assert result.method == UpdateDeliveryMethod.PDF_MANUAL
        assert result.reason == "no_email"
        assert result.update.status == CustomerUpdateStatus.DRAFT
        assert smtp.sent_messages == []


class TestOptOut:
    async def test_opt_out_defaults_to_false(self, db_session, sample_customer):
        assert (
            await CustomerMessageService.is_opted_out(db_session, sample_customer.id)
            is False
        )

    async def test_opt_out_blocks_email_and_falls_back_to_pdf(
        self, db_session, sample_order, sample_customer, sample_user, smtp
    ):
        await CustomerMessageService.set_email_opt_out(
            db_session, sample_customer.id, opted_out=True, user_id=sample_user.id
        )
        assert await CustomerMessageService.is_opted_out(db_session, sample_customer.id)

        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.PICKUP_READY,
            order_id=sample_order.id,
            user_id=sample_user.id,
        )
        assert result.delivered is False
        assert result.method == UpdateDeliveryMethod.PDF_MANUAL
        assert result.reason == "opted_out"
        assert smtp.sent_messages == []

    async def test_opt_out_is_stored_as_revoked_email_contact_consent(
        self, db_session, sample_customer, sample_user
    ):
        await CustomerMessageService.set_email_opt_out(
            db_session, sample_customer.id, opted_out=True, user_id=sample_user.id
        )
        consents = await ConsentService.list_consents(db_session, sample_customer.id)
        email_rows = [
            c for c in consents if c.purpose == ConsentPurpose.EMAIL_CONTACT.value
        ]
        assert email_rows and all(c.revoked_at is not None for c in email_rows)

    async def test_lifting_the_opt_out_re_enables_email(
        self, db_session, sample_order, sample_customer, sample_user, smtp
    ):
        await CustomerMessageService.set_email_opt_out(
            db_session, sample_customer.id, opted_out=True, user_id=sample_user.id
        )
        await CustomerMessageService.set_email_opt_out(
            db_session, sample_customer.id, opted_out=False, user_id=sample_user.id
        )
        assert (
            await CustomerMessageService.is_opted_out(db_session, sample_customer.id)
            is False
        )
        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.PICKUP_READY,
            order_id=sample_order.id,
            user_id=sample_user.id,
        )
        assert result.delivered is True

    async def test_revoking_existing_email_contact_consent_opts_out(
        self, db_session, sample_customer
    ):
        await _grant(db_session, sample_customer.id, ConsentPurpose.EMAIL_CONTACT)
        assert (
            await CustomerMessageService.is_opted_out(db_session, sample_customer.id)
            is False
        )
        await ConsentService.revoke(
            db_session,
            sample_customer.id,
            ConsentPurpose.EMAIL_CONTACT,
            revoked_by_user_id=None,
        )
        await db_session.commit()
        assert await CustomerMessageService.is_opted_out(db_session, sample_customer.id)

    async def test_automated_mail_honours_opt_out(
        self, db_session, sample_order, sample_customer, sample_user, admin_user, smtp
    ):
        from datetime import datetime

        sample_order.completed_at = datetime.utcnow()
        await db_session.commit()
        await CustomerMessageService.set_email_opt_out(
            db_session, sample_customer.id, opted_out=True, user_id=sample_user.id
        )

        sent = await automated_customer_email.send_customer_mail_once(
            db_session, sample_order, NotificationTypeEnum.PICKUP_READY
        )
        assert sent is False
        assert smtp.sent_messages == []
        rows = (await db_session.execute(select(CustomerUpdate))).scalars().all()
        assert rows == []


# ---------------------------------------------------------------------------
# Footer + audit
# ---------------------------------------------------------------------------


class TestFooterAndAudit:
    async def test_every_message_carries_art13_footer_and_reply_line(
        self, db_session, sample_order, sample_user, smtp
    ):
        await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject="Stand",
            body="Text",
            user_id=sample_user.id,
        )
        plain = _plain_part(smtp.sent_messages[0])
        assert "Datenschutz" in plain
        assert "Art. 6 Abs. 1 lit. b DSGVO" in plain
        assert "Datenschutzhinweise" in plain
        assert "antworten Sie einfach auf diese E-Mail" in plain

    async def test_sent_message_writes_one_audit_row_without_body(
        self, db_session, sample_order, sample_user, smtp
    ):
        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject="Stand",
            body="GEHEIMER_TEXT",
            user_id=sample_user.id,
        )
        rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog).where(
                        CustomerAuditLog.action == "customer_message_sent"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.customer_id == sample_order.customer_id
        assert row.entity == "customer_update"
        assert row.entity_id == result.update.id
        assert row.details["message_kind"] == "status_update"
        assert row.details["delivery_method"] == "email"
        assert row.details["photo_count"] == 0
        assert row.details["legal_basis"].startswith("Art. 6(1)(b)")
        assert "GEHEIMER_TEXT" not in str(row.details)

    async def test_manual_pdf_delivery_is_audited_too(
        self, db_session, sample_order, sample_customer, sample_user, smtp
    ):
        from goldsmith_erp.services.customer_update_service import CustomerUpdateService

        sample_customer.email = None
        await db_session.commit()
        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject="Stand",
            body="Text",
            user_id=sample_user.id,
        )
        await CustomerUpdateService.mark_delivered(
            db_session, result.update.id, sample_user.id
        )
        rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog).where(
                        CustomerAuditLog.action == "customer_message_sent"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].details["delivery_method"] == "pdf_manual"


# ---------------------------------------------------------------------------
# Preview (composer)
# ---------------------------------------------------------------------------


class TestPreview:
    async def test_preview_renders_text_with_footer_and_flags(
        self, db_session, sample_order, sample_user
    ):
        preview = await CustomerMessageService.preview(
            db_session,
            order_id=sample_order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Stand",
            body="Wir polieren gerade.",
            photo_ids=[],
        )
        assert preview.subject == "Stand"
        assert "Wir polieren gerade." in preview.text
        assert "Datenschutz" in preview.text
        assert preview.delivery_method == UpdateDeliveryMethod.EMAIL
        assert preview.photo_consent is False
        assert preview.email_opt_out is False
        assert preview.blocked_reason is None

    async def test_preview_reports_missing_photo_consent_without_raising(
        self, db_session, sample_order, sample_user, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(tmp_path))
        photo = await _make_photo(db_session, tmp_path, sample_order, sample_user)
        preview = await CustomerMessageService.preview(
            db_session,
            order_id=sample_order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject=None,
            body=None,
            photo_ids=[photo.id],
        )
        assert preview.photo_count == 1
        assert preview.photo_consent is False
        assert preview.blocked_reason and "Einwilligung" in preview.blocked_reason

    async def test_preview_pdf_is_a_pdf_and_stores_nothing(
        self, db_session, sample_order, sample_user
    ):
        pdf = await CustomerMessageService.render_preview_pdf(
            db_session,
            order_id=sample_order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Stand",
            body="Wir polieren gerade.",
            photo_ids=[],
        )
        assert pdf.startswith(b"%PDF")
        rows = (await db_session.execute(select(CustomerUpdate))).scalars().all()
        assert rows == []

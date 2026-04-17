"""Scanner Pydantic schemas — contract tests.

Covers `src/goldsmith_erp/models/scanner.py` — the Slice 3 request /
response schemas. Each test pins a single behaviour so a regression
names itself when it fails.

Test-selection criteria follow the Slice 3 plan and Anna's B1
resolution brief:

* ``StrictRequestBase`` inheritance — unknown keys + audit/server
  fields rejected.
* ``raw_payload`` sanitisation — control chars stripped, null bytes
  rejected, length bounded, empty-after-strip rejected.
* ``ScanContext`` literal unions accept valid values + reject
  out-of-set ones.
* ``client_version`` regex rejects ``1.2``, accepts ``1.2.3`` and
  ``1.2.3-beta2``.
* ``idempotency_key`` accepts UUID4, rejects UUID1.
* ``ScanLogCreate.context`` pass-through validation — context
  validation still fires when nested.
* ``ResolveResponse.extra="forbid"`` — response layer cannot leak
  fields via developer drift.
* ``ScanLogBatchCreate`` cap — 101 events reject with 422.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from goldsmith_erp.models.scanner import (
    ActionItem,
    BatchLogResponse,
    ResolveRequest,
    ResolveResponse,
    ScanContext,
    ScanLogBatchCreate,
    ScanLogCreate,
)


# --------------------------------------------------------------------------- #
# ScanContext — B1 strict whitelist
# --------------------------------------------------------------------------- #


class TestScanContext:
    def test_empty_context_is_valid(self):
        """Empty ScanContext should construct cleanly with defaults."""
        ctx = ScanContext()
        # input_source default documented as "manual".
        assert ctx.input_source == "manual"
        assert ctx.running_timer_id is None
        assert ctx.current_order_id is None
        assert ctx.current_location is None
        assert ctx.device_type is None
        assert ctx.client_version is None

    def test_unknown_key_rejected(self):
        """B1 blocker: unknown key must raise 422 (extra='forbid')."""
        with pytest.raises(ValidationError) as exc:
            ScanContext.model_validate({"customer_id": 42})
        # Pydantic v2 emits "Extra inputs are not permitted" for extra.
        assert "customer_id" in str(exc.value)

    def test_input_source_valid_values(self):
        """Literal union accepts camera / usb_hid / manual."""
        for value in ("camera", "usb_hid", "manual"):
            ctx = ScanContext(input_source=value)
            assert ctx.input_source == value

    def test_input_source_invalid_rejected(self):
        with pytest.raises(ValidationError):
            ScanContext(input_source="telepathy")

    def test_device_type_valid_values(self):
        for value in ("mobile", "desktop", "tablet"):
            ctx = ScanContext(device_type=value)
            assert ctx.device_type == value

    def test_device_type_invalid_rejected(self):
        with pytest.raises(ValidationError):
            ScanContext(device_type="watch")

    def test_client_version_pattern_accepts_valid(self):
        """Pattern matches semver + optional alnum suffix."""
        for version in ("1.2.3", "1.2.3-beta2", "10.20.30-rc1"):
            ctx = ScanContext(client_version=version)
            assert ctx.client_version == version

    def test_client_version_pattern_rejects_short(self):
        """``1.2`` is not full semver and must fail."""
        with pytest.raises(ValidationError):
            ScanContext(client_version="1.2")

    def test_client_version_pattern_rejects_leading_v(self):
        """``v1.2.3`` is display-convention, not payload-legal."""
        with pytest.raises(ValidationError):
            ScanContext(client_version="v1.2.3")

    def test_current_order_id_rejects_zero(self):
        """Positive integer constraint (gt=0)."""
        with pytest.raises(ValidationError):
            ScanContext(current_order_id=0)

    def test_current_location_length_bounded(self):
        """max_length=100 guards against absurd station labels."""
        with pytest.raises(ValidationError):
            ScanContext(current_location="x" * 101)


# --------------------------------------------------------------------------- #
# ResolveRequest — control-char / null-byte / length rules
# --------------------------------------------------------------------------- #


class TestResolveRequest:
    def test_happy_path(self):
        req = ResolveRequest(raw_payload="ORDER:1")
        assert req.raw_payload == "ORDER:1"
        # Default ScanContext factory fired.
        assert req.context.input_source == "manual"

    def test_null_byte_rejected(self):
        """Explicit null-byte reject — never a legit payload."""
        with pytest.raises(ValidationError) as exc:
            ResolveRequest(raw_payload="\x00ORDER:1")
        assert "null byte" in str(exc.value).lower()

    def test_control_chars_stripped(self):
        """ASCII control chars except \\t should be stripped silently."""
        req = ResolveRequest(raw_payload="ORDER:1\r\n")
        # CR + LF stripped, payload preserved.
        assert req.raw_payload == "ORDER:1"

    def test_tab_preserved(self):
        """TAB is legitimate — barcode readers emit it as a field sep."""
        req = ResolveRequest(raw_payload="ORDER:1\tlot=42")
        assert "\t" in req.raw_payload

    def test_empty_after_strip_rejected(self):
        """Pure-control-char input is empty post-sanitise → 422."""
        with pytest.raises(ValidationError):
            ResolveRequest(raw_payload="\r\n\v")

    def test_max_length_500(self):
        """Over-500 chars must reject pre-strip."""
        with pytest.raises(ValidationError):
            ResolveRequest(raw_payload="X" * 501)

    def test_min_length_one(self):
        with pytest.raises(ValidationError):
            ResolveRequest(raw_payload="")

    def test_rejects_unknown_toplevel_key(self):
        """Top-level extra key — StrictRequestBase forbids."""
        with pytest.raises(ValidationError):
            ResolveRequest.model_validate({
                "raw_payload": "ORDER:1",
                "bogus": "x",
            })

    def test_rejects_user_id_in_body(self):
        """user_id in body is audit metadata — 422 per StrictRequestBase."""
        with pytest.raises(ValidationError) as exc:
            ResolveRequest.model_validate({
                "raw_payload": "ORDER:1",
                "user_id": 7,
            })
        assert "user_id" in str(exc.value)

    def test_nested_context_unknown_key_rejected(self):
        """B1 nested validation still fires — critical for Anna's block."""
        with pytest.raises(ValidationError) as exc:
            ResolveRequest.model_validate({
                "raw_payload": "ORDER:1",
                "context": {"customer_id": 9},
            })
        assert "customer_id" in str(exc.value)


# --------------------------------------------------------------------------- #
# ScanLogCreate — idempotency, user_id reject, pass-through context
# --------------------------------------------------------------------------- #


class TestScanLogCreate:
    def test_minimum_payload(self):
        """Only raw_payload is required."""
        log = ScanLogCreate(raw_payload="ORDER:1")
        assert log.raw_payload == "ORDER:1"
        assert log.offline_queued is False
        assert log.idempotency_key is None

    def test_uuid4_accepted(self):
        key = uuid.uuid4()
        log = ScanLogCreate(
            raw_payload="ORDER:1",
            idempotency_key=str(key),
        )
        assert str(log.idempotency_key) == str(key)

    def test_uuid1_rejected(self):
        """UUID1 contains MAC address — leaks device identity."""
        key = uuid.uuid1()
        with pytest.raises(ValidationError):
            ScanLogCreate(
                raw_payload="ORDER:1",
                idempotency_key=str(key),
            )

    def test_fallback_reason_literal(self):
        log = ScanLogCreate(
            raw_payload="ORDER:1",
            fallback_reason="camera_denied",
        )
        assert log.fallback_reason == "camera_denied"

    def test_fallback_reason_invalid_rejected(self):
        with pytest.raises(ValidationError):
            ScanLogCreate(
                raw_payload="ORDER:1",
                fallback_reason="camera_exploded",
            )

    def test_nested_context_unknown_key_rejected(self):
        with pytest.raises(ValidationError) as exc:
            ScanLogCreate.model_validate({
                "raw_payload": "ORDER:1",
                "context": {"customer_id": 9},
            })
        assert "customer_id" in str(exc.value)

    def test_user_id_in_body_rejected(self):
        """StrictRequestBase rejects payload-level user_id."""
        with pytest.raises(ValidationError) as exc:
            ScanLogCreate.model_validate({
                "raw_payload": "ORDER:1",
                "user_id": 99,
            })
        assert "user_id" in str(exc.value)

    def test_created_by_in_body_rejected(self):
        """``*_by`` suffix rejected by StrictRequestBase too."""
        with pytest.raises(ValidationError) as exc:
            ScanLogCreate.model_validate({
                "raw_payload": "ORDER:1",
                "created_by": 7,
            })
        assert "created_by" in str(exc.value)

    def test_retention_class_in_body_rejected(self):
        """Server-controlled field rejected (Slice 2 StrictRequestBase)."""
        with pytest.raises(ValidationError):
            ScanLogCreate.model_validate({
                "raw_payload": "ORDER:1",
                "retention_class": "financial_10y",
            })

    def test_control_chars_stripped_on_raw_payload(self):
        log = ScanLogCreate(raw_payload="ORDER:1\r\n")
        assert log.raw_payload == "ORDER:1"

    def test_null_byte_rejected(self):
        with pytest.raises(ValidationError):
            ScanLogCreate(raw_payload="\x00ORDER:1")


# --------------------------------------------------------------------------- #
# ScanLogBatchCreate — size cap
# --------------------------------------------------------------------------- #


class TestScanLogBatchCreate:
    def test_valid_batch(self):
        events = [
            ScanLogCreate(raw_payload=f"ORDER:{i}") for i in range(1, 6)
        ]
        batch = ScanLogBatchCreate(events=events)
        assert len(batch.events) == 5

    def test_empty_batch_rejected(self):
        """min_length=1 — a zero-event batch is pointless round-trip."""
        with pytest.raises(ValidationError):
            ScanLogBatchCreate(events=[])

    def test_too_many_events_rejected(self):
        """101 events > max_length=100 → 422."""
        events = [
            ScanLogCreate(raw_payload=f"ORDER:{i}") for i in range(101)
        ]
        with pytest.raises(ValidationError):
            ScanLogBatchCreate(events=events)


# --------------------------------------------------------------------------- #
# ResolveResponse / ActionItem — response hygiene
# --------------------------------------------------------------------------- #


class TestResolveResponseHygiene:
    def test_extra_field_rejected(self):
        """extra='forbid' on the response prevents developer drift."""
        with pytest.raises(ValidationError):
            ResolveResponse.model_validate({
                "resolved": True,
                "resolution_path": "prefix",
                "entity_type": "order",
                "entity_id": 1,
                "leaked_field": "oops",
            })

    def test_resolution_path_literal_bounds(self):
        """Only the 4 documented resolution paths are accepted."""
        for path in ("prefix", "alias", "numeric_fallback", "unknown"):
            ResolveResponse(resolved=False, resolution_path=path)
        with pytest.raises(ValidationError):
            ResolveResponse(resolved=False, resolution_path="magic")


class TestActionItemHygiene:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            ActionItem.model_validate({
                "id": "x",
                "label": "y",
                "icon": "z",
                "mystery": True,
            })

    def test_label_length_bounded(self):
        """Long labels break tablet-portrait layouts — hard cap at 100."""
        with pytest.raises(ValidationError):
            ActionItem(id="x", label="y" * 101, icon="z")


# --------------------------------------------------------------------------- #
# BatchLogResponse — non-negative counts
# --------------------------------------------------------------------------- #


class TestBatchLogResponse:
    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            BatchLogResponse(
                ingested=-1,
                deduplicated=0,
                rejected=0,
                reasons=[],
            )

    def test_reasons_capped(self):
        """max_length=10 on reasons list — spec §8.a defence-in-depth."""
        with pytest.raises(ValidationError):
            BatchLogResponse(
                ingested=0,
                deduplicated=0,
                rejected=20,
                reasons=["r"] * 11,
            )

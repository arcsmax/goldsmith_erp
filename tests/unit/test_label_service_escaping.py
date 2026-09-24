"""Printable labels must HTML-escape every stored value (SEC-07).

Order titles, repair descriptions, customer names and the workshop name are
user-controlled. Interpolating them raw into the label document allowed stored
HTML injection (forms, meta refresh) on a same-origin page an admin prints.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from goldsmith_erp.services.label_service import LabelService

PAYLOAD = '<form action="/api/v1/x"><button>Drucken</button></form>'
ESCAPED = "&lt;form action=&quot;/api/v1/x&quot;&gt;"
META = '<meta http-equiv="refresh" content="0;url=https://evil.test">'


def _customer():
    return SimpleNamespace(first_name=META, last_name="<b>Kunde</b>")


def _assert_no_raw_payload(html: str) -> None:
    assert PAYLOAD not in html
    assert META not in html
    assert "<b>Kunde</b>" not in html
    assert "<script>alert" not in html


def test_order_label_escapes_title_customer_and_workshop():
    order = SimpleNamespace(
        id=42,
        title=PAYLOAD,
        deadline=date(2026, 10, 1),
        ring_size_mm="<i>54</i>",
        status="<script>alert(1)</script>",
    )

    html = LabelService.generate_order_label_html(
        order, _customer(), workshop_name="<script>alert(2)</script>"
    )

    _assert_no_raw_payload(html)
    assert ESCAPED in html
    assert "&lt;b&gt;Kunde&lt;/b&gt;" in html
    assert "<i>54</i>" not in html
    assert "Auftrag #42" in html


def test_repair_label_escapes_description_bag_and_customer():
    repair = SimpleNamespace(
        id=7,
        item_description=PAYLOAD,
        bag_number='"><img src=x>',
        estimated_completion=None,
        deadline=None,
    )

    html = LabelService.generate_repair_label_html(
        repair, _customer(), workshop_name="Werkstatt & Co"
    )

    _assert_no_raw_payload(html)
    assert ESCAPED in html
    assert '"><img src=x>' not in html
    assert "Werkstatt &amp; Co" in html


@pytest.mark.parametrize("value", ["Ring 750 Gelbgold", "Kette ä ö ü ß"])
def test_plain_titles_render_unchanged(value: str):
    order = SimpleNamespace(
        id=1, title=value, deadline=None, ring_size_mm=None, status="draft"
    )

    html = LabelService.generate_order_label_html(order, None)

    assert value in html

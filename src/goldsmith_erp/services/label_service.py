# src/goldsmith_erp/services/label_service.py
"""
Label generation service for QR-code-enabled order labels.

Produces printable HTML documents sized for standard label paper
(89x36mm Dymo/Zebra compatible, or A7 for desk printers).  The QR
code encodes the canonical payload used by ScannerPage so the
scanner → label → re-scan loop closes without any additional
configuration.

QR payload format:
  Orders:  ORDER:<id>      e.g. "ORDER:42"
  Repairs: REPAIR:<id>     (reserved for future repair entity)
"""

import io


class LabelService:
    """Generate printable HTML labels with embedded QR codes."""

    # ------------------------------------------------------------------ #
    # QR helpers                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate_qr_svg(data: str, scale: int = 4) -> str:
        """Return an inline SVG string for *data*.

        The SVG has no fixed width/height so it scales to its container
        via CSS without distortion artifacts.
        """
        import segno

        qr = segno.make(data, error="M")
        buffer = io.BytesIO()
        qr.save(buffer, kind="svg", scale=scale, border=1, svgclass=None, nl=False)
        svg = buffer.getvalue().decode("utf-8")
        # Strip the XML declaration so the string embeds cleanly in HTML
        if svg.startswith("<?xml"):
            svg = svg[svg.index("<svg"):]
        return svg

    # ------------------------------------------------------------------ #
    # Label CSS / layout                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _base_css(label_width_mm: int = 89, label_height_mm: int = 36) -> str:
        """Return the shared CSS for all label types."""
        return f"""
        <style>
          @page {{
            size: {label_width_mm}mm {label_height_mm}mm;
            margin: 0;
          }}

          * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
          }}

          body {{
            width: {label_width_mm}mm;
            height: {label_height_mm}mm;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            background: #fff;
            color: #111;
            overflow: hidden;
          }}

          .label {{
            display: flex;
            flex-direction: row;
            align-items: stretch;
            width: 100%;
            height: 100%;
            padding: 2mm;
            gap: 2mm;
          }}

          /* QR code column */
          .label-qr {{
            flex: 0 0 auto;
            width: {label_height_mm - 4}mm;   /* square: height minus padding */
            display: flex;
            align-items: center;
            justify-content: center;
          }}

          .label-qr svg {{
            width: 100%;
            height: 100%;
          }}

          /* Divider */
          .label-divider {{
            width: 0.3mm;
            background: #ccc;
            flex-shrink: 0;
          }}

          /* Text column */
          .label-body {{
            flex: 1 1 auto;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            overflow: hidden;
            min-width: 0;
          }}

          .label-workshop {{
            font-size: 5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #b45309;   /* amber-700 — goldsmith brand */
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}

          .label-order-number {{
            font-size: 9pt;
            font-weight: 700;
            color: #111;
            white-space: nowrap;
          }}

          .label-title {{
            font-size: 6.5pt;
            font-weight: 600;
            color: #333;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}

          .label-meta {{
            font-size: 5.5pt;
            color: #555;
            display: flex;
            flex-direction: column;
            gap: 0.5mm;
          }}

          .label-meta-row {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}

          .label-meta-row strong {{
            color: #333;
          }}

          .label-status {{
            font-size: 4.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #6b7280;
            margin-top: auto;
          }}

          @media print {{
            body {{
              -webkit-print-color-adjust: exact;
              print-color-adjust: exact;
            }}
          }}
        </style>
        """

    @staticmethod
    def _html_wrapper(title: str, css: str, body: str) -> str:
        """Wrap label content in a complete, self-contained HTML document."""
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  {css}
  <script>
    // Auto-trigger print dialog; close tab on cancel/done.
    window.addEventListener('load', function () {{
      window.print();
    }});
  </script>
</head>
<body>
{body}
</body>
</html>"""

    # ------------------------------------------------------------------ #
    # Order label                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate_order_label_html(
        order: object,
        customer: object | None,
        workshop_name: str = "Goldschmiede",
        label_width_mm: int = 89,
        label_height_mm: int = 36,
    ) -> str:
        """Generate a printable HTML label for *order*.

        Parameters
        ----------
        order:
            SQLAlchemy Order ORM instance (or any object with the
            standard Order attributes).
        customer:
            SQLAlchemy Customer ORM instance, or None.
        workshop_name:
            Business name printed at the top of the label.
        label_width_mm / label_height_mm:
            Label paper dimensions in millimetres.
            Default 89x36mm covers Dymo 99010 / Zebra ZD-series labels.
        """
        qr_payload = f"ORDER:{order.id}"  # type: ignore[union-attr]
        qr_svg = LabelService.generate_qr_svg(qr_payload)

        # Customer display name (PII — used only for rendered HTML,
        # never logged)
        if customer:
            customer_name = f"{customer.first_name} {customer.last_name}".strip()
        else:
            customer_name = "—"

        # Deadline
        deadline_str = "—"
        if order.deadline:  # type: ignore[union-attr]
            try:
                deadline_str = order.deadline.strftime("%d.%m.%Y")  # type: ignore[union-attr]
            except AttributeError:
                deadline_str = str(order.deadline)  # type: ignore[union-attr]

        # Ring size
        ring_size_str = ""
        ring_size = getattr(order, "ring_size_mm", None)
        if ring_size:
            ring_size_str = f"Ringmaß: {ring_size}mm"

        # Status label
        status_labels: dict[str, str] = {
            "draft": "Entwurf",
            "confirmed": "Bestätigt",
            "in_progress": "In Bearbeitung",
            "waiting_for_fitting": "Wartet auf Anprobe",
            "fitting_done": "Anprobe abgeschlossen",
            "ready_for_setting": "Bereit für Steinbesatz",
            "quality_check": "Endkontrolle",
            "completed": "Fertiggestellt",
            "delivered": "Ausgeliefert",
            "new": "Neu",
        }
        raw_status = order.status  # type: ignore[union-attr]
        status_value = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
        status_display = status_labels.get(status_value, status_value)

        css = LabelService._base_css(label_width_mm, label_height_mm)

        body = f"""
<div class="label">
  <div class="label-qr">
    {qr_svg}
  </div>
  <div class="label-divider"></div>
  <div class="label-body">
    <div class="label-workshop">{workshop_name}</div>
    <div class="label-order-number">Auftrag #{order.id}</div>
    <div class="label-title">{order.title}</div>
    <div class="label-meta">
      <div class="label-meta-row"><strong>Kunde:</strong> {customer_name}</div>
      <div class="label-meta-row"><strong>Deadline:</strong> {deadline_str}</div>
      {f'<div class="label-meta-row">{ring_size_str}</div>' if ring_size_str else ''}
    </div>
    <div class="label-status">{status_display}</div>
  </div>
</div>"""

        return LabelService._html_wrapper(
            title=f"Etikett – Auftrag #{order.id}",  # type: ignore[union-attr]
            css=css,
            body=body,
        )

    # ------------------------------------------------------------------ #
    # Repair label (reserved for future Repair entity)                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate_repair_label_html(
        repair: object,
        customer: object | None,
        workshop_name: str = "Goldschmiede",
        label_width_mm: int = 89,
        label_height_mm: int = 36,
    ) -> str:
        """Generate a printable HTML label for a repair job.

        Uses the same 89x36mm format as order labels.  The QR payload
        is ``REPAIR:<id>`` so the scanner can distinguish repair from
        order scans.
        """
        qr_payload = f"REPAIR:{repair.id}"  # type: ignore[union-attr]
        qr_svg = LabelService.generate_qr_svg(qr_payload)

        if customer:
            customer_name = f"{customer.first_name} {customer.last_name}".strip()
        else:
            customer_name = "—"

        est_completion = "—"
        completion_date = getattr(repair, "estimated_completion", None) or getattr(
            repair, "deadline", None
        )
        if completion_date:
            try:
                est_completion = completion_date.strftime("%d.%m.%Y")
            except AttributeError:
                est_completion = str(completion_date)

        bag_number = getattr(repair, "bag_number", None) or getattr(repair, "id", "—")
        item_description = getattr(repair, "item_description", None) or getattr(
            repair, "description", "—"
        )

        css = LabelService._base_css(label_width_mm, label_height_mm)

        body = f"""
<div class="label">
  <div class="label-qr">
    {qr_svg}
  </div>
  <div class="label-divider"></div>
  <div class="label-body">
    <div class="label-workshop">{workshop_name}</div>
    <div class="label-order-number">Reparatur #{repair.id} · Beutel {bag_number}</div>
    <div class="label-title">{item_description}</div>
    <div class="label-meta">
      <div class="label-meta-row"><strong>Kunde:</strong> {customer_name}</div>
      <div class="label-meta-row"><strong>Fertig ca.:</strong> {est_completion}</div>
    </div>
  </div>
</div>"""

        return LabelService._html_wrapper(
            title=f"Etikett – Reparatur #{repair.id}",  # type: ignore[union-attr]
            css=css,
            body=body,
        )

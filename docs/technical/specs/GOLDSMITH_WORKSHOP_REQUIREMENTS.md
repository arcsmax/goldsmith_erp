# Goldsmith Workshop Requirements - Domain-Specific Features
**Datum:** 2025-11-09
**Status:** Requirements Analysis & Gap Identification
**Priorität:** CRITICAL for Production Use

---

## Executive Summary

Dieses Dokument definiert **Goldschmied-spezifische Requirements**, die in einem Standard-ERP NICHT vorhanden sind, aber für eine Goldschmiedewerkstatt **essentiell** sind.

**Problem:** Das aktuelle System ist ein generisches ERP. Es fehlen kritische Domänen-Features, die ein Goldschmied TÄGLICH braucht.

---

## 🏆 CRITICAL MISSING FEATURES (Dealbreakers)

### 1. Edelmetall-Preisverwaltung & Kursintegration

**Warum kritisch?**
Gold-, Silber- und Platin-Preise schwanken **TÄGLICH**. Ein Goldschmied MUSS aktuelle Kurse kennen, um:
- Materialkosten zu kalkulieren
- Verkaufspreise anzupassen
- Profitabilität zu gewährleisten

**Aktueller Status:** ❌ FEHLT KOMPLETT

**Required Features:**
```yaml
Edelmetall-Preise:
  - Täglicher automatischer Import von Kursen (API: Kitco, Bullion Vault, LBMA)
  - Währungsumrechnung (USD → EUR)
  - Historische Kursdaten (für Preisanalyse)
  - Preisalarme (z.B. "Gold über 2000€/Unze")

Materialien erweitern:
  - Reinheitsgrad (24K, 18K, 14K, 925 Silber, 950 Platin)
  - Dichte (g/cm³) für Gewichtsberechnung
  - Aktueller Marktpreis (automatisch aktualisiert)
  - Aufschlag % (z.B. +15% auf Großhandelspreis)
  - Verarbeitungskosten (€/g)
```

**Database Schema:**
```sql
CREATE TABLE metal_prices (
    id SERIAL PRIMARY KEY,
    metal_type VARCHAR(50) NOT NULL, -- 'gold', 'silver', 'platinum', 'palladium'
    purity VARCHAR(20) NOT NULL,     -- '24K', '18K', '14K', '925', '950'
    price_per_gram DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'EUR',
    source VARCHAR(100),              -- API source
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(metal_type, purity, fetched_at::date)
);

CREATE INDEX idx_metal_prices_latest ON metal_prices(metal_type, purity, fetched_at DESC);
```

**API Endpoint:**
```python
GET /api/v1/metals/prices?metal=gold&purity=18K
GET /api/v1/metals/prices/history?metal=gold&days=30
POST /api/v1/metals/prices/sync  # Admin only - force refresh
```

**Implementation Priority:** 🚨 **P0 - CRITICAL**
**Estimated Effort:** 2-3 days

---

### 2. Gewichtsberechnung & Materialverbrauch

**Warum kritisch?**
Ein Ring aus 18K Gold mit 5g kostet völlig anders als 3g. Gewicht = Materialkosten!

**Aktueller Status:** ❌ FEHLT KOMPLETT

**Required Features:**
```yaml
Auftrag:
  - Geschätztes Gewicht (vom Goldschmied eingegeben)
  - Tatsächliches Gewicht (nach Fertigstellung gewogen)
  - Materialverbrauch-Tracking (Material IN vs. OUT)
  - Verschnitt-Berechnung (z.B. 5% Verlust beim Schmelzen)

Kalkulation:
  - Automatische Berechnung: Gewicht × Preis/g = Materialkosten
  - Manuelle Überschreibung möglich
  - Historischer Preis (zum Zeitpunkt der Auftragsannahme)
  - Aktueller Preis (zur Echtzeit-Kalkulation)
```

**Database Schema:**
```sql
ALTER TABLE orders ADD COLUMN estimated_weight_g DECIMAL(8,3);
ALTER TABLE orders ADD COLUMN actual_weight_g DECIMAL(8,3);
ALTER TABLE orders ADD COLUMN material_cost_calculated DECIMAL(10,2);
ALTER TABLE orders ADD COLUMN material_cost_override DECIMAL(10,2);
ALTER TABLE orders ADD COLUMN scrap_percentage DECIMAL(5,2) DEFAULT 5.0;

CREATE TABLE material_usage (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    material_id INTEGER REFERENCES materials(id),
    weight_used_g DECIMAL(8,3) NOT NULL,
    price_per_gram DECIMAL(10,2) NOT NULL,  -- Price at time of use
    total_cost DECIMAL(10,2) GENERATED ALWAYS AS (weight_used_g * price_per_gram) STORED,
    used_at TIMESTAMP DEFAULT NOW()
);
```

**Implementation Priority:** 🚨 **P0 - CRITICAL**
**Estimated Effort:** 2 days

---

### 3. Kosten-Kalkulation & Preisfindung

**Warum kritisch?**
Wie viel kostet ein Auftrag? Material + Arbeitszeit + Gewinnmarge = Verkaufspreis

**Aktueller Status:** ⚠️ TEILWEISE (nur manuelle Preiseingabe)

**Required Features:**
```yaml
Automatische Kalkulation:
  Material-Kosten:
    - Gewicht × Materialpreis
    - + Edelsteine (falls vorhanden)
    - + Verarbeitungskosten

  Arbeitszeit-Kosten:
    - Erfasste Zeit × Stundensatz
    - Oder Pauschale pro Auftragstyp

  Gewinnmarge:
    - Prozentsatz (z.B. 40% Marge)
    - Oder fixer Betrag

  Endpreis:
    - Material + Arbeit + Marge + MwSt = Verkaufspreis
    - Runden auf .00 oder .99
```

**Database Schema:**
```sql
ALTER TABLE orders ADD COLUMN labor_hours DECIMAL(8,2);
ALTER TABLE orders ADD COLUMN hourly_rate DECIMAL(10,2) DEFAULT 75.00;
ALTER TABLE orders ADD COLUMN labor_cost DECIMAL(10,2)
    GENERATED ALWAYS AS (labor_hours * hourly_rate) STORED;

ALTER TABLE orders ADD COLUMN profit_margin_percent DECIMAL(5,2) DEFAULT 40.0;
ALTER TABLE orders ADD COLUMN vat_rate DECIMAL(5,2) DEFAULT 19.0;

ALTER TABLE orders ADD COLUMN calculated_price DECIMAL(10,2);
ALTER TABLE orders ADD COLUMN final_price DECIMAL(10,2);  -- Can be manually overridden

CREATE TABLE gemstones (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    type VARCHAR(50) NOT NULL,  -- 'diamond', 'ruby', 'sapphire', etc.
    carat DECIMAL(6,3),
    quality VARCHAR(20),         -- 'VS1', 'VVS2', etc.
    cost DECIMAL(10,2) NOT NULL,
    quantity INTEGER DEFAULT 1
);
```

**Calculation Function:**
```python
def calculate_order_price(order_id):
    """
    Automatic price calculation for goldsmith orders
    """
    # 1. Material costs (metal weight × price)
    material_cost = sum(usage.total_cost for usage in order.material_usage)

    # 2. Gemstone costs
    gemstone_cost = sum(gem.cost * gem.quantity for gem in order.gemstones)

    # 3. Labor costs (time entries × hourly rate)
    labor_cost = order.labor_hours * order.hourly_rate

    # 4. Total before margin
    subtotal = material_cost + gemstone_cost + labor_cost

    # 5. Add profit margin
    total_with_margin = subtotal * (1 + order.profit_margin_percent / 100)

    # 6. Add VAT
    total_with_vat = total_with_margin * (1 + order.vat_rate / 100)

    # 7. Round to .00 or .99
    final_price = round_to_99(total_with_vat)

    return {
        'material_cost': material_cost,
        'gemstone_cost': gemstone_cost,
        'labor_cost': labor_cost,
        'subtotal': subtotal,
        'margin': total_with_margin - subtotal,
        'vat': total_with_vat - total_with_margin,
        'final_price': final_price
    }
```

**Implementation Priority:** 🚨 **P0 - CRITICAL**
**Estimated Effort:** 3 days

---

### 4. Tresor-Management & Sicherheit

**Warum kritisch?**
Goldschmiede haben WERTVOLLES Material (Gold, Edelsteine). Tresor-Tracking ist essentiell!

**Aktueller Status:** ⚠️ TEILWEISE (nur "current_location")

**Required Features:**
```yaml
Sicherheitsbereiche:
  - Tresor (verschiedene Ebenen: A, B, C)
  - Werkbank (offen zugänglich)
  - Vitrine (Kundenbereich)
  - Lager (weniger wertvoll)

Zugangskontrolle:
  - Wer darf Tresor öffnen? (Admin-Level)
  - Audit Log: Wer hat wann was in/aus Tresor genommen
  - Automatische Alerts bei ungewöhnlichen Bewegungen

Inventur:
  - Regelmäßige Bestandsaufnahme
  - Sollwert vs. Istwert
  - Differenzen-Tracking
```

**Database Schema:**
```sql
CREATE TABLE storage_locations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'vault', 'workbench', 'showcase', 'storage'
    security_level INTEGER DEFAULT 1,  -- 1=low, 5=high (vault)
    requires_permission BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE location_history ADD COLUMN access_granted BOOLEAN DEFAULT TRUE;
ALTER TABLE location_history ADD COLUMN access_reason TEXT;

CREATE TABLE vault_access_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(50) NOT NULL,  -- 'open', 'close', 'item_added', 'item_removed'
    order_id INTEGER REFERENCES orders(id),
    timestamp TIMESTAMP DEFAULT NOW(),
    notes TEXT
);
```

**Implementation Priority:** 🔴 **P1 - HIGH**
**Estimated Effort:** 2 days

---

### 5. Kundenhistorie & Präferenzen

**Warum kritisch?**
Stammkunden haben Vorlieben! "Frau Müller mag nur 18K Roségold."

**Aktueller Status:** ⚠️ TEILWEISE (Customer model existiert, aber keine Historie)

**Required Features:**
```yaml
Kundenhistorie:
  - Alle bisherigen Aufträge auf einen Blick
  - Gesamtumsatz (lifetime value)
  - Durchschnittliche Auftragswert
  - Letzte Interaktion

Präferenzen:
  - Bevorzugtes Material (z.B. "18K Gelbgold")
  - Bevorzugte Stile (z.B. "Modern, minimalistisch")
  - Ringgrößen (wichtig für Ringe!)
  - Allergien (z.B. "Nickel-Allergie")

Kommunikationslog:
  - Telefonate, Emails, Besuche
  - Notizen zu Gesprächen
  - Erinnerungen (z.B. "Hochzeitstag in 3 Wochen")
```

**Database Schema:**
```sql
CREATE TABLE customer_preferences (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    preferred_metal VARCHAR(50),   -- '18K Yellow Gold'
    preferred_style VARCHAR(100),  -- 'Modern, Minimalist'
    ring_size VARCHAR(10),         -- 'US 7', 'EU 54'
    allergies TEXT[],              -- Array of allergies
    notes TEXT
);

CREATE TABLE customer_communications (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    type VARCHAR(50) NOT NULL,  -- 'phone', 'email', 'visit', 'note'
    subject VARCHAR(200),
    content TEXT,
    user_id INTEGER REFERENCES users(id),  -- Who logged this
    logged_at TIMESTAMP DEFAULT NOW()
);

-- Customer lifetime metrics (computed view)
CREATE VIEW customer_metrics AS
SELECT
    c.id AS customer_id,
    COUNT(o.id) AS total_orders,
    SUM(o.price) AS lifetime_value,
    AVG(o.price) AS average_order_value,
    MAX(o.created_at) AS last_order_date,
    MIN(o.created_at) AS first_order_date
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id;
```

**Implementation Priority:** 🔴 **P1 - HIGH**
**Estimated Effort:** 2 days

---

### 6. Rechnungsstellung & Zahlungsverfolgung

**Warum kritisch?**
Ohne Rechnung = kein Geld! BUSINESS BLOCKER!

**Aktueller Status:** ❌ FEHLT KOMPLETT

**Required Features:**
```yaml
Rechnung-Generierung:
  - PDF-Export (professionelles Layout)
  - Rechtliche Pflichtangaben (Deutschland):
    - Rechnungsnummer (fortlaufend)
    - Steuernummer / USt-IdNr
    - Leistungsdatum
    - MwSt-Ausweis (19% oder 7%)
  - Rechnungsadresse vs. Lieferadresse
  - Zahlungsbedingungen (z.B. "14 Tage netto")

Zahlungsverfolgung:
  - Status: Offen, Teilzahlung, Bezahlt
  - Zahlungsdatum
  - Zahlungsmethode (Bar, Überweisung, Karte)
  - Automatische Mahnungen (nach 14, 30, 45 Tagen)
```

**Database Schema:**
```sql
CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,  -- 'INV-2025-001'
    order_id INTEGER REFERENCES orders(id),
    customer_id INTEGER REFERENCES customers(id),

    -- Amounts
    subtotal DECIMAL(10,2) NOT NULL,
    vat_amount DECIMAL(10,2) NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,

    -- Status
    status VARCHAR(50) DEFAULT 'draft',  -- 'draft', 'sent', 'paid', 'overdue', 'cancelled'
    issued_at DATE NOT NULL,
    due_date DATE NOT NULL,
    paid_at DATE,

    -- Payment
    payment_method VARCHAR(50),  -- 'cash', 'transfer', 'card'
    payment_reference VARCHAR(100),

    -- Legal
    tax_id VARCHAR(50),  -- Steuernummer
    vat_id VARCHAR(50),  -- USt-IdNr

    -- PDF
    pdf_path VARCHAR(500),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    description TEXT NOT NULL,
    quantity DECIMAL(8,2) DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    vat_rate DECIMAL(5,2) NOT NULL,
    total DECIMAL(10,2) GENERATED ALWAYS AS (quantity * unit_price) STORED
);

CREATE TABLE payment_reminders (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    reminder_level INTEGER NOT NULL,  -- 1, 2, 3
    sent_at TIMESTAMP NOT NULL,
    method VARCHAR(50),  -- 'email', 'mail', 'phone'
    notes TEXT
);
```

**PDF Generation:**
```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def generate_invoice_pdf(invoice_id: int) -> str:
    """
    Generate professional invoice PDF
    """
    invoice = get_invoice(invoice_id)

    pdf_path = f"/invoices/INV-{invoice.invoice_number}.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)

    # Header
    c.drawString(50, 800, "Goldschmiede Mustermann GmbH")
    c.drawString(50, 785, "Musterstraße 123, 12345 Musterstadt")
    c.drawString(50, 770, f"Steuernummer: {invoice.tax_id}")

    # Invoice number & date
    c.drawString(400, 800, f"Rechnung Nr.: {invoice.invoice_number}")
    c.drawString(400, 785, f"Datum: {invoice.issued_at}")
    c.drawString(400, 770, f"Fällig: {invoice.due_date}")

    # Customer address
    c.drawString(50, 700, f"{invoice.customer.first_name} {invoice.customer.last_name}")
    c.drawString(50, 685, f"{invoice.customer.street}")
    c.drawString(50, 670, f"{invoice.customer.postal_code} {invoice.customer.city}")

    # Line items table
    y = 600
    c.drawString(50, y, "Pos.")
    c.drawString(100, y, "Beschreibung")
    c.drawString(350, y, "Menge")
    c.drawString(420, y, "Preis")
    c.drawString(500, y, "Summe")

    y -= 20
    for i, item in enumerate(invoice.items):
        c.drawString(50, y, str(i+1))
        c.drawString(100, y, item.description[:40])
        c.drawString(350, y, str(item.quantity))
        c.drawString(420, y, f"{item.unit_price:.2f} €")
        c.drawString(500, y, f"{item.total:.2f} €")
        y -= 15

    # Totals
    y -= 20
    c.drawString(420, y, "Zwischensumme:")
    c.drawString(500, y, f"{invoice.subtotal:.2f} €")
    y -= 15
    c.drawString(420, y, f"MwSt ({invoice.vat_rate}%):")
    c.drawString(500, y, f"{invoice.vat_amount:.2f} €")
    y -= 15
    c.drawString(420, y, "Gesamtbetrag:")
    c.drawString(500, y, f"{invoice.total_amount:.2f} €")

    # Payment terms
    c.drawString(50, 150, f"Zahlbar bis {invoice.due_date} ohne Abzug.")

    c.save()
    return pdf_path
```

**Implementation Priority:** 🚨 **P0 - CRITICAL**
**Estimated Effort:** 4-5 days

---

### 7. Edelstein-Verwaltung

**Warum kritisch?**
Viele Goldschmied-Aufträge beinhalten Edelsteine (Diamanten, Saphire, etc.)

**Aktueller Status:** ❌ FEHLT KOMPLETT

**Required Features:**
```yaml
Edelstein-Katalog:
  - Typ (Diamant, Rubin, Saphir, Smaragd, etc.)
  - Karat (Gewicht)
  - Qualität (4C: Cut, Clarity, Color, Carat)
  - Zertifikat (GIA, IGI, HRD)
  - Einkaufspreis
  - Verkaufspreis

Zuordnung zu Aufträgen:
  - Mehrere Edelsteine pro Auftrag
  - Fassungs-Art (Krappenfassung, Zargen, etc.)
  - Kosten-Kalkulation einbeziehen
```

**Database Schema:**
```sql
CREATE TABLE gemstones_catalog (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50) NOT NULL,  -- 'diamond', 'ruby', 'sapphire', 'emerald'
    carat DECIMAL(6,3),
    cut VARCHAR(50),           -- 'Excellent', 'Very Good', 'Good'
    clarity VARCHAR(20),       -- 'IF', 'VVS1', 'VVS2', 'VS1', 'VS2'
    color VARCHAR(20),         -- 'D', 'E', 'F' (for diamonds)
    shape VARCHAR(50),         -- 'Round', 'Princess', 'Oval'
    certificate_number VARCHAR(100),
    certificate_authority VARCHAR(50),  -- 'GIA', 'IGI'
    purchase_price DECIMAL(10,2),
    selling_price DECIMAL(10,2),
    in_stock BOOLEAN DEFAULT TRUE,
    location VARCHAR(100),
    notes TEXT
);

-- Already created above, but included for completeness:
CREATE TABLE gemstones (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    catalog_id INTEGER REFERENCES gemstones_catalog(id),
    type VARCHAR(50) NOT NULL,
    carat DECIMAL(6,3),
    quality VARCHAR(20),
    cost DECIMAL(10,2) NOT NULL,
    quantity INTEGER DEFAULT 1,
    setting_type VARCHAR(100)  -- 'Prong', 'Bezel', 'Channel', etc.
);
```

**Implementation Priority:** 🟡 **P2 - MEDIUM**
**Estimated Effort:** 2 days

---

## 🔍 Architecture Deep Dive: Missing Components

### Current Architecture (What We Have):

```
┌─────────────────────────────────────────────────────────────┐
│                     CURRENT SYSTEM                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ User Management (Auth, RBAC)                           │
│  ✅ Order Management (CRUD, Status, Materials)             │
│  ✅ Customer Management (CRM - NEW!)                        │
│  ✅ Time Tracking (Backend - Phase 5.1)                    │
│  ✅ Material Management (Basic CRUD)                        │
│  ✅ Location Tracking (current_location, history)          │
│  ✅ Photo Documentation (DB schema)                         │
│  ✅ Real-time Updates (WebSocket, Redis Pub/Sub)           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Target Architecture (What Goldsmith Workshop Needs):

```
┌─────────────────────────────────────────────────────────────┐
│               GOLDSMITH WORKSHOP ERP                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ User Management                                         │
│  ✅ Order Management                                        │
│  ✅ Customer Management + ❌ Historie + ❌ Präferenzen      │
│  ✅ Time Tracking (Backend) + ❌ Frontend UI                │
│  ⚠️  Material Management + ❌ Edelmetall-Kurse              │
│  ✅ Location Tracking + ❌ Tresor-Management                │
│  ✅ Photo Documentation (DB) + ❌ Frontend Upload           │
│  ❌ Edelstein-Verwaltung (NEU)                              │
│  ❌ Gewichtsberechnung (NEU)                                │
│  ❌ Kosten-Kalkulation (NEU)                                │
│  ❌ Rechnungsstellung (NEU)                                 │
│  ❌ Zahlungsverfolgung (NEU)                                │
│  ❌ Kalender/Timeline (NEU)                                 │
│  ❌ Reports & Analytics (NEU)                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Feature Priority Matrix

| Feature | Business Impact | Technical Complexity | Priority | Effort |
|---------|----------------|---------------------|----------|--------|
| **Rechnungsstellung** | 🚨 CRITICAL | Medium | P0 | 5 days |
| **Edelmetall-Kurse** | 🚨 CRITICAL | Low | P0 | 3 days |
| **Gewichtsberechnung** | 🚨 CRITICAL | Low | P0 | 2 days |
| **Kosten-Kalkulation** | 🚨 CRITICAL | Medium | P0 | 3 days |
| **Kalender-View** | 🔴 HIGH | Medium | P1 | 3 days |
| **Kundenhistorie** | 🔴 HIGH | Low | P1 | 2 days |
| **Tresor-Management** | 🔴 HIGH | Medium | P1 | 2 days |
| **Time-Tracking UI** | 🔴 HIGH | High | P1 | 4 days |
| **Zahlungsverfolgung** | 🔴 HIGH | Low | P1 | 2 days |
| **Edelstein-Verwaltung** | 🟡 MEDIUM | Medium | P2 | 2 days |
| **Reports & Analytics** | 🟡 MEDIUM | High | P2 | 5 days |
| **Photo Upload UI** | 🟡 MEDIUM | Low | P2 | 1 day |

**Total P0 Effort:** ~13 days
**Total P1 Effort:** ~17 days
**Total P2 Effort:** ~8 days

**Grand Total:** ~38 days (≈ 8 weeks with 1 developer)

---

## 🎯 Recommended Implementation Roadmap

### Phase 2.2: Core Business Functions (2 weeks)
- ✅ Customer CRM (DONE!)
- ⏳ Gewichtsberechnung & Materialverbrauch
- ⏳ Kosten-Kalkulation
- ⏳ Rechnungsstellung & PDF

### Phase 2.3: Edelmetall-Integration (1 week)
- ⏳ Edelmetall-Kurse API Integration
- ⏳ Material-Erweiterung (Reinheitsgrad, Dichte)
- ⏳ Automatische Preis-Updates

### Phase 2.4: Frontend Completion (2 weeks)
- ⏳ Time-Tracking UI
- ⏳ Kalender-View
- ⏳ Customer Frontend Pages
- ⏳ Photo Upload

### Phase 2.5: Security & Value (1 week)
- ⏳ Tresor-Management
- ⏳ Zahlungsverfolgung
- ⏳ Kundenhistorie & Präferenzen

### Phase 3: Advanced Features (2 weeks)
- ⏳ Edelstein-Verwaltung
- ⏳ Reports & Analytics
- ⏳ ML-Zeitschätzung

---

## 🚀 Quick Wins (< 1 Day Each)

1. **Deadline-Feld** - ✅ DONE (Phase 2.1)
2. **Customer-Order-Link** - ✅ DONE (Phase 2.1)
3. **Order Weight Fields** - ADD: `estimated_weight_g`, `actual_weight_g`
4. **Payment Status Field** - ADD: `payment_status` to orders
5. **Invoice Number Generator** - Simple sequential numbering

---

## 📝 Next Steps

1. **Review & Approve** this requirements document
2. **Prioritize** features with business stakeholder
3. **Create Jira/GitHub Issues** for each feature
4. **Start with P0 features** (Invoicing, Metal Prices, Weight Calculation)

---

**Autor:** Claude (AI Assistant)
**Review:** Pending
**Status:** Draft → Ready for Implementation

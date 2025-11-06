# Goldsmith ERP - System Architecture

## Table of Contents

1. [Vision & Goals](#vision--goals)
2. [Cross-Platform Strategy](#cross-platform-strategy)
3. [Tag System Architecture](#tag-system-architecture)
4. [Template Engine](#template-engine)
5. [Workflow Engine](#workflow-engine)
6. [Data Model](#data-model)
7. [Technology Stack](#technology-stack)
8. [Security & Performance](#security--performance)

---

## Vision & Goals

### Core Vision
Ein universelles, templatebasiertes Tracking-System für Goldschmieden, das physische Assets (Schmuckstücke, Rohmaterialien, Edelsteine, Werkzeuge) mittels **NFC und QR-Code Tags** erfasst und über **dynamische Workflows** verwaltet.

### Key Principles

1. **Universal Tracking**: Jedes physische Objekt erhält einen Tag mit NFC-Chip UND QR-Code (beide mit identischer Information)
2. **Template-Driven**: Unterschiedliche Entity-Typen (Schmuck, Material, Werkzeug) haben eigene, anpassbare Templates
3. **Cross-Platform**: Funktioniert auf Android, iOS, Windows, macOS
4. **Dynamic Workflows**: Formulare und Prozesse passen sich automatisch an Kontext und Daten an
5. **Integrated Operations**: Stock-Management, Preiskalkulation, Task-Creation sind direkt in Workflows integriert

### Business Use Cases

#### Use Case 1: Schmuck-Reparatur-Auftrag
```
Kunde bringt Ring zur Reinigung und Steinersatz
  → Goldschmied scannt NFC-Tag am Ring
  → System: Neuer Auftrag oder existierend?
  → Template "Schmuck-Reparatur" lädt
  → Felder werden dynamisch erstellt:
     - Kunde auswählen (mit Suche)
     - Ankunftsdatum (automatisch gesetzt)
     - Services auswählen:
       * Reinigung (Basis €15, Multiplikator 0-10)
       * Steinersatz (triggert Stock-Check)
  → Bei "Steinersatz":
     - Verfügbare Steine aus Lager anzeigen
     - Filter: Größe, Farbe, Qualität
     - Wenn nicht vorhanden: "Stein bestellen" Task erstellen
  → Gesamtpreis wird automatisch berechnet
  → Status: "Angenommen" → Workflow startet
```

#### Use Case 2: Material-Wareneingang
```
Lieferung von 100g 750er Gold
  → Mitarbeiter scannt NFC-Tag auf Material-Beutel
  → Template "Material-Eingang" lädt
  → Felder:
     - Lieferant (aus Dropdown)
     - Materialtyp: Gold
     - Reinheit: 750
     - Gewicht: 100g
     - Chargennummer
     - Preis
  → Speichern → Lagerbestand wird automatisch aktualisiert
  → OCR kann Lieferschein scannen und Felder automatisch füllen
```

#### Use Case 3: Werkzeug-Tracking
```
Goldschmied entnimmt spezielles Werkzeug
  → Scannt NFC-Tag am Werkzeug
  → System fragt: "Werkzeug entnehmen?"
  → Bestätigt → Zeitstempel + User gespeichert
  → Werkzeug als "in Benutzung" markiert
  → Bei Rückgabe: Erneut scannen → Zeitstempel + Zustandscheck
```

---

## Cross-Platform Strategy

### Challenge
System muss funktionieren auf:
- **Android** (Smartphones, Tablets) - Haupt-Use-Case für Werkstatt
- **iOS** (iPhone, iPad) - Für Management und Außendienst
- **Windows** (Desktop, Tablets) - Für Büro/Verkauf
- **macOS** (Desktop, MacBook) - Für Management

Zusätzliche Anforderungen:
- **NFC-Scanning**: Voller Hardware-Zugriff nötig (nicht per Web möglich auf iOS)
- **QR-Scanning**: Kamera-Zugriff (per Web möglich, aber native besser)
- **Offline-Fähigkeit**: Werkstatt kann ohne Internet arbeiten
- **Push-Notifications**: Für Workflow-Updates

### Architectural Decision: **Hybrid Approach**

```
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                        │
│  - REST API                                                  │
│  - WebSocket (Real-time)                                     │
│  - Template Engine                                           │
│  - Workflow Engine                                           │
│  - Database (PostgreSQL)                                     │
│  - Redis (Cache, Pub/Sub)                                    │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTPS / WSS
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   WEB APP    │    │    MOBILE    │    │   DESKTOP    │
│   (React)    │    │ (React Native│    │  (Electron)  │
│              │    │   OR Flutter)│    │  [Optional]  │
│ - PWA        │    │              │    │              │
│ - Responsive │    │ - Android    │    │ - Windows    │
│ - QR Scanner │    │ - iOS        │    │ - macOS      │
│   (WebRTC)   │    │              │    │              │
│ - No NFC ❌  │    │ - Full NFC ✅│    │ - Wrapped    │
│              │    │ - Native QR ✅│    │   Web App    │
└──────────────┘    └──────────────┘    └──────────────┘
```

### Implementation Strategy

#### Phase 1: Web Foundation (MVP)
- **Technology**: React + TypeScript + Vite
- **Features**:
  - Full UI/UX
  - QR-Code Scanning (via Camera API)
  - Desktop/Tablet optimized
  - PWA installierbar
- **Limitations**: Kein NFC auf iOS
- **Timeline**: 6-8 Wochen

#### Phase 2: Native Mobile Apps
- **Technology**: React Native (oder Flutter)
- **Features**:
  - Voller NFC-Support (iOS + Android)
  - Native QR-Scanner
  - Offline-Modus mit lokaler SQLite
  - Push-Notifications
  - Code-Sharing mit Web (React Components)
- **Timeline**: +6-8 Wochen

#### Phase 3: Desktop Enhancement (Optional)
- **Technology**: Electron
- **Features**:
  - Installierbare Desktop-App
  - USB-NFC-Reader Support
  - Lokale Datenbank für Offline
- **Timeline**: +2-3 Wochen

### Technology Choice: React vs Flutter

| Criteria | React (Web) + React Native | Flutter |
|----------|---------------------------|---------|
| **Team Skillset** | Bereits React im Projekt ✅ | Neue Technologie ❌ |
| **Code Reuse** | Hoch (Components shareable) | Sehr hoch (100% Codebase) |
| **Web Support** | Nativ (React) ✅ | Flutter Web (Beta) ⚠️ |
| **Mobile Support** | React Native (mature) ✅ | Excellent ✅ |
| **Desktop Support** | Electron (gut) ✅ | Native (excellent) ✅ |
| **NFC Support** | react-native-nfc-manager ✅ | flutter_nfc_kit ✅ |
| **Ecosystem** | Riesig ✅ | Wachsend ⚠️ |
| **Learning Curve** | Niedrig (bereits React) ✅ | Hoch (Dart lernen) ❌ |

**Decision: React Ecosystem**
- Nutzt existierendes React-Know-How
- Schrittweise Erweiterung (Web → Mobile)
- Große Community und Libraries
- Flutter als Alternative für Rewrite in v2.0 evaluieren

---

## Tag System Architecture

### Physical Tag Composition

Jeder Tag besteht aus:
1. **NFC-Chip** (NTAG215, NTAG216, MIFARE Ultralight)
   - 888 Bytes Speicher (NTAG216)
   - Read/Write
   - 13.56 MHz (ISO/IEC 14443 Type A)

2. **QR-Code** (gedruckt auf demselben Label)
   - Format: QR Code (Version 3-5)
   - Error Correction: Level H (30%)
   - Gleiche Daten wie NFC

3. **Human-Readable** (optional)
   - Tag-ID als Text
   - Für manuelle Eingabe als Fallback

### Tag Data Structure

**Gespeicherte Information (im Chip und QR):**
```json
{
  "v": 1,                          // Schema Version
  "id": "TG-2024-A1B2C3",         // Unique Tag ID (12 chars)
  "type": "entity",                // Tag Type
  "url": "https://erp.example.com/t/TG-2024-A1B2C3"  // Deep Link
}
```

- **Total size**: ~70 Bytes (passt gut in NFC und QR)
- **URL-based**: App kann Deep Link öffnen oder API-Call machen
- **Schema Version**: Für zukünftige Änderungen

### Tag Lifecycle

```
┌─────────────────┐
│  1. MANUFACTURE │  Tag wird produziert mit unique ID
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. INVENTORY   │  Tag liegt im Lager, unregistriert
└────────┬────────┘
         │
         ▼  [Scan + Assign]
┌─────────────────┐
│  3. REGISTERED  │  Tag ist Entity zugeordnet (Schmuck, Material, etc.)
└────────┬────────┘
         │
         ▼  [Scan]
┌─────────────────┐
│  4. ACTIVE USE  │  Tag wird gescannt für View/Edit/Workflow
└────────┬────────┘
         │
         ▼  [Deactivate]
┌─────────────────┐
│ 5. DEREGISTERED │  Entity gelöscht/archiviert, Tag wiederverwendbar
└─────────────────┘
```

### Tag Registration Flow

**Szenario: Neues Schmuckstück kommt rein**

```
1. User scannt Tag (NFC oder QR)
   └─→ App liest Tag-ID: "TG-2024-A1B2C3"

2. App macht API-Call: GET /api/v1/tags/TG-2024-A1B2C3
   └─→ Response: {"registered": false, "tag_id": "TG-2024-A1B2C3"}

3. App zeigt: "Tag nicht registriert. Entity erstellen?"
   └─→ User wählt Entity-Typ: "Schmuck"

4. App lädt Template: GET /api/v1/templates/jewelry_intake
   └─→ Response: Template Definition (siehe unten)

5. App zeigt dynamisches Formular basierend auf Template

6. User füllt aus:
   - Kunde: "Max Mustermann"
   - Services: ["Reinigung", "Steinersatz"]
   - ...

7. App sendet: POST /api/v1/entities
   {
     "template_id": "jewelry_intake",
     "tag_id": "TG-2024-A1B2C3",
     "data": { ... }
   }

8. Backend:
   - Erstellt Entity
   - Verknüpft Tag
   - Initialisiert Workflow
   - Sendet WebSocket-Event

9. App zeigt: "Auftrag angelegt! Status: Angenommen"
```

### Tag Scanning Flow (Existing Entity)

```
1. User scannt Tag: "TG-2024-A1B2C3"

2. API-Call: GET /api/v1/tags/TG-2024-A1B2C3
   └─→ Response: {
         "registered": true,
         "entity_id": 42,
         "entity_type": "jewelry",
         "template_id": "jewelry_intake"
       }

3. API-Call: GET /api/v1/entities/42
   └─→ Response: Full entity data + current state

4. App zeigt Entity-Detail-View:
   - Alle Felder readonly oder editable (je nach State)
   - Aktuelle Workflow-Stage
   - Verfügbare Actions ("In Bearbeitung nehmen", "Fertigmelden", etc.)
   - Historie (Statusänderungen, Edits)

5. User kann:
   - Status ändern (Workflow-Transition)
   - Felder editieren (wenn erlaubt)
   - Fotos hinzufügen
   - Kommentare schreiben
```

### NFC vs QR Fallback Strategy

**Priorität**: NFC first (schneller, bequemer)

**Fallback-Logik**:
```
IF NFC available AND enabled
  THEN use NFC scanning
ELSE IF Camera available
  THEN use QR scanning
ELSE
  THEN show manual input field
```

**Use Cases für QR-Only**:
- iOS Geräte ohne NFC-fähige App (Web-Version)
- Distanz-Scanning (QR aus Entfernung lesbar)
- Tag beschädigt (NFC kaputt, QR noch lesbar)

---

## Template Engine

### Concept

Der Template-Engine ist das **Herzstück** des Systems. Er ermöglicht:
1. **Dynamische Formulare**: UI passt sich automatisch an Entity-Typ an
2. **Business Logic**: Berechnungen, Validierungen, Abhängigkeiten zwischen Feldern
3. **Workflow Integration**: Templates definieren erlaubte Status-Übergänge
4. **Anpassbarkeit**: Admin kann Templates ohne Code-Änderung modifizieren

### Template Structure

Ein Template ist eine **JSON-basierte Konfiguration**:

```typescript
interface Template {
  // Metadata
  id: string;                    // "jewelry_intake"
  name: string;                  // "Schmuck-Annahme"
  version: number;               // 1, 2, 3... (für Versionierung)
  entity_type: string;           // "jewelry", "material", "tool"
  icon: string;                  // "💍", "🔨", "💎"

  // UI Sections (gruppiert Felder visuell)
  sections: Section[];

  // Field Definitions
  fields: Field[];

  // Calculations (computed fields)
  calculations: Calculation[];

  // Validations
  validations: Validation[];

  // Workflow
  workflow: WorkflowDefinition;

  // Actions (buttons/operations)
  actions: Action[];

  // Permissions
  permissions: Permission[];
}
```

### Field Types

Der Template-Engine unterstützt folgende Feld-Typen:

```typescript
type FieldType =
  // Basic Types
  | "text"              // Single-line text
  | "textarea"          // Multi-line text
  | "number"            // Numeric input
  | "currency"          // Money with € symbol
  | "date"              // Date picker
  | "datetime"          // Date + Time picker
  | "boolean"           // Checkbox

  // Selection Types
  | "select"            // Dropdown (single)
  | "multiselect"       // Multiple selection
  | "radio"             // Radio buttons

  // Relationship Types
  | "relation"          // Foreign key (Customer, Material, etc.)
  | "multirelation"     // Many-to-many

  // Special Types
  | "file"              // File upload
  | "image"             // Image upload with preview
  | "signature"         // Digital signature
  | "location"          // GPS coordinates
  | "barcode"           // Barcode scanner

  // Computed Types
  | "calculated"        // Auto-calculated (readonly)
  | "aggregation"       // Sum, avg, etc. from related records
```

### Example Template: Jewelry Repair Order

```json
{
  "id": "jewelry_repair_v1",
  "name": "Schmuck-Reparatur",
  "version": 1,
  "entity_type": "jewelry_order",
  "icon": "💍",

  "sections": [
    {
      "id": "customer_info",
      "title": "Kundeninformation",
      "order": 1,
      "collapsible": false
    },
    {
      "id": "service_details",
      "title": "Leistungen",
      "order": 2,
      "collapsible": false
    },
    {
      "id": "pricing",
      "title": "Kalkulation",
      "order": 3,
      "collapsible": false
    }
  ],

  "fields": [
    {
      "id": "customer",
      "section": "customer_info",
      "type": "relation",
      "label": "Kunde",
      "entity": "Customer",
      "required": true,
      "searchable": true,
      "create_inline": true,
      "display_template": "{{first_name}} {{last_name}} ({{email}})",
      "order": 1
    },
    {
      "id": "arrival_date",
      "section": "customer_info",
      "type": "datetime",
      "label": "Annahmedatum",
      "default": "now()",
      "readonly": true,
      "order": 2
    },
    {
      "id": "description",
      "section": "customer_info",
      "type": "textarea",
      "label": "Beschreibung des Stücks",
      "placeholder": "z.B. Goldring mit Diamant, 585er Gold",
      "order": 3
    },
    {
      "id": "services",
      "section": "service_details",
      "type": "multiselect",
      "label": "Gewünschte Leistungen",
      "required": true,
      "options": [
        {
          "id": "cleaning",
          "label": "Reinigung",
          "metadata": {
            "base_price": 15.00,
            "has_multiplier": true,
            "multiplier_min": 0,
            "multiplier_max": 10,
            "multiplier_default": 1
          }
        },
        {
          "id": "polishing",
          "label": "Polieren",
          "metadata": {
            "base_price": 25.00,
            "has_multiplier": false
          }
        },
        {
          "id": "stone_replacement",
          "label": "Steinersatz",
          "metadata": {
            "base_price": 0,
            "triggers_fields": ["stone_selection", "stone_constraints"]
          }
        },
        {
          "id": "ring_sizing",
          "label": "Ringgröße ändern",
          "metadata": {
            "base_price": 30.00,
            "triggers_fields": ["target_size"]
          }
        },
        {
          "id": "repair",
          "label": "Reparatur",
          "metadata": {
            "base_price": 0,
            "triggers_fields": ["repair_description"]
          }
        }
      ],
      "order": 4
    },
    {
      "id": "cleaning_intensity",
      "section": "service_details",
      "type": "number",
      "label": "Reinigungsintensität",
      "min": 0,
      "max": 10,
      "default": 1,
      "help_text": "0 = kostenlos, 1 = Standard (€15), 10 = intensiv (€150)",
      "condition": {
        "field": "services",
        "operator": "contains",
        "value": "cleaning"
      },
      "order": 5
    },
    {
      "id": "stone_selection",
      "section": "service_details",
      "type": "relation",
      "label": "Stein auswählen",
      "entity": "Material",
      "required": false,
      "filters": {
        "material_type": "stone",
        "stock__gt": 0
      },
      "display_template": "{{name}} ({{size}}mm, {{color}}, Lager: {{stock}})",
      "condition": {
        "field": "services",
        "operator": "contains",
        "value": "stone_replacement"
      },
      "integrations": {
        "stock_check": true,
        "show_preview": true
      },
      "order": 6
    },
    {
      "id": "stone_not_available_task",
      "section": "service_details",
      "type": "action_button",
      "label": "Stein bestellen",
      "action": "create_task",
      "action_config": {
        "task_template": "order_stone",
        "prefill": {
          "type": "stone",
          "for_order_id": "{{entity_id}}"
        }
      },
      "condition": {
        "field": "services",
        "operator": "contains",
        "value": "stone_replacement"
      },
      "order": 7
    },
    {
      "id": "stone_constraints",
      "section": "service_details",
      "type": "fieldset",
      "label": "Steinanforderungen (für Bestellung)",
      "condition": {
        "field": "services",
        "operator": "contains",
        "value": "stone_replacement"
      },
      "fields": [
        {
          "id": "stone_size_min",
          "type": "number",
          "label": "Größe Min (mm)",
          "default": 3.0
        },
        {
          "id": "stone_size_max",
          "type": "number",
          "label": "Größe Max (mm)",
          "default": 5.0
        },
        {
          "id": "stone_color",
          "type": "select",
          "label": "Farbe",
          "options": ["Klar", "Blau", "Rot", "Grün", "Gelb"]
        },
        {
          "id": "stone_quality",
          "type": "select",
          "label": "Qualität",
          "options": ["IF", "VVS", "VS", "SI", "I"]
        },
        {
          "id": "stone_budget_max",
          "type": "currency",
          "label": "Max. Budget",
          "default": 100.00
        }
      ],
      "order": 8
    },
    {
      "id": "target_size",
      "section": "service_details",
      "type": "number",
      "label": "Ziel-Ringgröße",
      "condition": {
        "field": "services",
        "operator": "contains",
        "value": "ring_sizing"
      },
      "order": 9
    },
    {
      "id": "repair_description",
      "section": "service_details",
      "type": "textarea",
      "label": "Reparatur-Details",
      "condition": {
        "field": "services",
        "operator": "contains",
        "value": "repair"
      },
      "order": 10
    },
    {
      "id": "photos",
      "section": "service_details",
      "type": "image",
      "label": "Fotos",
      "multiple": true,
      "max_files": 5,
      "order": 11
    }
  ],

  "calculations": [
    {
      "id": "cleaning_price",
      "type": "formula",
      "formula": "IF(CONTAINS(services, 'cleaning'), 15 * cleaning_intensity, 0)"
    },
    {
      "id": "polishing_price",
      "type": "formula",
      "formula": "IF(CONTAINS(services, 'polishing'), 25, 0)"
    },
    {
      "id": "stone_price",
      "type": "lookup",
      "source": "stone_selection.unit_price",
      "default": 0
    },
    {
      "id": "ring_sizing_price",
      "type": "formula",
      "formula": "IF(CONTAINS(services, 'ring_sizing'), 30, 0)"
    },
    {
      "id": "total_price",
      "type": "formula",
      "formula": "cleaning_price + polishing_price + stone_price + ring_sizing_price",
      "display": {
        "section": "pricing",
        "label": "Gesamtpreis",
        "format": "currency"
      }
    }
  ],

  "validations": [
    {
      "type": "required_if",
      "field": "stone_selection",
      "condition": {
        "field": "services",
        "operator": "contains",
        "value": "stone_replacement"
      },
      "message": "Bitte Stein auswählen oder Bestellung anlegen"
    },
    {
      "type": "custom",
      "script": "IF(stone_selection AND stone_selection.stock < 1) THEN ERROR('Stein nicht auf Lager!')"
    }
  ],

  "workflow": {
    "initial_state": "received",
    "states": [
      {
        "id": "received",
        "label": "Angenommen",
        "color": "blue"
      },
      {
        "id": "in_progress",
        "label": "In Bearbeitung",
        "color": "yellow"
      },
      {
        "id": "waiting_stone",
        "label": "Warte auf Material",
        "color": "orange"
      },
      {
        "id": "quality_check",
        "label": "Qualitätsprüfung",
        "color": "purple"
      },
      {
        "id": "completed",
        "label": "Fertig",
        "color": "green"
      },
      {
        "id": "delivered",
        "label": "Ausgeliefert",
        "color": "gray"
      }
    ],
    "transitions": [
      {
        "from": "received",
        "to": "in_progress",
        "label": "Bearbeitung starten",
        "requires_permission": "goldsmith"
      },
      {
        "from": "received",
        "to": "waiting_stone",
        "label": "Material bestellen",
        "condition": {
          "field": "services",
          "operator": "contains",
          "value": "stone_replacement"
        }
      },
      {
        "from": "in_progress",
        "to": "quality_check",
        "label": "QC anfragen"
      },
      {
        "from": "waiting_stone",
        "to": "in_progress",
        "label": "Material eingegangen",
        "auto_trigger": {
          "event": "material_received",
          "condition": "stone_selection.stock > 0"
        }
      },
      {
        "from": "quality_check",
        "to": "in_progress",
        "label": "Nacharbeit nötig"
      },
      {
        "from": "quality_check",
        "to": "completed",
        "label": "QC bestanden"
      },
      {
        "from": "completed",
        "to": "delivered",
        "label": "An Kunde übergeben",
        "actions": [
          "send_notification",
          "update_stock",
          "create_invoice"
        ]
      }
    ]
  },

  "actions": [
    {
      "id": "print_label",
      "label": "Job-Label drucken",
      "icon": "🖨️",
      "type": "print",
      "template": "job_label",
      "available_in_states": ["received", "in_progress"]
    },
    {
      "id": "notify_customer",
      "label": "Kunde benachrichtigen",
      "icon": "📧",
      "type": "notification",
      "channels": ["email", "sms"],
      "available_in_states": ["completed"]
    }
  ],

  "permissions": {
    "create": ["admin", "receptionist"],
    "view": ["admin", "goldsmith", "receptionist"],
    "edit": ["admin", "goldsmith"],
    "delete": ["admin"],
    "workflow_transition": {
      "received->in_progress": ["goldsmith"],
      "in_progress->quality_check": ["goldsmith"],
      "quality_check->completed": ["admin", "quality_manager"],
      "completed->delivered": ["receptionist"]
    }
  }
}
```

### Template Storage

Templates werden in der Datenbank gespeichert:

```sql
CREATE TABLE templates (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    entity_type VARCHAR(50) NOT NULL,
    icon VARCHAR(10),
    config JSONB NOT NULL,  -- Full template definition
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id),

    UNIQUE(id, version)
);

CREATE INDEX idx_templates_entity_type ON templates(entity_type);
CREATE INDEX idx_templates_active ON templates(is_active);
```

### Template Versioning

Templates können versioniert werden:
- **v1**: Initiale Version
- **v2**: Feld hinzugefügt
- **v3**: Workflow angepasst

Entities speichern ihre Template-Version → Alte Entities funktionieren weiter, neue nutzen neue Version.

---

## Workflow Engine

Der Workflow-Engine verwaltet **State Transitions** und **Automatisierungen**.

### Workflow State Machine

```
┌──────────┐
│ RECEIVED │  (Auftrag angenommen)
└────┬─────┘
     │
     ├─→ [Goldschmied startet] ─→ ┌──────────────┐
     │                             │ IN_PROGRESS  │
     │                             └──────┬───────┘
     │                                    │
     │                                    ├─→ [Fertig] ─→ ┌───────────────┐
     │                                    │                │ QUALITY_CHECK │
     │                                    │                └───────┬───────┘
     │                                    │                        │
     │                                    │                        ├─→ [OK] ─→ ┌───────────┐
     │                                    │                        │            │ COMPLETED │
     │                                    │                        │            └─────┬─────┘
     │                                    │                        │                  │
     │                                    │                        └─→ [Not OK] ──────┘
     │                                    │                                (zurück zu IN_PROGRESS)
     │
     └─→ [Material fehlt] ─→ ┌──────────────┐
                              │ WAITING_STONE│ ─→ [Material da] ─→ (zu IN_PROGRESS)
                              └──────────────┘
```

### Workflow Features

1. **State Validation**: Nur erlaubte Übergänge möglich
2. **Permission Checks**: User muss Berechtigung für Transition haben
3. **Conditional Transitions**: Transition nur wenn Bedingung erfüllt
4. **Auto-Transitions**: System triggert Transition automatisch (z.B. bei Material-Eingang)
5. **Transition Actions**: Bei Transition werden Aktionen ausgeführt (Notification, Stock-Update, etc.)
6. **State Hooks**: Before/After-Hooks für Custom Logic

### Implementation

```python
# Backend: Workflow Engine
class WorkflowEngine:
    def __init__(self, template: Template, entity: Entity):
        self.template = template
        self.entity = entity
        self.workflow = template.workflow

    def can_transition(self, to_state: str, user: User) -> tuple[bool, str]:
        """Check if transition is allowed"""
        current_state = self.entity.state

        # Find transition
        transition = self._find_transition(current_state, to_state)
        if not transition:
            return False, "Invalid transition"

        # Check permissions
        if not self._has_permission(user, transition):
            return False, "Permission denied"

        # Check conditions
        if not self._check_conditions(transition):
            return False, "Conditions not met"

        return True, "OK"

    async def transition(self, to_state: str, user: User, data: dict = None):
        """Execute state transition"""
        # Validate
        can, reason = self.can_transition(to_state, user)
        if not can:
            raise WorkflowError(reason)

        # Before hook
        await self._before_transition(to_state, data)

        # Update state
        old_state = self.entity.state
        self.entity.state = to_state
        self.entity.updated_at = datetime.now()
        self.entity.updated_by = user.id

        # Execute actions
        transition = self._find_transition(old_state, to_state)
        await self._execute_actions(transition.actions, data)

        # After hook
        await self._after_transition(old_state, to_state, data)

        # Save
        await self.entity.save()

        # Log history
        await self._log_history(old_state, to_state, user, data)

        # Publish event
        await publish_event("workflow_transition", {
            "entity_id": self.entity.id,
            "from_state": old_state,
            "to_state": to_state,
            "user": user.id
        })
```

---

## Data Model

### Core Tables

```sql
-- Tags (NFC + QR)
CREATE TABLE tags (
    id VARCHAR(20) PRIMARY KEY,  -- "TG-2024-A1B2C3"
    type VARCHAR(20) DEFAULT 'entity',
    created_at TIMESTAMP DEFAULT NOW(),
    registered BOOLEAN DEFAULT false,
    entity_id INTEGER NULL,
    metadata JSONB
);

-- Templates
CREATE TABLE templates (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version INTEGER DEFAULT 1,
    entity_type VARCHAR(50),
    config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Entities (instances of templates)
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    template_id VARCHAR(50) REFERENCES templates(id),
    template_version INTEGER,
    tag_id VARCHAR(20) REFERENCES tags(id),
    state VARCHAR(50) NOT NULL,
    data JSONB NOT NULL,  -- All dynamic field values
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id),
    updated_by INTEGER REFERENCES users(id)
);

-- Entity History (audit log)
CREATE TABLE entity_history (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id),
    action VARCHAR(20),  -- "create", "update", "transition"
    old_state VARCHAR(50),
    new_state VARCHAR(50),
    changes JSONB,  -- Field-level changes
    user_id INTEGER REFERENCES users(id),
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Tasks (TODOs created by workflows)
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    template_id VARCHAR(50),  -- Optional: Task can have template too
    related_entity_id INTEGER REFERENCES entities(id),
    assigned_to INTEGER REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'open',  -- open, in_progress, completed
    due_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Existing tables (extended)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(200),
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    role VARCHAR(20),  -- admin, goldsmith, receptionist, quality_manager
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    customer_number VARCHAR(20) UNIQUE,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(100),
    phone VARCHAR(20),
    address JSONB,
    notes TEXT,
    tags JSONB,  -- ["VIP", "Stammkunde"]
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE materials (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    material_type VARCHAR(50),  -- gold, silver, stone, tool
    description TEXT,
    unit_price DECIMAL(10,2),
    stock DECIMAL(10,3),
    unit VARCHAR(20),  -- g, kg, pcs
    metadata JSONB,  -- Type-specific: purity, size, color, etc.
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Entity Data Storage (JSONB)

Entities speichern ihre Daten in einem JSONB-Feld. Beispiel:

```json
{
  "customer": 42,
  "arrival_date": "2024-01-15T10:30:00Z",
  "description": "Goldring 585er mit Diamant",
  "services": ["cleaning", "stone_replacement"],
  "cleaning_intensity": 3,
  "stone_selection": 123,
  "stone_constraints": {
    "stone_size_min": 3.5,
    "stone_size_max": 4.0,
    "stone_color": "Klar",
    "stone_quality": "VS",
    "stone_budget_max": 150.00
  },
  "photos": [
    "https://s3.../entity_42_photo1.jpg",
    "https://s3.../entity_42_photo2.jpg"
  ],
  "_calculated": {
    "cleaning_price": 45.00,
    "stone_price": 120.00,
    "total_price": 165.00
  }
}
```

### Indexes für Performance

```sql
-- Tag lookup (sehr häufig)
CREATE INDEX idx_tags_id ON tags(id);
CREATE INDEX idx_tags_entity ON tags(entity_id);

-- Entity queries
CREATE INDEX idx_entities_template ON entities(template_id);
CREATE INDEX idx_entities_state ON entities(state);
CREATE INDEX idx_entities_tag ON entities(tag_id);
CREATE INDEX idx_entities_created ON entities(created_at DESC);

-- JSONB queries (for filtering by field values)
CREATE INDEX idx_entities_data_customer ON entities USING GIN ((data->'customer'));
CREATE INDEX idx_entities_data_services ON entities USING GIN ((data->'services'));

-- Full-text search
CREATE INDEX idx_entities_data_fulltext ON entities USING GIN (to_tsvector('german', data::text));
```

---

## Technology Stack

### Backend
- **Runtime**: Python 3.11+
- **Framework**: FastAPI (async)
- **ORM**: SQLAlchemy 2.0 (async)
- **Database**: PostgreSQL 15 (JSONB support)
- **Cache/Pub-Sub**: Redis 7
- **File Storage**: S3-compatible (MinIO/AWS)
- **Migrations**: Alembic
- **Task Queue**: Celery (optional, for heavy tasks)
- **Web Server**: Uvicorn (ASGI)

### Frontend - Web
- **Framework**: React 18
- **Language**: TypeScript
- **Build Tool**: Vite
- **State Management**: Zustand (oder Redux Toolkit)
- **Routing**: React Router v6
- **UI Components**: Shadcn/ui (Tailwind-based)
- **Forms**: React Hook Form
- **API Client**: Axios
- **WebSocket**: native WebSocket API
- **QR Scanning**: html5-qrcode
- **Charts**: Recharts
- **Date/Time**: date-fns

### Frontend - Mobile (Phase 2)
- **Framework**: React Native
- **Language**: TypeScript
- **Navigation**: React Navigation
- **NFC**: react-native-nfc-manager
- **QR Scanning**: react-native-camera
- **Offline DB**: WatermelonDB oder SQLite
- **State Sync**: Redux + Redux Persist

### DevOps
- **Containerization**: Docker + Docker Compose
- **Orchestration**: Kubernetes (production)
- **CI/CD**: GitHub Actions
- **Monitoring**: Prometheus + Grafana
- **Logging**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **Error Tracking**: Sentry

---

## Security & Performance

### Security Measures

1. **Authentication**
   - JWT with short expiry (15 min)
   - Refresh tokens (7 days)
   - Secure password hashing (bcrypt)

2. **Authorization**
   - Role-based access control (RBAC)
   - Template-level permissions
   - State-transition permissions

3. **Data Protection**
   - HTTPS only (TLS 1.3)
   - Database encryption at rest
   - GDPR compliance (data deletion, export)
   - Audit logging (all changes tracked)

4. **API Security**
   - Rate limiting (per user/IP)
   - CORS policies
   - Input validation (Pydantic)
   - SQL injection protection (ORM)
   - XSS protection (React auto-escaping)

### Performance Optimizations

1. **Database**
   - Proper indexes (see above)
   - Connection pooling (asyncpg)
   - Query optimization (no N+1)
   - Materialized views for reports

2. **Caching**
   - Redis for:
     - Template definitions (rarely change)
     - User sessions
     - Material stock (with invalidation)
     - Aggregated reports

3. **API**
   - Pagination (all list endpoints)
   - Field selection (GraphQL-style)
   - Response compression (gzip)
   - CDN for static files

4. **Frontend**
   - Code splitting (React.lazy)
   - Image optimization (WebP)
   - Lazy loading
   - Virtual scrolling (large lists)
   - Service Worker (PWA cache)

### Scalability

**Horizontal Scaling**:
- Backend: Multiple FastAPI instances behind load balancer
- Database: PostgreSQL read replicas
- Redis: Redis Cluster for high availability
- File Storage: S3 (infinitely scalable)

**Vertical Scaling**:
- Database: Increase CPU/RAM for complex queries
- Redis: More memory for larger cache

---

## Next Steps

1. **Review and Approve**: Team reviews this architecture
2. **Create Roadmap**: See ROADMAP.md for implementation phases
3. **Prototype**: Build minimal template engine prototype
4. **Iterate**: Test with real use cases, refine

---

**Document Version**: 1.0
**Last Updated**: 2024-01-15
**Authors**: Architecture Team
**Status**: Draft for Review

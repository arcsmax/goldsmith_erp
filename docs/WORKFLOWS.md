# Goldsmith ERP - Workflow Examples

## Table of Contents

1. [Workflow Overview](#workflow-overview)
2. [Jewelry Repair Workflow](#jewelry-repair-workflow)
3. [Material Intake Workflow](#material-intake-workflow)
4. [Custom Order Creation Workflow](#custom-order-creation-workflow)
5. [Tool Checkout Workflow](#tool-checkout-workflow)
6. [Stone Procurement Workflow](#stone-procurement-workflow)
7. [Quality Control Workflow](#quality-control-workflow)

---

## Workflow Overview

Alle Workflows in Goldsmith ERP folgen diesem Grundmuster:

```
┌──────────────┐
│  TAG SCAN    │  User scannt NFC oder QR-Code
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ TAG LOOKUP   │  System prüft: Registered?
└──────┬───────┘
       │
       ├─→ [Neu] ──────→ ┌─────────────────┐
       │                 │ REGISTRATION    │  Template auswählen → Formular
       │                 └─────────────────┘
       │
       └─→ [Existiert] ─→ ┌─────────────────┐
                          │ ENTITY VIEW     │  Daten anzeigen → Workflow-Actions
                          └─────────────────┘
```

---

## Jewelry Repair Workflow

### Szenario
Ein Kunde bringt einen Goldring zur Reinigung und Steinersatz.

### Workflow-Schritte

#### 1. Annahme (Reception)

**Aktion**: Rezeptionist scannt Tag am Ring

```
┌─────────────────────────────────────────┐
│  TAG SCAN: TG-2024-J0042                │
│  Status: Nicht registriert              │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  TEMPLATE AUSWAHL                       │
│  ○ Schmuck-Reparatur                    │
│  ○ Schmuck-Neubau                       │
│  ○ Material-Eingang                     │
│  ○ Werkzeug                             │
└─────────────────────────────────────────┘
         │ [Wählt: Schmuck-Reparatur]
         ▼
┌─────────────────────────────────────────┐
│  FORMULAR: SCHMUCK-REPARATUR            │
│─────────────────────────────────────────│
│  Kundeninformation                      │
│  ├─ Kunde: [Suchen...] "Max Muster" ✓   │
│  ├─ Annahme: 15.01.2024 10:30 🔒       │
│  └─ Beschreibung:                       │
│     "Goldring 585er, Diamant 4mm"       │
│                                         │
│  Leistungen                             │
│  ☑ Reinigung                            │
│    └─ Intensität: [====|-----] 4/10     │
│       Preis: €60                        │
│  ☑ Steinersatz                          │
│    └─ Stein: [Auswählen aus Lager...]  │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Verfügbare Steine (3 gefunden)    │ │
│  ├───────────────────────────────────┤ │
│  │ ○ Diamant 4.0mm, VS, €120, Lager:1│ │
│  │ ○ Diamant 4.2mm, SI, €85, Lager:2 │ │
│  │ ○ Zirkonia 4.0mm, €15, Lager:5    │ │
│  └───────────────────────────────────┘ │
│                                         │
│  [Stein nicht gefunden?]                │
│  → Button: "Stein bestellen" 🛒         │
│                                         │
│  Kalkulation                            │
│  ├─ Reinigung: €60                      │
│  ├─ Stein: €120                         │
│  └─ GESAMT: €180 ✨                     │
│                                         │
│  [Fotos] 📷                             │
│  ├─ ring_overview.jpg                   │
│  └─ stone_closeup.jpg                   │
│                                         │
│  [ Speichern & Job-Label drucken ]     │
└─────────────────────────────────────────┘
```

**System-Aktionen beim Speichern**:
- Entity erstellt mit ID: `E-2024-00087`
- Tag verknüpft: `TG-2024-J0042` → Entity `E-2024-00087`
- Initial State: `received`
- Lagerbestand: Diamant 4.0mm: 1 → 0 (reserviert)
- Job-Label wird generiert und gedruckt
- WebSocket-Event: Neuer Job im System

**Job-Label (gedruckt)**:
```
┌────────────────────────────────┐
│  GOLDSMITH ERP                 │
│  Job #E-2024-00087             │
├────────────────────────────────┤
│  Kunde: Max Mustermann         │
│  Annahme: 15.01.2024           │
│  Services:                     │
│  • Reinigung (Intensiv)        │
│  • Steinersatz (4mm Diamant)   │
│  Preis: €180                   │
│  Status: 🔵 Angenommen         │
│  Zugewiesen: -                 │
└────────────────────────────────┘
   [QR-CODE: E-2024-00087]
```

---

#### 2. Bearbeitung starten (Goldsmith)

**Aktion**: Goldschmied scannt Job-Label

```
┌─────────────────────────────────────────┐
│  JOB #E-2024-00087                      │
│  Status: 🔵 Angenommen                  │
│─────────────────────────────────────────│
│  Kunde: Max Mustermann                  │
│  Services:                              │
│  • Reinigung (Intensität 4)             │
│  • Steinersatz                          │
│                                         │
│  Verfügbare Aktionen:                   │
│  ┌───────────────────────────────────┐ │
│  │ ▶ Bearbeitung starten             │ │
│  │   Wechselt zu: In Bearbeitung     │ │
│  └───────────────────────────────────┘ │
│  ┌───────────────────────────────────┐ │
│  │ 📦 Material fehlt                 │ │
│  │   Wechselt zu: Warte auf Material │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**User klickt**: "Bearbeitung starten"

**System-Aktionen**:
- State: `received` → `in_progress`
- Assigned to: User "Johann Schmidt" (Goldschmied)
- Timestamp: 15.01.2024 14:00
- WebSocket-Event: Job-Status aktualisiert
- Timer startet (optional für Zeiterfassung)

---

#### 3. Fertigmeldung

**Aktion**: Goldschmied scannt erneut (nach Fertigstellung)

```
┌─────────────────────────────────────────┐
│  JOB #E-2024-00087                      │
│  Status: 🟡 In Bearbeitung              │
│  Zugewiesen: Johann Schmidt             │
│  Dauer: 2h 15min                        │
│─────────────────────────────────────────│
│  Verfügbare Aktionen:                   │
│  ┌───────────────────────────────────┐ │
│  │ ✓ Fertig melden                   │ │
│  │   Wechselt zu: Qualitätsprüfung   │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**User klickt**: "Fertig melden"

**System fragt**:
```
┌─────────────────────────────────────────┐
│  ARBEIT ABGESCHLOSSEN?                  │
│─────────────────────────────────────────│
│  Arbeitszeit: 2h 15min                  │
│                                         │
│  Notizen (optional):                    │
│  ┌─────────────────────────────────┐   │
│  │ "Stein perfekt eingesetzt,      │   │
│  │  Ring poliert und gereinigt"    │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Fotos hinzufügen? 📷                   │
│  [Foto aufnehmen]                       │
│                                         │
│  [ Abbrechen ]  [ Bestätigen ]         │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- State: `in_progress` → `quality_check`
- Arbeitszeit gespeichert: 2h 15min
- Notiz hinzugefügt
- QC-Manager erhält Notification

---

#### 4. Qualitätsprüfung

**Aktion**: QC-Manager scannt Job

```
┌─────────────────────────────────────────┐
│  JOB #E-2024-00087                      │
│  Status: 🟣 Qualitätsprüfung            │
│  Bearbeitet von: Johann Schmidt         │
│─────────────────────────────────────────│
│  Services durchgeführt:                 │
│  ✓ Reinigung (Intensität 4)             │
│  ✓ Steinersatz (Diamant 4mm)            │
│                                         │
│  Notizen vom Goldschmied:               │
│  "Stein perfekt eingesetzt..."          │
│                                         │
│  Fotos:                                 │
│  [📷 IMG1] [📷 IMG2]                    │
│                                         │
│  QUALITÄTSPRÜFUNG:                      │
│  ┌───────────────────────────────────┐ │
│  │ ✅ QC bestanden                   │ │
│  │   → Job fertigstellen             │ │
│  └───────────────────────────────────┘ │
│  ┌───────────────────────────────────┐ │
│  │ ⚠️  Nacharbeit nötig              │ │
│  │   → Zurück in Bearbeitung         │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**User klickt**: "QC bestanden"

**System-Aktionen**:
- State: `quality_check` → `completed`
- Timestamp completed: 15.01.2024 16:30
- Notification an Rezeption: "Job fertig zur Abholung"
- Notification an Kunde (E-Mail/SMS): "Ihr Schmuck ist fertig!"

---

#### 5. Abholung

**Aktion**: Kunde holt ab, Rezeption scannt Job

```
┌─────────────────────────────────────────┐
│  JOB #E-2024-00087                      │
│  Status: 🟢 Fertig                      │
│  Kunde: Max Mustermann                  │
│  Preis: €180                            │
│─────────────────────────────────────────│
│  Verfügbare Aktionen:                   │
│  ┌───────────────────────────────────┐ │
│  │ 🤝 An Kunde übergeben             │ │
│  │   → Rechnung erstellen            │ │
│  │   → Job abschließen               │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**User klickt**: "An Kunde übergeben"

**System fragt Zahlungsart**:
```
┌─────────────────────────────────────────┐
│  RECHNUNG ERSTELLEN                     │
│─────────────────────────────────────────│
│  Betrag: €180                           │
│                                         │
│  Zahlungsart:                           │
│  ○ Bar                                  │
│  ○ EC-Karte                             │
│  ○ Kreditkarte                          │
│  ○ Überweisung (Rechnung per E-Mail)   │
│                                         │
│  [ Rechnung drucken & Abschließen ]    │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- State: `completed` → `delivered`
- Rechnung erstellt und gedruckt/gemailt
- Zahlung verbucht
- Tag wird "released" (kann wiederverwendet werden)
- Job archiviert
- Statistiken aktualisiert (Umsatz, Durchlaufzeit, etc.)

---

### Workflow-Übersicht (State Machine)

```
┌──────────┐
│ RECEIVED │  (Angenommen)
└────┬─────┘
     │
     ├─→ [Start] ──────────→ ┌──────────────┐
     │                        │ IN_PROGRESS  │
     │                        └──────┬───────┘
     │                               │
     │                               ├─→ [Fertig] ─→ ┌───────────────┐
     │                               │                │ QUALITY_CHECK │
     │                               │                └───────┬───────┘
     │                               │                        │
     │                               │                        ├─→ [OK] ─→ ┌───────────┐
     │                               │                        │            │ COMPLETED │
     │                               │                        │            └─────┬─────┘
     │                               │                        │                  │
     │                               │                        └─→ [Not OK] ──────┤
     │                               │                           (zurück)        │
     │                               │                                           │
     └─→ [Material fehlt] ─→ ┌──────────────┐                                   │
                              │ WAITING_MAT  │ ─────────────────────────────────┤
                              └──────────────┘   [Material da]                  │
                                                                                 │
                                                                                 ▼
                                                                         ┌──────────────┐
                                                                         │  DELIVERED   │
                                                                         └──────────────┘
                                                                          (Abgeschlossen)
```

---

## Material Intake Workflow

### Szenario
Lieferung von 100g 750er Gold kommt an.

#### 1. Wareneingang scannen

```
┌─────────────────────────────────────────┐
│  TAG SCAN: TG-2024-M0123                │
│  Typ: Material                          │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  FORMULAR: MATERIAL-EINGANG             │
│─────────────────────────────────────────│
│  Lieferant                              │
│  └─ [Auswählen...] "Schöne GmbH" ✓     │
│                                         │
│  Material-Details                       │
│  ├─ Typ: [Dropdown]                     │
│  │   ● Gold                             │
│  │   ○ Silber                           │
│  │   ○ Platin                           │
│  │   ○ Edelstein                        │
│  ├─ Reinheit:                           │
│  │   [333] [585] [750] [999] ← 750 ✓   │
│  ├─ Gewicht: [100.00] g                 │
│  ├─ Chargennummer: "CH-2024-0042"       │
│  └─ Einkaufspreis: €5,800               │
│                                         │
│  OCR-Scan verfügbar? 📄                 │
│  [Lieferschein fotografieren]           │
│  → Felder werden automatisch gefüllt    │
│                                         │
│  Lagerort                               │
│  └─ [Tresor A, Fach 3]                  │
│                                         │
│  Fotos (optional) 📷                    │
│  [+]                                    │
│                                         │
│  [ Speichern & Label drucken ]         │
└─────────────────────────────────────────┘
```

**System-Aktionen beim Speichern**:
- Material-Entity erstellt: `M-2024-00231`
- Tag verknüpft: `TG-2024-M0123` → `M-2024-00231`
- Lagerbestand aktualisiert:
  - Gold 750: +100g
  - Gesamtwert: +€5,800
- Material-Label gedruckt mit QR-Code
- Benachrichtigungen:
  - Falls Stein-Bestellungen offen → Check: Passt dieser zu Anforderungen?
  - Falls Low-Stock-Alert aktiv → Warnung aufheben

**Material-Label**:
```
┌────────────────────────────────┐
│  GOLDSMITH ERP                 │
│  Material #M-2024-00231        │
├────────────────────────────────┤
│  Gold 750 (18kt)               │
│  Gewicht: 100.00g              │
│  Charge: CH-2024-0042          │
│  Lagerort: Tresor A, Fach 3    │
│  Eingang: 15.01.2024           │
└────────────────────────────────┘
   [QR-CODE: M-2024-00231]
```

---

## Custom Order Creation Workflow

### Szenario
Kunde möchte individuellen Ring anfertigen lassen (kein bestehendes Stück).

#### 1. Angebot erstellen

```
┌─────────────────────────────────────────┐
│  NEUER AUFTRAG (ohne physisches Tag)    │
│  Template: Schmuck-Neubau               │
│─────────────────────────────────────────│
│  Kunde: [Suchen...] "Anna Müller" ✓     │
│  Angebotsdatum: 15.01.2024 🔒           │
│                                         │
│  Design-Anforderungen                   │
│  ├─ Art: [Dropdown]                     │
│  │   ● Ring                             │
│  │   ○ Kette                            │
│  │   ○ Ohrringe                         │
│  ├─ Material:                           │
│  │   ☑ Gold 750                         │
│  │   Gewicht (geschätzt): 8g            │
│  ├─ Steine:                             │
│  │   ☑ Hauptstein: Saphir 6mm           │
│  │   ☑ Nebensteine: 6x Diamant 2mm      │
│  └─ Ringgröße: 54                       │
│                                         │
│  Design-Skizze 🎨                       │
│  [Bild hochladen] sketch_ring_001.jpg ✓ │
│                                         │
│  Kalkulation                            │
│  ├─ Material (Gold 8g): €480            │
│  ├─ Hauptstein (Saphir): €350           │
│  ├─ Nebensteine (6x): €180              │
│  ├─ Arbeitszeit (geschätzt 6h): €420    │
│  ├─ Zwischensumme: €1,430               │
│  ├─ Marge (30%): €429                   │
│  └─ ANGEBOTSPREIS: €1,860               │
│                                         │
│  Liefertermin (geschätzt):              │
│  └─ 4-6 Wochen (ML-Prognose)            │
│                                         │
│  [ Angebot als PDF ]  [ Speichern ]    │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- Entity erstellt: `O-2024-00088` (Order)
- State: `quotation` (Angebot)
- Angebots-PDF generiert
- E-Mail an Kunde mit PDF
- Reminder: Nach 7 Tagen Nachfassen

#### 2. Kunde akzeptiert Angebot

**Rezeption scannt QR-Code des Angebots** (oder sucht Order)

```
┌─────────────────────────────────────────┐
│  AUFTRAG #O-2024-00088                  │
│  Status: 📋 Angebot                     │
│  Kunde: Anna Müller                     │
│─────────────────────────────────────────│
│  Verfügbare Aktionen:                   │
│  ┌───────────────────────────────────┐ │
│  │ ✅ Angebot angenommen             │ │
│  │   → Auftrag bestätigen            │ │
│  └───────────────────────────────────┘ │
│  ┌───────────────────────────────────┐ │
│  │ ❌ Angebot abgelehnt              │ │
│  │   → Auftrag archivieren           │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**User klickt**: "Angebot angenommen"

**System fragt**:
```
┌─────────────────────────────────────────┐
│  AUFTRAGSBESTÄTIGUNG                    │
│─────────────────────────────────────────│
│  Anzahlung erhalten?                    │
│  ○ Ja: [___] € (empf. 30% = €558)       │
│  ○ Nein, später                         │
│                                         │
│  Liefertermin vereinbart:               │
│  [📅 28.02.2024] (6 Wochen)             │
│                                         │
│  NFC-Tag zuweisen (optional):           │
│  [Jetzt Tag scannen] oder [Später]     │
│                                         │
│  [ Bestätigen ]                         │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- State: `quotation` → `confirmed`
- Anzahlung verbucht (falls angegeben)
- Liefertermin gesetzt
- Material-Reservierung:
  - Gold 750: -8g (reserviert)
  - Saphir 6mm: -1 (reserviert)
  - Diamant 2mm: -6 (reserviert)
- Falls Material fehlt: Automatische Task "Material bestellen"
- Job-Planung: Auftrag erscheint in Produktions-Queue
- Notification an Goldschmied-Team

#### 3. Produktion

**Ablauf analog zum Repair-Workflow**:
- `confirmed` → `in_progress` (Goldschmied startet)
- `in_progress` → `quality_check` (Fertigmeldung)
- `quality_check` → `completed` (QC bestanden)
- `completed` → `delivered` (Kunde holt ab)

**Zusätzlich**:
- Bei Fertigstellung: NFC-Tag am fertigen Ring anbringen
- Tag-Scan ermöglicht zukünftige Service-Historie

---

## Tool Checkout Workflow

### Szenario
Goldschmied entnimmt spezielles Werkzeug aus Tresor.

#### 1. Werkzeug entnehmen

```
┌─────────────────────────────────────────┐
│  TAG SCAN: TG-2024-T0007                │
│  Werkzeug: Spezial-Graviermaschine      │
│  Status: ✅ Verfügbar                   │
│─────────────────────────────────────────│
│  Letzter Benutzer: Maria Klein          │
│  Letzte Nutzung: 10.01.2024             │
│  Zustand bei Rückgabe: "Gut"            │
│                                         │
│  ENTNEHMEN?                             │
│  [ Ja, entnehmen ]  [ Abbrechen ]      │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- Tool-Status: `available` → `checked_out`
- Checked out by: User "Johann Schmidt"
- Checkout time: 15.01.2024 14:30
- WebSocket-Event: Tool nicht mehr verfügbar

#### 2. Werkzeug zurückgeben

**Goldschmied scannt erneut**

```
┌─────────────────────────────────────────┐
│  TAG SCAN: TG-2024-T0007                │
│  Werkzeug: Spezial-Graviermaschine      │
│  Status: 🔴 In Benutzung (Sie)          │
│─────────────────────────────────────────│
│  Entnommen: 15.01.2024 14:30            │
│  Dauer: 2h 15min                        │
│                                         │
│  ZURÜCKGEBEN?                           │
│  Zustand:                               │
│  ○ Gut (keine Probleme)                 │
│  ○ Wartung nötig                        │
│  ○ Defekt                               │
│                                         │
│  Notizen (optional):                    │
│  ┌─────────────────────────────────┐   │
│  │                                 │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [ Zurückgeben ]                        │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- Tool-Status: `checked_out` → `available` (oder `maintenance`)
- Return time: 15.01.2024 16:45
- Usage duration: 2h 15min (für Statistiken)
- Falls "Wartung nötig": Task für Werkstatt erstellen
- WebSocket-Event: Tool wieder verfügbar

---

## Stone Procurement Workflow

### Szenario
Bei Repair-Auftrag wird Stein benötigt, der nicht auf Lager ist.

#### 1. Task-Erstellung (automatisch oder manuell)

**Im Repair-Workflow (siehe oben)**:
- User klickt "Stein bestellen"
- Task wird erstellt mit Pre-Fill aus Constraints

```
┌─────────────────────────────────────────┐
│  NEUE AUFGABE: STEIN BESTELLEN          │
│─────────────────────────────────────────│
│  Für Auftrag: #E-2024-00087             │
│  Kunde: Max Mustermann                  │
│                                         │
│  Anforderungen (aus Auftrag):           │
│  ├─ Typ: Diamant                        │
│  ├─ Größe: 3.5-4.0mm                    │
│  ├─ Farbe: Klar (D-F)                   │
│  ├─ Qualität: VS oder besser            │
│  └─ Budget: Max. €150                   │
│                                         │
│  Priorität:                             │
│  ○ Normal (7 Tage)                      │
│  ● Dringend (3 Tage) ← Auto-selected    │
│  ○ Sofort (Express)                     │
│                                         │
│  Zuweisen an:                           │
│  [Dropdown] "Einkauf" ✓                 │
│                                         │
│  [ Task erstellen ]                     │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- Task erstellt: `T-2024-00042`
- Assigned to: Einkauf-Team
- Linked to Order: `E-2024-00087`
- Notification an Einkauf
- Order-Status: `received` → `waiting_stone`

#### 2. Einkauf bestellt Stein

**Einkauf öffnet Task**

```
┌─────────────────────────────────────────┐
│  TASK #T-2024-00042                     │
│  Stein bestellen für #E-2024-00087      │
│  Status: 🔵 Offen                       │
│─────────────────────────────────────────│
│  Anforderungen:                         │
│  • Diamant, 3.5-4.0mm, Klar, VS+        │
│  • Budget: €150                         │
│  • Dringend (3 Tage)                    │
│                                         │
│  LIEFERANTEN-SUCHE                      │
│  [Suche bei bekannten Lieferanten...]   │
│                                         │
│  Ergebnisse:                            │
│  ┌───────────────────────────────────┐ │
│  │ Lieferant A                       │ │
│  │ Diamant 3.8mm, VS1, €135          │ │
│  │ Lieferzeit: 2 Tage ✓              │ │
│  │ [Bestellen]                       │ │
│  └───────────────────────────────────┘ │
│  ┌───────────────────────────────────┐ │
│  │ Lieferant B                       │ │
│  │ Diamant 4.0mm, VS2, €120          │ │
│  │ Lieferzeit: 5 Tage ⚠️             │ │
│  │ [Bestellen]                       │ │
│  └───────────────────────────────────┘ │
│                                         │
│  [ Externe Bestellung aufgeben ]       │
└─────────────────────────────────────────┘
```

**User wählt Lieferant A und klickt "Bestellen"**

```
┌─────────────────────────────────────────┐
│  BESTELLUNG AUFGEBEN                    │
│─────────────────────────────────────────│
│  Lieferant: Lieferant A                 │
│  Artikel: Diamant 3.8mm, VS1            │
│  Preis: €135                            │
│  Lieferzeit: 2 Tage                     │
│                                         │
│  Bestellnummer (extern):                │
│  [ORDER-A-2024-7731]                    │
│                                         │
│  Erwartetes Lieferdatum:                │
│  [📅 17.01.2024]                        │
│                                         │
│  [ Bestellung bestätigen ]              │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- Task-Status: `open` → `in_progress`
- Purchase Order erstellt: `PO-2024-00015`
- Linked to Task `T-2024-00042`
- Expected delivery: 17.01.2024
- Notification an Original-Order: "Stein bestellt, Lieferung 17.01."
- Reminder gesetzt für 17.01.

#### 3. Material kommt an

**Wareneingang scannt Lieferung** (siehe Material Intake)

**System erkennt**:
- Neuer Stein passt zu offener Task `T-2024-00042`
- Auto-Popup:

```
┌─────────────────────────────────────────┐
│  MATERIAL-ZUORDNUNG                     │
│─────────────────────────────────────────│
│  Eingehender Stein passt zu:            │
│                                         │
│  Task #T-2024-00042                     │
│  "Stein für Auftrag #E-2024-00087"      │
│                                         │
│  Stein automatisch zuordnen?            │
│  [ Ja ]  [ Nein, manuell ]              │
└─────────────────────────────────────────┘
```

**User klickt "Ja"**

**System-Aktionen**:
- Task-Status: `in_progress` → `completed`
- Purchase Order: `completed`
- Material `M-2024-00232` linked to Order `E-2024-00087`
- Order-Status: `waiting_stone` → `in_progress` (Auto-Transition!)
- Notification an Goldschmied: "Material da, Auftrag kann fortgesetzt werden"
- Lagerbestand: Diamant 3.8mm: +1 (dann sofort -1 für Order-Reservierung)

---

## Quality Control Workflow

### Szenario
Systematischer QC-Prozess für fertige Arbeiten.

#### QC-Checklist Template

```
┌─────────────────────────────────────────┐
│  QUALITÄTSPRÜFUNG #E-2024-00087         │
│  Ring mit Steinersatz                   │
│─────────────────────────────────────────│
│  VISUELLE PRÜFUNG                       │
│  ☐ Oberfläche sauber & poliert          │
│  ☐ Keine Kratzer oder Dellen            │
│  ☐ Gravuren klar lesbar                 │
│                                         │
│  STEIN-PRÜFUNG                          │
│  ☐ Stein fest eingesetzt                │
│  ☐ Stein korrekt ausgerichtet           │
│  ☐ Krappen gleichmäßig                  │
│  ☐ Keine Beschädigungen am Stein        │
│                                         │
│  FUNKTIONALE PRÜFUNG                    │
│  ☐ Ring rund (nicht verzogen)           │
│  ☐ Passform korrekt                     │
│  ☐ Bewegliche Teile funktionieren       │
│                                         │
│  MESSWERTE                              │
│  ├─ Ringgröße (gemessen): [___]         │
│  ├─ Gewicht: [___] g                    │
│  └─ Steingröße: [___] mm                │
│                                         │
│  FOTOS (Pflicht) 📷                     │
│  ☐ Gesamtansicht                        │
│  ☐ Stein Close-up                       │
│  ☐ Gravur (falls vorhanden)             │
│                                         │
│  NOTIZEN                                │
│  ┌─────────────────────────────────┐   │
│  │                                 │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ENTSCHEIDUNG                           │
│  ○ ✅ Bestanden → Fertigstellen         │
│  ○ ⚠️  Nacharbeit → Zurück an Goldsmith │
│  ○ ❌ Kritisch → Escalation             │
│                                         │
│  [ QC abschließen ]                     │
└─────────────────────────────────────────┘
```

**Wenn "Nacharbeit" gewählt**:

```
┌─────────────────────────────────────────┐
│  NACHARBEIT ERFORDERLICH                │
│─────────────────────────────────────────│
│  Welche Probleme?                       │
│  ☐ Polieren unzureichend                │
│  ☑ Stein nicht optimal ausgerichtet     │
│  ☐ Kratzer vorhanden                    │
│  ☐ Sonstiges                            │
│                                         │
│  Details:                               │
│  ┌─────────────────────────────────┐   │
│  │ "Stein leicht schief, bitte     │   │
│  │  nochmal zentrieren"            │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Zuweisen an:                           │
│  [Johann Schmidt] (Original-Bearbeiter) │
│                                         │
│  [ Zurück an Goldschmied ]              │
└─────────────────────────────────────────┘
```

**System-Aktionen**:
- State: `quality_check` → `in_progress` (zurück)
- Notification an Goldschmied mit QC-Notizen
- QC-Bericht wird zu Job-Historie hinzugefügt
- Counter: "QC-Runden" für Statistiken

---

## Zusammenfassung: Workflow-Patterns

### Pattern 1: Lineare Workflows
```
A → B → C → D → E
```
Beispiel: Material-Eingang (einfach, keine Branches)

### Pattern 2: Bedingte Workflows
```
A → B → [Bedingung]
         ├─→ C1 (wenn X)
         └─→ C2 (wenn Y)
```
Beispiel: Repair (mit/ohne Material-Bestellung)

### Pattern 3: Zyklische Workflows
```
A → B → C
    ↑   ↓
    └───┘ (Loop bei Nacharbeit)
```
Beispiel: QC mit Nacharbeit

### Pattern 4: Parallel Workflows
```
A → [Split]
     ├─→ B1
     ├─→ B2
     └─→ B3
    [Join] → C
```
Beispiel: Multi-Part Order (mehrere Teile gleichzeitig in Bearbeitung)

---

**Document Version**: 1.0
**Last Updated**: 2024-01-15
**Status**: Complete

# Feature Specification: Intelligentes Time-Tracking & ML-gestütztes Workflow-Management

## Executive Summary

Ein umfassendes System zur detaillierten Erfassung, Analyse und Vorhersage von Arbeitsabläufen in der Goldschmiedewerkstatt. Ziel ist die automatische Berechnung realistischer Liefertermine basierend auf historischen Daten und maschinellem Lernen.

---

## 1. Kalender-System

### 1.1 Deadline-Verwaltung

**Features:**
- **Visuelle Auftragszeitlinie**: Gantt-Chart-ähnliche Darstellung aller Aufträge
- **Deadline-Anzeige**: Rot markiert bei Überschreitung, Gelb bei knappen Terminen
- **Zeitplanung**: Geschätzte vs. tatsächliche Arbeitszeit
- **Kapazitätsanzeige**: Verfügbare Arbeitsstunden pro Tag/Woche
- **Konflikt-Erkennung**: Warnung bei zeitlichen Überschneidungen

**Ansichten:**
- Tages-Ansicht: Stündliche Aufteilung
- Wochen-Ansicht: Übersicht aller Aufträge
- Monats-Ansicht: Langfristige Planung
- Auftragsspezifisch: Timeline eines einzelnen Auftrags

### 1.2 Zeitschätzung

**Automatische Schätzung (ML-basiert):**
```
Eingabe:
- Auftragstyp (Ring, Kette, Anhänger, etc.)
- Komplexität (1-5 Sterne)
- Material (Gold 750, Silber 925, etc.)
- Arbeitsschritte (Löten, Fassen, Polieren, etc.)
- Edelsteine (Anzahl, Größe, Art)

Ausgabe:
- Geschätzte Gesamtzeit (Stunden)
- Geschätzte Zeit pro Arbeitsschritt
- Konfidenzintervall (z.B. 4-6 Stunden, 90% sicher)
- Ähnliche vergangene Aufträge als Referenz
```

**Manuelle Eingabe:**
- Goldschmied kann Schätzung überschreiben
- System lernt aus Abweichungen
- Notizen zur Schätzung (z.B. "Kunde sehr anspruchsvoll")

---

## 2. Time-Tracking System

### 2.1 Kern-Funktionen

**Start/Stop-Tracking:**
```
Workflow:
1. Goldschmied scannt QR/NFC-Tag des Auftrags
2. Quick-Action-Menü erscheint
3. Wählt "Zeit erfassen"
4. Wählt Aktivität (z.B. "Löten")
5. Timer startet automatisch
6. Bei erneutem Scan: Timer stoppt
7. Zeit wird gespeichert mit allen Metadaten
```

**Erfasste Daten pro Zeit-Eintrag:**
```json
{
  "time_entry_id": "uuid",
  "order_id": 123,
  "activity_type": "soldering",
  "start_time": "2025-01-15T09:15:00Z",
  "end_time": "2025-01-15T10:45:00Z",
  "duration_minutes": 90,
  "location": "workbench_1",
  "user_id": 5,
  "interruptions": [
    {
      "reason": "customer_call",
      "duration_minutes": 5
    }
  ],
  "materials_used": [
    {
      "material_id": 42,
      "quantity": 2.5,
      "unit": "g"
    }
  ],
  "complexity_rating": 3,
  "quality_check_passed": true,
  "rework_required": false,
  "notes": "Kunde möchte breitere Ringschiene",
  "photos": ["photo_uuid_1", "photo_uuid_2"]
}
```

### 2.2 Aktivitäts-Typen (Presets)

**Standard-Aktivitäten:**
```
Fertigung:
- ⚒️ Löten (Soldering)
- 💎 Fassen (Stone Setting)
- ✨ Polieren (Polishing)
- 🔨 Hämmern/Formen (Forging/Shaping)
- 🔧 Reparatur (Repair)
- 📏 Anpassen (Resizing)
- 🎨 Gravieren (Engraving)
- 🧪 Ätzen/Oxidieren (Etching/Oxidizing)
- 🔍 Qualitätskontrolle (Quality Control)
- 🧹 Nacharbeit (Rework)

Verwaltung:
- 📞 Kundengespräch (Customer Communication)
- 📋 Planung (Planning)
- 📦 Material bestellen (Order Materials)
- 📥 Material annehmen (Receive Materials)
- 🚚 Versand vorbereiten (Prepare Shipping)
- 📸 Foto-Dokumentation (Photo Documentation)

Wartezeit:
- ⏳ Warten auf Material (Waiting for Materials)
- 🔬 Prüfung extern (External Testing)
- 👤 Kundenfreigabe (Customer Approval)
```

**Frequenz-basierte Sortierung:**
- System trackt, welche Aktivitäten am häufigsten verwendet werden
- Zeigt Top 5 ganz oben
- Rest alphabetisch oder nach Kategorie

**Custom-Aktivitäten:**
- Goldschmied kann eigene Aktivitäten anlegen
- Mit Icons, Farben, Beschreibung
- Können an Auftragstyp gebunden werden

### 2.3 Unterbrechungs-Tracking

**Automatische Erkennung:**
- Wenn zwischen Scan-Start und Scan-Stop > 2 Stunden vergehen
- System fragt: "Hattest du Unterbrechungen?"
- Liste häufiger Gründe:
  - Kunde in der Werkstatt
  - Telefongespräch
  - Mittagspause
  - Material holen
  - Anderer Auftrag (Notfall)
  - Werkzeug reparieren

**Manuelle Pause:**
- "Pause"-Button im laufenden Timer
- Grund auswählen
- Automatischer Restart

> ℹ️ **Stand 2026-09-25:** Der frühere "Pause"-Button widersprach dieser Spec —
> er fror nur die Anzeige ein, während der Server im Hintergrund
> weiterzählte, ohne einen Grund zu erfassen. Er wurde deshalb ersatzlos
> entfernt (FE-10, `docs/review/2026-09-25/`). Eine echte, dieser Spec
> entsprechende manuelle Pause (Grund erfassen, als Unterbrechung im Server
> speichern, danach neu berechnen) ist als offener Punkt W2-14 in
> [MASTER-FIX-PLAN.md](../../review/2026-09-25/MASTER-FIX-PLAN.md) verzeichnet.

---

## 3. Quick-Action-Menü (nach QR/NFC-Scan)

### 3.1 Haupt-Aktionen

```
┌─────────────────────────────────────────┐
│     Auftrag #123: Verlobungsring       │
│     Status: In Bearbeitung              │
├─────────────────────────────────────────┤
│                                         │
│  ⏱️  ZEIT ERFASSEN                      │
│     → Aktivität wählen & Timer starten │
│                                         │
│  📍 LAGERORT ÄNDERN                     │
│     Aktuell: Werkbank 1                │
│     → Werkbank 2 / Tresor / Lager      │
│                                         │
│  📦 MATERIAL                            │
│     → Bestellen / Verbraucht erfassen  │
│                                         │
│  👤 KUNDENINFO                          │
│     → Details ändern / Notiz hinzufügen│
│                                         │
│  📸 FOTO                                │
│     → Arbeitsfortschritt dokumentieren │
│                                         │
│  🔄 STATUS ÄNDERN                       │
│     → Fertig / Prüfung / Auslieferung  │
│                                         │
│  📋 DETAILS ANZEIGEN                    │
│     → Zur Auftrags-Detailseite         │
│                                         │
└─────────────────────────────────────────┘
```

### 3.2 Kontext-sensitive Actions

**Wenn Timer läuft:**
```
┌─────────────────────────────────────────┐
│  ⏱️  Timer läuft: Löten                 │
│     Seit 00:23:15                       │
├─────────────────────────────────────────┤
│  ⏸️  PAUSE                              │
│  ⏹️  STOPP (abschließen)                │
│  🔄 AKTIVITÄT WECHSELN                  │
│  ➕ UNTERBRECHUNG ERFASSEN              │
└─────────────────────────────────────────┘
```

**Nach Aktivitätsabschluss:**
```
Aktivität beendet: Löten (23 Min)

✅ Erfolgreich?     [ Ja ] [ Nacharbeit nötig ]
⭐ Komplexität:     [ 1 ] [ 2 ] [ 3 ] [ 4 ] [ 5 ]
💎 Qualität:        [ Bestanden ] [ Nachprüfung ]
📸 Foto?            [ Foto machen ]
📝 Notiz?           [____________]

                    [ Speichern ]
```

---

## 4. Lagerort-Tracking (Location Management)

### 4.1 Locations

**Vordefinierte Orte:**
```
Werkstatt:
- 🔧 Werkbank 1
- 🔧 Werkbank 2
- 🔧 Werkbank 3
- 🔬 Prüfbank
- ✨ Polierstation

Lager:
- 📦 Materialregal
- 🔒 Tresor
- 📥 Eingang (neue Aufträge)
- 📤 Ausgang (fertige Aufträge)

Extern:
- 🚚 Beim Kunden
- 🔬 Labor (Prüfung)
- 🏢 Partner-Werkstatt
- 📬 Versand
```

**Location-History:**
```json
{
  "order_id": 123,
  "location_history": [
    {
      "location": "entrance",
      "timestamp": "2025-01-10T08:00:00Z",
      "changed_by": "user_5"
    },
    {
      "location": "workbench_1",
      "timestamp": "2025-01-10T09:15:00Z",
      "changed_by": "user_5"
    },
    {
      "location": "vault",
      "timestamp": "2025-01-10T17:30:00Z",
      "changed_by": "user_5"
    }
  ],
  "current_location": "vault"
}
```

### 4.2 Auto-Location bei Zeit-Tracking

**Intelligente Vorschläge:**
```
Wenn Aktivität = "Löten"
→ Vorschlag: Werkbank mit Lötstation

Wenn Aktivität = "Polieren"
→ Vorschlag: Polierstation

Wenn Aktivität = "Qualitätskontrolle"
→ Vorschlag: Prüfbank

Wenn Aktivität = "Kundengespräch"
→ Vorschlag: Verkaufsraum

Bei Timer-Stop
→ Vorschlag: "In Tresor legen?"
```

---

## 5. Material-Management mit Time-Tracking

### 5.1 Material-Erfassung

**Beim Arbeiten:**
```
Quick-Action: "Material verbraucht"

→ Material wählen:
  - Gold 750 (18k)
  - Silber 925
  - Edelstein (Diamant 0.5ct)

→ Menge eingeben:
  - [ 2.5 ] g

→ Automatisch:
  - Bestand reduziert
  - Kosten dem Auftrag zugeordnet
  - Zeitpunkt erfasst
  - Mit aktueller Aktivität verknüpft
```

**Bestellung tracken:**
```
Material fehlt während Arbeit:
1. Timer pausiert
2. "Material bestellen" gewählt
3. Material + Menge eingegeben
4. Lieferant gewählt
5. Geschätzte Lieferzeit: 3 Tage
6. → Auftrag automatisch pausiert
7. → Kalendereintrag: "Warten auf Material"
```

### 5.2 Material-Lieferzeit-Learning

**ML-Modell lernt:**
```
Lieferant A, Gold 750:
- Bestellung 1: 2 Tage
- Bestellung 2: 3 Tage
- Bestellung 3: 2 Tage
→ Durchschnitt: 2.3 Tage
→ Bei nächster Planung einbeziehen
```

---

## 6. Datenmodell für ML

### 6.1 Haupt-Entitäten

**Order (Auftrag):**
```json
{
  "order_id": 123,
  "customer_id": 456,
  "order_type": "engagement_ring",
  "created_at": "2025-01-10T08:00:00Z",
  "deadline": "2025-01-25T18:00:00Z",
  "estimated_hours": 8.0,
  "actual_hours": 9.5,
  "completed_at": "2025-01-24T16:30:00Z",
  "complexity_rating": 4,
  "materials": [...],
  "specifications": {
    "metal": "gold_750",
    "weight_grams": 5.2,
    "stones": [
      {
        "type": "diamond",
        "carat": 0.5,
        "count": 1,
        "setting_type": "prong"
      }
    ],
    "size": 54,
    "width_mm": 3.0,
    "custom_engraving": true,
    "finish": "high_polish"
  },
  "customer_attributes": {
    "is_premium": true,
    "urgency": "high",
    "detail_oriented": true,
    "previous_orders": 3
  }
}
```

**TimeEntry (Zeiteintrag):**
```json
{
  "entry_id": "uuid",
  "order_id": 123,
  "user_id": 5,
  "activity_type": "stone_setting",
  "start_time": "2025-01-15T10:00:00Z",
  "end_time": "2025-01-15T11:30:00Z",
  "duration_minutes": 90,
  "interruptions": [
    {
      "reason": "customer_call",
      "duration_minutes": 10
    }
  ],
  "location": "workbench_1",
  "complexity_rating": 4,
  "quality_rating": 5,
  "rework_required": false,
  "materials_used": [...],
  "tools_used": ["prong_pusher", "loupe_10x"],
  "weather_conditions": {
    "temperature_c": 22,
    "humidity_percent": 45
  },
  "user_state": {
    "fatigue_level": 2,
    "experience_years": 15
  },
  "notes": "Stein saß sehr fest, brauchte extra Vorsicht"
}
```

**Activity (Aktivität):**
```json
{
  "activity_id": 42,
  "name": "Löten",
  "category": "fabrication",
  "icon": "⚒️",
  "color": "#ff6b6b",
  "average_duration_minutes": 45,
  "requires_tools": ["torch", "flux", "solder"],
  "typical_for_order_types": [
    "ring",
    "chain_repair",
    "earrings"
  ],
  "usage_count": 1234,
  "last_used": "2025-01-15T11:30:00Z"
}
```

### 6.2 ML-Features (Input für Modelle)

**Order-Level Features:**
```python
# Auftragsspezifisch
- order_type (categorical)
- complexity_rating (1-5)
- metal_type (categorical)
- metal_weight_grams (numeric)
- stone_count (numeric)
- stone_total_carat (numeric)
- setting_type (categorical)
- has_engraving (boolean)
- finish_type (categorical)
- size_adjustment_required (boolean)

# Kundenbezogen
- customer_is_premium (boolean)
- customer_urgency (low/medium/high)
- customer_detail_oriented (boolean)
- customer_previous_orders (numeric)
- customer_avg_change_requests (numeric)

# Zeitlich
- order_created_weekday (categorical)
- order_created_month (categorical)
- deadline_in_days (numeric)
- current_workload_hours (numeric)
- pending_orders_count (numeric)

# Historisch
- similar_orders_avg_time (numeric)
- user_avg_speed_for_type (numeric)
- seasonal_factor (numeric)
```

**Activity-Level Features:**
```python
# Aktivitätsspezifisch
- activity_type (categorical)
- user_experience_years (numeric)
- user_fatigue_level (1-5)
- time_of_day (hour)
- day_of_week (categorical)

# Umgebung
- workbench_occupancy (numeric)
- temperature (numeric)
- humidity (numeric)

# Historisch
- user_avg_duration_for_activity (numeric)
- last_7_days_avg_speed (numeric)
- activity_frequency_rank (numeric)
```

---

## 7. ML-Modelle

### 7.1 Modell 1: Zeitschätzung (Duration Prediction)

**Ziel:** Vorhersage der Gesamtarbeitszeit für neuen Auftrag

**Algorithmus:** Gradient Boosting (XGBoost/LightGBM)

**Training:**
```python
Input: Order Features (siehe 6.2)
Output: estimated_hours (regression)

Metriken:
- RMSE (Root Mean Squared Error)
- MAPE (Mean Absolute Percentage Error)
- R² Score

Training Set:
- Alle abgeschlossenen Aufträge (>= 100)
- Features normalisiert
- Cross-Validation (5-fold)
```

**Verwendung:**
```python
new_order = {
  "order_type": "engagement_ring",
  "complexity": 4,
  "metal": "gold_750",
  "stones": [{"carat": 0.5}],
  ...
}

prediction = model.predict(new_order)
# Output:
{
  "estimated_hours": 8.5,
  "confidence_interval": [7.2, 9.8],
  "confidence_level": 0.90,
  "similar_orders": [
    {"order_id": 456, "actual_hours": 8.2},
    {"order_id": 789, "actual_hours": 9.1}
  ]
}
```

### 7.2 Modell 2: Aktivitätsdauer (Activity Duration)

**Ziel:** Vorhersage wie lange eine spezifische Aktivität dauert

**Algorithmus:** Random Forest

**Features:**
- Activity type
- Order complexity
- User experience
- Time of day
- Recent performance

**Output:** Geschätzte Minuten für Aktivität

### 7.3 Modell 3: Deadline-Berechnung (Delivery Date)

**Ziel:** Realistisches Abholdatum unter Berücksichtigung aller Faktoren

**Komplexer Algorithmus:**
```python
def calculate_delivery_date(order):
    # 1. Geschätzte Arbeitszeit
    estimated_hours = duration_model.predict(order)

    # 2. Aktuelle Auslastung
    current_workload = get_pending_workload()

    # 3. Arbeitstage berechnen
    workdays = get_available_workdays(
        start_date=today,
        user_capacity_hours_per_day=6,  # Netto-Arbeitszeit
        holidays=holidays_calendar
    )

    # 4. Materiallieferzeiten
    material_lead_time = predict_material_delivery(
        order.materials,
        suppliers
    )

    # 5. Puffer für Unvorhergesehenes
    buffer_hours = estimated_hours * 0.2  # 20% Puffer

    # 6. Kunde-spezifische Faktoren
    if order.customer.is_premium:
        priority_boost = 0.8  # 20% schneller
    else:
        priority_boost = 1.0

    # 7. Saisonale Faktoren
    seasonal_factor = get_seasonal_workload(today.month)

    # 8. Berechnung
    total_hours = (
        estimated_hours + buffer_hours
    ) * priority_boost * seasonal_factor

    # 9. Kalender-Logik
    delivery_date = calculate_calendar_date(
        start_date=today,
        required_hours=total_hours,
        workdays=workdays,
        current_queue=current_workload,
        material_wait=material_lead_time
    )

    return {
        "delivery_date": delivery_date,
        "estimated_hours": estimated_hours,
        "buffer_hours": buffer_hours,
        "material_wait_days": material_lead_time,
        "total_calendar_days": (delivery_date - today).days,
        "confidence": 0.85
    }
```

### 7.4 Modell 4: Anomalie-Erkennung

**Ziel:** Erkennung ungewöhnlich langer Aktivitäten

**Use Case:**
```
Normale Löt-Aktivität: 30-45 Min
Aktuelle Aktivität: 120 Min

→ Alert: "Löten dauert ungewöhnlich lange. Alles OK?"
→ Mögliche Gründe:
  - Komplikationen
  - Werkzeug defekt
  - Nacharbeit nötig
```

**Algorithmus:** Isolation Forest oder Autoencoder

---

## 8. Kalender-Integration & Planung

### 8.1 Intelligente Planung

**Auto-Scheduling:**
```python
def schedule_new_order(order, requested_deadline):
    # 1. Zeit schätzen
    estimated_time = duration_model.predict(order)

    # 2. Aktuelle Aufträge laden
    current_schedule = get_current_schedule()

    # 3. Verfügbare Slots finden
    available_slots = find_available_slots(
        required_hours=estimated_time,
        deadline=requested_deadline,
        current_schedule=current_schedule,
        min_chunk_hours=2  # Mindestens 2h am Stück
    )

    # 4. Optimal-Slot auswählen
    best_slot = select_optimal_slot(
        available_slots,
        preferences={
            "minimize_fragmentation": True,
            "prefer_morning": True,  # Goldschmied arbeitet morgens besser
            "avoid_friday_afternoon": True  # Oft Kundentermine
        }
    )

    # 5. Kalender aktualisieren
    schedule_order(order, best_slot)

    # 6. Warnung bei Konflikt
    if not can_meet_deadline(order, requested_deadline):
        return {
            "scheduled": True,
            "warning": "Deadline knapp!",
            "suggested_deadline": calculated_deadline,
            "rush_fee_suggested": True
        }

    return {
        "scheduled": True,
        "time_slots": best_slot,
        "delivery_date": best_slot.end_date
    }
```

### 8.2 Kalender-Ansichten

**Tagesansicht:**
```
Mittwoch, 15. Januar 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

08:00 - 10:30 │ 📋 Ring #123 - Fassen
              │ ⏱️ Geplant: 2.5h
              │ 📍 Werkbank 1

10:30 - 11:00 │ ☕ Pause

11:00 - 13:00 │ 📋 Kette #456 - Löten
              │ ⏱️ Geplant: 2h
              │ 📍 Werkbank 2

13:00 - 14:00 │ 🍽️ Mittagspause

14:00 - 16:30 │ 📋 Ring #123 - Polieren
              │ ⏱️ Geplant: 2.5h
              │ 📍 Polierstation

16:30 - 17:00 │ 📋 Ring #123 - Qualitätskontrolle
              │ ⏱️ Geplant: 0.5h

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gesamt: 7.5h | Auslastung: 94%
```

**Wochenansicht:**
```
KW 3 - Januar 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mo  Di  Mi  Do  Fr  Sa  So
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8h  7h  7.5h 6h  4h  -   -   Gesamt: 32.5h

Aufträge diese Woche:
• Ring #123    [████████░░] 80% - Deadline: Fr
• Kette #456   [███░░░░░░░] 30% - Deadline: Mo
• Anhänger #789[█░░░░░░░░░] 10% - Deadline: Mi (nächste Woche)

⚠️ Ring #123 läuft Deadline-Gefahr!
```

---

## 9. Erweiterte Features

### 9.1 Foto-Dokumentation mit Zeitstempel

**Workflow:**
```
1. Nach Aktivität abschließen
2. "Foto machen" Button
3. Kamera öffnet sich
4. Foto wird geschossen
5. Automatisch verknüpft mit:
   - Auftrag
   - Aktivität
   - Zeitstempel
   - Benutzer
   - Location
6. Optional: Notiz hinzufügen
7. Speichern
```

**ML-Nutzung:**
- Computer Vision zur Qualitätskontrolle
- Automatische Erkennung von Fehlern
- Fortschritts-Tracking durch Bildvergleich

### 9.2 Batch-Processing Erkennung

**ML erkennt ähnliche Aufträge:**
```
Neue Aufträge:
- Ring #801: Trauring Gold 750, Größe 54
- Ring #802: Trauring Gold 750, Größe 58
- Ring #803: Trauring Gold 750, Größe 52

ML-Vorschlag:
"Diese 3 Ringe sind sehr ähnlich.
Batch-Processing könnte 25% Zeit sparen.
Möchtest du sie zusammen bearbeiten?"

Vorteile:
- Werkzeug-Setup nur 1x
- Material-Vorbereitung effizienter
- Flow-State durch wiederholte Arbeit
```

### 9.3 Mitarbeiter-Spezialisierung

**System lernt Stärken:**
```
User #5 (Max):
- Besonders schnell bei: Fassen (20% über Durchschnitt)
- Durchschnittlich bei: Löten
- Langsamer bei: Polieren (15% unter Durchschnitt)

User #8 (Anna):
- Besonders schnell bei: Polieren (30% über Durchschnitt)
- Spezialisiert auf: Gravuren

→ Auto-Vorschlag bei Auftragsplanung:
  "Ring #123 (Fassung komplex) → Max zuweisen"
  "Ring #456 (Hochglanzpolierung) → Anna zuweisen"
```

### 9.4 Kunden-Kommunikations-Tracker

**Automatische Updates:**
```
Kunde möchte informiert werden:
- Bei 50% Fortschritt
- 1 Tag vor Fertigstellung
- Bei Verzögerungen

System sendet automatisch:
"Guten Tag Herr Müller,
Ihr Verlobungsring ist zu 50% fertig.
Die Fassung ist abgeschlossen, jetzt kommt das Polieren.
Voraussichtliche Fertigstellung: Freitag 18:00 Uhr.

Fortschritt: [████████░░] 80%
Zeit investiert: 6.5h von geschätzten 8h

Mit freundlichen Grüßen,
Goldschmiede Schmidt"
```

### 9.5 Nacharbeits-Analyse

**ML-Modell zur Fehlervermeidung:**
```
Analyse:
- 15% aller Fassungen erfordern Nacharbeit
- Hauptursache: Zu schnelles Arbeiten (< 30 Min)
- Tritt auf bei: Ermüdung (> 6h Arbeitstag)

Empfehlung:
"Fassungs-Arbeiten sollten vormittags geplant werden.
Mindestens 45 Min einplanen.
Pause davor einlegen."

Ergebnis:
- Nacharbeitsquote sinkt auf 5%
- Kundenzufriedenheit steigt
```

### 9.6 Saisonale Anpassungen

**Historische Daten:**
```
Dezember:
- 3x höheres Auftragsvolumen
- Durchschnittliche Bearbeitungszeit +15% (Stress)
- Viele Reparaturen nach Weihnachten

ML-Empfehlung:
"Für Dezember-Aufträge 20% Puffer einplanen.
Keine neuen Aufträge ab 15. Dezember annehmen.
Oder: Temporäre Hilfe einstellen."
```

---

## 10. Datenbank-Schema

### 10.1 Tabellen

```sql
-- Aufträge
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    order_type VARCHAR(50),
    created_at TIMESTAMP,
    deadline TIMESTAMP,
    completed_at TIMESTAMP,
    estimated_hours DECIMAL(5,2),
    complexity_rating INTEGER CHECK (complexity_rating BETWEEN 1 AND 5),
    specifications JSONB,
    current_location VARCHAR(50),
    status VARCHAR(20)
);

-- Zeiterfassung
CREATE TABLE time_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id INTEGER REFERENCES orders(id),
    user_id INTEGER REFERENCES users(id),
    activity_id INTEGER REFERENCES activities(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_minutes INTEGER,
    location VARCHAR(50),
    complexity_rating INTEGER,
    quality_rating INTEGER,
    rework_required BOOLEAN DEFAULT FALSE,
    notes TEXT,
    metadata JSONB
);

-- Aktivitäten
CREATE TABLE activities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    icon VARCHAR(10),
    color VARCHAR(7),
    usage_count INTEGER DEFAULT 0,
    last_used TIMESTAMP,
    average_duration_minutes DECIMAL(5,2),
    is_custom BOOLEAN DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id)
);

-- Unterbrechungen
CREATE TABLE interruptions (
    id SERIAL PRIMARY KEY,
    time_entry_id UUID REFERENCES time_entries(id),
    reason VARCHAR(100),
    duration_minutes INTEGER,
    timestamp TIMESTAMP
);

-- Location History
CREATE TABLE location_history (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    location VARCHAR(50),
    timestamp TIMESTAMP,
    changed_by INTEGER REFERENCES users(id)
);

-- Material-Verwendung
CREATE TABLE material_usage (
    id SERIAL PRIMARY KEY,
    time_entry_id UUID REFERENCES time_entries(id),
    material_id INTEGER REFERENCES materials(id),
    quantity DECIMAL(10,2),
    unit VARCHAR(20),
    cost DECIMAL(10,2)
);

-- Fotos
CREATE TABLE order_photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id INTEGER REFERENCES orders(id),
    time_entry_id UUID REFERENCES time_entries(id),
    file_path VARCHAR(500),
    timestamp TIMESTAMP,
    taken_by INTEGER REFERENCES users(id),
    notes TEXT
);

-- ML-Vorhersagen (für Audit)
CREATE TABLE ml_predictions (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    model_version VARCHAR(20),
    predicted_hours DECIMAL(5,2),
    confidence_interval_lower DECIMAL(5,2),
    confidence_interval_upper DECIMAL(5,2),
    confidence_level DECIMAL(3,2),
    features_used JSONB,
    created_at TIMESTAMP,
    actual_hours DECIMAL(5,2)  -- Wird nach Abschluss gefüllt
);
```

### 10.2 Indizes für Performance

```sql
CREATE INDEX idx_time_entries_order ON time_entries(order_id);
CREATE INDEX idx_time_entries_user ON time_entries(user_id);
CREATE INDEX idx_time_entries_activity ON time_entries(activity_id);
CREATE INDEX idx_time_entries_start_time ON time_entries(start_time);
CREATE INDEX idx_orders_deadline ON orders(deadline);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_activities_usage ON activities(usage_count DESC);
```

---

## 11. API-Endpunkte

### 11.1 Time-Tracking

```typescript
// Timer starten
POST /api/v1/time-tracking/start
{
  "order_id": 123,
  "activity_id": 42,
  "location": "workbench_1"
}
Response: { "entry_id": "uuid", "started_at": "..." }

// Timer stoppen
POST /api/v1/time-tracking/stop/{entry_id}
{
  "complexity_rating": 4,
  "quality_rating": 5,
  "rework_required": false,
  "notes": "..."
}

// Unterbrechung hinzufügen
POST /api/v1/time-tracking/{entry_id}/interruptions
{
  "reason": "customer_call",
  "duration_minutes": 10
}

// Aktuelle Timer abrufen
GET /api/v1/time-tracking/active
Response: [{ "entry_id": "...", "order_id": 123, ... }]
```

### 11.2 ML-Vorhersagen

```typescript
// Zeitschätzung für neuen Auftrag
POST /api/v1/ml/estimate-duration
{
  "order_type": "engagement_ring",
  "complexity": 4,
  "specifications": { ... }
}
Response: {
  "estimated_hours": 8.5,
  "confidence_interval": [7.2, 9.8],
  "similar_orders": [...]
}

// Deadline berechnen
POST /api/v1/ml/calculate-deadline
{
  "order": { ... },
  "requested_deadline": "2025-02-01"
}
Response: {
  "feasible": true,
  "suggested_deadline": "2025-01-28",
  "workload_analysis": { ... }
}
```

### 11.3 Kalender

```typescript
// Kalender abrufen
GET /api/v1/calendar?start=2025-01-01&end=2025-01-31
Response: {
  "days": [
    {
      "date": "2025-01-15",
      "scheduled_hours": 7.5,
      "capacity_hours": 8.0,
      "orders": [...]
    }
  ]
}

// Auftrag planen
POST /api/v1/calendar/schedule
{
  "order_id": 123,
  "preferred_slots": [...]
}
```

---

## 12. Frontend-Komponenten

### 12.1 Quick-Action-Modal

```tsx
<QuickActionModal order={order}>
  <ActionButton
    icon="⏱️"
    label="Zeit erfassen"
    onClick={() => startTimeTracking(order)}
  />
  <ActionButton
    icon="📍"
    label="Lagerort ändern"
    onClick={() => changeLocation(order)}
  />
  <ActionButton
    icon="📦"
    label="Material"
    onClick={() => manageMaterial(order)}
  />
  ...
</QuickActionModal>
```

### 12.2 Activity-Picker

```tsx
<ActivityPicker
  onSelect={(activity) => startTimer(activity)}
  sortBy="frequency"
  showRecent={5}
/>
```

### 12.3 Kalender-Komponente

```tsx
<Calendar
  view="week"
  orders={orders}
  onDrop={(order, slot) => reschedule(order, slot)}
  showCapacity={true}
  highlightDeadlines={true}
/>
```

---

## 13. Implementation Roadmap

### Phase 1: Basis Time-Tracking (2 Wochen)
- [ ] Time-Entry Datenmodell
- [ ] Start/Stop API
- [ ] Aktivitäts-Verwaltung
- [ ] Basic Quick-Action-Menü
- [ ] Scanner-Integration

### Phase 2: Location & Material (1 Woche)
- [ ] Location-Tracking
- [ ] Material-Verbrauchs-Erfassung
- [ ] Location-History

### Phase 3: Erweiterte Features (2 Wochen)
- [ ] Unterbrechungs-Tracking
- [ ] Foto-Upload
- [ ] Komplexitäts-/Qualitäts-Ratings
- [ ] Aktivitäts-Presets

### Phase 4: Kalender (2 Wochen)
- [ ] Kalender-Datenmodell
- [ ] Tages-/Wochen-/Monatsansicht
- [ ] Drag & Drop Planung
- [ ] Deadline-Warnungen

### Phase 5: ML-Basis (3 Wochen)
- [ ] Daten-Export für ML
- [ ] Feature-Engineering
- [ ] Erstes Zeitschätzungs-Modell
- [ ] Model-API-Integration

### Phase 6: ML-Advanced (4 Wochen)
- [ ] Aktivitätsdauer-Vorhersage
- [ ] Deadline-Berechnung
- [ ] Batch-Erkennung
- [ ] Anomalie-Detektion

### Phase 7: Optimierung (2 Wochen)
- [ ] Performance-Tuning
- [ ] UI/UX-Verbesserungen
- [ ] Mobile-Optimierung
- [ ] Reporting & Analytics

**Gesamtdauer: ~16 Wochen (4 Monate)**

---

## 14. Success Metrics (KPIs)

### Operativ:
- ✅ **Tracking-Quote**: > 90% aller Arbeitszeiten erfasst
- ✅ **Scanner-Nutzung**: > 80% der Aufträge per QR/NFC geöffnet
- ✅ **Foto-Dokumentation**: Durchschnittlich 3+ Fotos pro Auftrag

### Qualität:
- ✅ **Zeitschätzungs-Genauigkeit**: MAPE < 15%
- ✅ **Deadline-Einhaltung**: > 95%
- ✅ **Nacharbeitsquote**: < 5%

### Effizienz:
- ✅ **Durchschnittszeit pro Auftragstyp**: -10% nach 6 Monaten
- ✅ **Auslastungsoptimierung**: +15% produktive Zeit
- ✅ **Material-Verschwendung**: -20%

### Business:
- ✅ **Kundenzufriedenheit**: +25%
- ✅ **Termintreue**: 98%+
- ✅ **Umsatz pro Stunde**: +20%

---

## 15. Datenschutz & Compliance

### DSGVO-Konformität:
- Anonymisierung von Trainingsdaten nach 2 Jahren
- Kunden-Opt-out für ML-Verwendung
- Foto-Speicherung mit Einwilligung
- Recht auf Löschung

### Audit-Trail:
- Alle Änderungen an Zeiteinträgen geloggt
- ML-Vorhersagen nachvollziehbar
- User-Aktionen protokolliert

---

## 16. Zukünftige Erweiterungen

### Voice-Interface:
```
"Starte Zeiterfassung für Ring 123, Aktivität Löten"
"Pause für 10 Minuten, Grund: Kundengespräch"
"Wie lange brauche ich noch für Ring 123?"
→ "Geschätzt noch 45 Minuten"
```

### AR-Integration:
- AR-Brille zeigt Timer beim Arbeiten
- Hands-free Foto-Dokumentation
- Schritt-für-Schritt-Anleitungen eingeblendet

### IoT-Sensoren:
- Automatische Erkennung: "Werkzeug in Hand = Timer läuft"
- Temperatur/Luftfeuchtigkeit für optimale Arbeitsbedingungen
- Werkbank-Belegung automatisch tracken

### Multi-Werkstatt-Sync:
- Zentrale Datenbank für mehrere Standorte
- Best-Practices-Sharing
- Vergleichs-Benchmarks

---

## Fazit

Dieses System verwandelt eine traditionelle Goldschmiede-Werkstatt in eine **datengetriebene, KI-optimierte Produktionsstätte**. Es verbindet:

1. ✅ **Einfachheit** (QR-Scan + Quick-Actions)
2. ✅ **Detailtiefe** (Minutengenaues Tracking)
3. ✅ **Intelligenz** (ML-Vorhersagen)
4. ✅ **Praxisnähe** (Echte Workflows berücksichtigt)

**ROI:**
- Zeitersparnis: 2-3 Stunden/Woche durch optimierte Planung
- Termintreue: Zufriedenere Kunden, mehr Weiterempfehlungen
- Effizienz: 15-20% mehr Aufträge bei gleicher Arbeitszeit

**Das System zahlt sich in < 6 Monaten aus!** 🎯

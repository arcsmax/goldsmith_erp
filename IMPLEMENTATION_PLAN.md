# Implementation Plan: Time-Tracking & Quick-Actions (Phase 5)

## Aktueller Stand

✅ **Abgeschlossen:**
- Phase 1: Kritische Bugs behoben
- Phase 2: User & Material Management (Backend)
- Phase 3: Frontend-Architektur mit React Router
- Phase 4: Tab-Memory System mit QR/NFC Scanner

## Nächster Schritt: Phase 5 - Time-Tracking Foundation

### Ziel
Ein funktionierendes Time-Tracking-System, das die Basis für ML und Kalender bildet.

---

## Phase 5.1: Backend - Datenmodell & APIs (Priorität 1)

### 5.1.1 Datenbank-Schema erstellen

**Neue Tabellen:**

```sql
1. activities (Aktivitäts-Presets)
   - id, name, category, icon, color
   - usage_count, average_duration_minutes
   - is_custom, created_by

2. time_entries (Haupt-Tracking)
   - id (UUID), order_id, user_id, activity_id
   - start_time, end_time, duration_minutes
   - location, complexity_rating, quality_rating
   - rework_required, notes, metadata (JSONB)

3. interruptions (Unterbrechungen)
   - id, time_entry_id, reason
   - duration_minutes, timestamp

4. location_history (Lagerort-Verlauf)
   - id, order_id, location
   - timestamp, changed_by

5. order_photos (Foto-Dokumentation)
   - id (UUID), order_id, time_entry_id
   - file_path, timestamp, taken_by, notes
```

**Aufgaben:**
- [ ] Alembic Migration erstellen
- [ ] SQLAlchemy Models definieren
- [ ] Indizes für Performance
- [ ] Seed-Data für Standard-Aktivitäten

### 5.1.2 Pydantic Schemas

**Neue Schemas:**
```python
# models/activity.py
- ActivityBase, ActivityCreate, ActivityRead, ActivityUpdate

# models/time_entry.py
- TimeEntryBase, TimeEntryCreate, TimeEntryRead
- TimeEntryStart, TimeEntryStop
- TimeEntryWithDetails (inkl. Activity, Order)

# models/location.py
- LocationHistoryCreate, LocationHistoryRead

# models/interruption.py
- InterruptionCreate, InterruptionRead
```

**Aufgaben:**
- [ ] Schema-Dateien erstellen
- [ ] Validierungen hinzufügen
- [ ] from_attributes konfigurieren

### 5.1.3 Services Layer

**Neue Services:**
```python
# services/activity_service.py
- get_all_activities()
- get_popular_activities(limit=5)
- create_custom_activity()
- increment_usage_count()

# services/time_tracking_service.py
- start_timer(order_id, activity_id, location)
- stop_timer(entry_id, ratings, notes)
- pause_timer(entry_id, reason)
- resume_timer(entry_id)
- get_active_timers(user_id)
- get_time_entries_by_order(order_id)

# services/location_service.py
- update_location(order_id, location, user_id)
- get_location_history(order_id)
- get_current_location(order_id)
```

**Aufgaben:**
- [ ] Service-Dateien erstellen
- [ ] Business-Logik implementieren
- [ ] Error-Handling

### 5.1.4 API Router

**Neue Endpoints:**
```python
# api/routers/time_tracking.py

POST   /time-tracking/start
POST   /time-tracking/{entry_id}/stop
POST   /time-tracking/{entry_id}/pause
POST   /time-tracking/{entry_id}/resume
GET    /time-tracking/active
GET    /time-tracking/order/{order_id}
POST   /time-tracking/{entry_id}/interruptions

# api/routers/activities.py

GET    /activities
GET    /activities/popular
POST   /activities
PUT    /activities/{id}
DELETE /activities/{id}

# api/routers/locations.py

POST   /locations/update
GET    /locations/history/{order_id}
GET    /locations/current/{order_id}
```

**Aufgaben:**
- [ ] Router-Dateien erstellen
- [ ] Endpoints implementieren
- [ ] Permissions hinzufügen
- [ ] In main.py registrieren

### 5.1.5 Seed Standard-Aktivitäten

**Aktivitäten anlegen:**
```python
Standard-Aktivitäten (15):
- Löten, Fassen, Polieren, Hämmern/Formen
- Reparatur, Anpassen, Gravieren, Ätzen
- Qualitätskontrolle, Nacharbeit
- Kundengespräch, Planung
- Material bestellen, Material annehmen
- Versand vorbereiten

Kategorien:
- fabrication (Fertigung)
- administration (Verwaltung)
- waiting (Wartezeit)
```

**Aufgaben:**
- [ ] Seed-Script erstellen
- [ ] Icons & Farben definieren
- [ ] Script in Migration einbinden

---

## Phase 5.2: Frontend - Quick-Actions & Timer (Priorität 2)

### 5.2.1 Types erweitern

**Neue TypeScript Types:**
```typescript
// types.ts

export interface ActivityType {
  id: number;
  name: string;
  category: string;
  icon: string;
  color: string;
  usage_count: number;
  average_duration_minutes: number;
}

export interface TimeEntryType {
  id: string; // UUID
  order_id: number;
  activity: ActivityType;
  start_time: string;
  end_time?: string;
  duration_minutes?: number;
  location?: string;
  is_active: boolean;
}

export interface QuickActionType {
  id: string;
  icon: string;
  label: string;
  action: () => void;
}
```

**Aufgaben:**
- [ ] Types in types.ts hinzufügen
- [ ] Input/Output-Types definieren

### 5.2.2 API Client erweitern

**Neue API Services:**
```typescript
// api/time-tracking.ts
export const timeTrackingApi = {
  startTimer(orderId, activityId, location)
  stopTimer(entryId, data)
  pauseTimer(entryId, reason)
  getActiveTimers()
  getOrderEntries(orderId)
}

// api/activities.ts
export const activitiesApi = {
  getAll()
  getPopular(limit)
  create(activity)
}

// api/locations.ts
export const locationsApi = {
  updateLocation(orderId, location)
  getHistory(orderId)
}
```

**Aufgaben:**
- [ ] API-Client-Dateien erstellen
- [ ] In api/index.ts exportieren

### 5.2.3 Quick-Action-Modal

**Komponente:**
```tsx
// components/QuickActionModal.tsx

<QuickActionModal
  order={order}
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
>
  <QuickAction
    icon="⏱️"
    label="Zeit erfassen"
    onClick={() => startTimeTracking()}
  />
  <QuickAction
    icon="📍"
    label="Lagerort ändern"
    onClick={() => changeLocation()}
  />
  <QuickAction
    icon="📦"
    label="Material"
    onClick={() => manageMaterial()}
  />
  ...
</QuickActionModal>
```

**Features:**
- Modal-Dialog mit Overlay
- Icon + Label pro Action
- Keyboard-Navigation (ESC schließt)
- Mobile-optimiert

**Aufgaben:**
- [ ] QuickActionModal.tsx erstellen
- [ ] Styling in quick-actions.css
- [ ] Integration in ScannerPage

### 5.2.4 Activity-Picker

**Komponente:**
```tsx
// components/ActivityPicker.tsx

<ActivityPicker
  onSelect={(activity) => handleSelect(activity)}
  sortBy="frequency"
  showRecent={5}
/>
```

**Features:**
- Liste aller Aktivitäten
- Top 5 nach Häufigkeit oben
- Icons & Farben anzeigen
- Durchschnittliche Dauer anzeigen
- Suchfeld für Filter

**Aufgaben:**
- [ ] ActivityPicker.tsx erstellen
- [ ] Styling
- [ ] Frequency-Sortierung implementieren

### 5.2.5 Timer-Widget

**Komponente:**
```tsx
// components/TimerWidget.tsx

<TimerWidget
  entry={activeEntry}
  onPause={() => pauseTimer()}
  onStop={() => stopTimer()}
/>
```

**Features:**
- Live-Countdown (MM:SS)
- Pause/Resume Buttons
- Stop mit Rating-Dialog
- Sticky Position (immer sichtbar)

**Aufgaben:**
- [ ] TimerWidget.tsx erstellen
- [ ] useInterval Hook für Live-Update
- [ ] Styling (Fixed Position)

### 5.2.6 Location-Picker

**Komponente:**
```tsx
// components/LocationPicker.tsx

<LocationPicker
  currentLocation={order.location}
  onSelect={(location) => updateLocation(location)}
/>
```

**Locations:**
```
Werkstatt: Werkbank 1-3, Prüfbank, Polierstation
Lager: Materialregal, Tresor, Eingang, Ausgang
Extern: Beim Kunden, Labor, Partner, Versand
```

**Aufgaben:**
- [ ] LocationPicker.tsx erstellen
- [ ] Icon pro Location
- [ ] Grid-Layout
- [ ] Styling

### 5.2.7 ScannerPage erweitern

**Neuer Flow:**
```tsx
1. Scan Order QR-Code
2. Quick-Action-Modal öffnet sich
3. User wählt "Zeit erfassen"
4. Activity-Picker erscheint
5. User wählt Aktivität
6. Timer startet automatisch
7. Navigation zu OrderDetailPage
```

**Aufgaben:**
- [ ] Quick-Action-Modal integrieren
- [ ] State-Management für Modal
- [ ] Auto-Navigation nach Action

### 5.2.8 OrderDetailPage erweitern

**Neuer Tab: "Zeiterfassung"**
```tsx
<OrderDetailPage>
  <Tabs>
    <Tab name="details">...</Tab>
    <Tab name="materials">...</Tab>
    <Tab name="time-tracking">
      <TimeTrackingTab
        entries={timeEntries}
        activeEntry={activeTimer}
        onStartTimer={() => ...}
      />
    </Tab>
    ...
  </Tabs>
</OrderDetailPage>
```

**Tab-Content:**
- Liste aller Zeit-Einträge für diesen Auftrag
- Gesamte Zeit anzeigen
- Chart: Zeit pro Aktivität
- "Zeit erfassen" Button

**Aufgaben:**
- [ ] TimeTrackingTab.tsx erstellen
- [ ] Tab in OrderDetailPage integrieren
- [ ] Styling

---

## Phase 5.3: Integration & Testing (Priorität 3)

### 5.3.1 End-to-End-Workflow testen

**Test-Szenarien:**

**Szenario 1: Einfacher Timer**
```
1. Scanner öffnen
2. Auftrag #123 scannen
3. "Zeit erfassen" wählen
4. "Löten" wählen
5. Timer startet
6. Nach 30 Min: Timer stoppen
7. Rating abgeben (Komplexität 3/5)
8. Speichern
9. Verifizieren: Zeit in DB gespeichert
```

**Szenario 2: Mit Unterbrechung**
```
1. Timer läuft für "Fassen"
2. Kunde kommt rein
3. Timer pausieren → "Kundengespräch"
4. 10 Min später: Timer fortsetzen
5. Nach 40 Min: Stoppen
6. Verifizieren: Unterbrechung erfasst
```

**Szenario 3: Location-Wechsel**
```
1. Auftrag #456 öffnen
2. Quick-Action: "Lagerort ändern"
3. "Werkbank 2" wählen
4. Verifizieren: Location aktualisiert
5. History zeigt Wechsel
```

**Aufgaben:**
- [ ] Manuelle Tests durchführen
- [ ] Edge-Cases prüfen
- [ ] Performance testen

### 5.3.2 Daten-Validierung

**Prüfen:**
- [ ] Zeitstempel korrekt (UTC)
- [ ] Duration-Berechnung stimmt
- [ ] Unterbrechungen korrekt zugeordnet
- [ ] Location-History vollständig
- [ ] Usage-Count wird inkrementiert

### 5.3.3 UI/UX-Polish

**Verbesserungen:**
- [ ] Loading-States für Timer
- [ ] Smooth Transitions
- [ ] Error-Messages bei Netzwerkfehlern
- [ ] Confirmation-Dialoge
- [ ] Mobile-Responsiveness prüfen

---

## Implementierungs-Reihenfolge

### Tag 1-2: Backend Foundation
1. ✅ Datenbank-Schema (Migration)
2. ✅ SQLAlchemy Models
3. ✅ Pydantic Schemas
4. ✅ Seed Standard-Aktivitäten

### Tag 3-4: Backend Services & APIs
5. ✅ Activity Service & Router
6. ✅ Time-Tracking Service & Router
7. ✅ Location Service & Router
8. ✅ APIs in main.py registrieren

### Tag 5-6: Frontend Components
9. ✅ TypeScript Types erweitern
10. ✅ API Clients erstellen
11. ✅ QuickActionModal bauen
12. ✅ ActivityPicker bauen

### Tag 7-8: Timer & Integration
13. ✅ TimerWidget implementieren
14. ✅ LocationPicker erstellen
15. ✅ ScannerPage Integration
16. ✅ OrderDetailPage Tab hinzufügen

### Tag 9-10: Testing & Polish
17. ✅ End-to-End Tests
18. ✅ Bug-Fixes
19. ✅ UI/UX-Verbesserungen
20. ✅ Dokumentation

---

## Technische Entscheidungen

### Datenbank
- **PostgreSQL** mit JSONB für Metadaten
- **UUID** für time_entry IDs (bessere Skalierung)
- **Indizes** auf order_id, user_id, start_time

### State-Management
- **React Context** für aktive Timer (global)
- **LocalStorage** als Backup bei Crash
- **Real-time Updates** via Polling (später WebSocket)

### Timer-Logik
- **Frontend**: Live-Display mit setInterval
- **Backend**: Authoritative Quelle für Zeiten
- **Auto-Save**: Alle 5 Min im Hintergrund

### Performance
- **Lazy-Loading** für alte Einträge
- **Pagination** für Zeit-Listen
- **Caching** von Aktivitäten (selten ändern sich)

---

## Success-Kriterien

Phase 5 ist abgeschlossen, wenn:

- [ ] Goldschmied kann Timer per QR-Scan starten
- [ ] Quick-Actions funktionieren
- [ ] Aktivitäten sind wählbar und sortiert
- [ ] Timer läuft und zeigt korrekte Zeit
- [ ] Timer kann pausiert/gestoppt werden
- [ ] Unterbrechungen werden erfasst
- [ ] Lagerort kann geändert werden
- [ ] Alle Daten werden korrekt in DB gespeichert
- [ ] Frontend zeigt Zeit-Einträge pro Auftrag
- [ ] Build ist erfolgreich
- [ ] Keine Console-Errors

---

## Nächste Phasen (Ausblick)

**Phase 6: Kalender & Planung**
- Kalender-Komponente
- Drag & Drop Scheduling
- Deadline-Berechnung
- Kapazitäts-Anzeige

**Phase 7: Analytics & Reporting**
- Dashboard-Charts
- Zeit pro Aktivität
- Effizienz-Metriken
- Export-Funktionen

**Phase 8: ML-Vorbereitung**
- Feature-Extraktion
- Daten-Export für Training
- Erste Zeitschätzungs-Prototypen

---

## Los geht's! 🚀

**Start:** Backend Datenmodell & Migration

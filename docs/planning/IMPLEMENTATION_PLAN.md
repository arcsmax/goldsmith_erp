# Implementation Plan: Time-Tracking & Quick-Actions (Phase 5)

## Aktueller Stand (2025-11-09)

✅ **Abgeschlossen (UPDATED):**
- **Phase 1: Production Readiness** (100% Complete)
  - ✅ Critical security fixes (SECRET_KEY, Redis, HttpOnly cookies, RBAC, Rate limiting)
  - ✅ Structured logging with JSON formatting + Request ID tracking
  - ✅ Health checks (6 endpoints: liveness, readiness, startup, detailed, basic, version)
  - ✅ N+1 query fixes with eager loading (95% query reduction)
  - ✅ Transaction management with ACID guarantees
  - ✅ Comprehensive input validation (Pydantic validators)

- **Phase 2.1: CRM Backend** (100% Complete)
  - ✅ Customer model separated from User (proper CRM)
  - ✅ Customer CRUD API (8 endpoints with permissions)
  - ✅ Customer service with business logic
  - ✅ Fine-grained RBAC permission system (15+ permissions)
  - ✅ Database migration with data migration (users → customers)
  - ✅ Frontend TypeScript types and API client

- **Phase 2.2: Cost Calculation** (100% Complete)
  - ✅ Weight-based material cost calculation
  - ✅ Gemstone management (type, carat, quality, cost)
  - ✅ Automatic price calculation: (Material + Gemstones + Labor) × (1 + Margin%) × (1 + VAT%)
  - ✅ CostCalculationService with PriceBreakdown
  - ✅ Scrap percentage support (default 5%)
  - ✅ Manual cost overrides
  - ✅ Price rounding to .00 or .99
  - ✅ Database migration with 11 new Order fields + Gemstone table

- **Phase 3: Frontend-Architektur mit React Router** (80% Complete)
  - ✅ React Router setup
  - ✅ Basic page structure
  - ⚠️ Missing: CustomersPage, Calendar, advanced components

- **Phase 4: Tab-Memory System mit QR/NFC Scanner** (90% Complete)
  - ✅ Tab memory system
  - ✅ QR/NFC scanner integration
  - ⚠️ Missing: Advanced Quick-Actions integration

- **Phase 5.1-5.2: Time-Tracking Backend** (100% Complete)
  - ✅ Database models (activities, time_entries, interruptions, location_history)
  - ✅ Services (ActivityService, TimeTrackingService, LocationService)
  - ✅ API routers (15+ endpoints)
  - ✅ Standard activities seeded (24 activity presets)

## Nächster Schritt: Phase 5.3 - Time-Tracking Frontend UI

**Priorität:** HIGH (Backend fertig, Frontend fehlt)
**Aufwand:** 32-41 Stunden geschätzt
**Ziel:** Komplette UI für Time-Tracking, Quick-Actions, Timer-Widget

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

### Tag 1-2: Backend Foundation ✅ COMPLETE
1. ✅ Datenbank-Schema (Migration)
2. ✅ SQLAlchemy Models
3. ✅ Pydantic Schemas
4. ✅ Seed Standard-Aktivitäten

### Tag 3-4: Backend Services & APIs ✅ COMPLETE
5. ✅ Activity Service & Router
6. ✅ Time-Tracking Service & Router
7. ✅ Location Service & Router
8. ✅ APIs in main.py registrieren

### Tag 5-6: Frontend Components ⚠️ IN PROGRESS (40% Complete)
9. ✅ TypeScript Types erweitern
10. ✅ API Clients erstellen
11. ⏳ QuickActionModal bauen (Backend fertig, Frontend fehlt)
12. ⏳ ActivityPicker bauen (Backend fertig, Frontend fehlt)

### Tag 7-8: Timer & Integration ❌ TODO
13. ⏳ TimerWidget implementieren (Backend fertig, Frontend fehlt)
14. ⏳ LocationPicker erstellen (Backend fertig, Frontend fehlt)
15. ⏳ ScannerPage Integration (Quick-Actions fehlen noch)
16. ⏳ OrderDetailPage Tab hinzufügen (Backend Daten vorhanden, Tab UI fehlt)

### Tag 9-10: Testing & Polish ❌ TODO
17. ❌ End-to-End Tests (0% test coverage)
18. ⏳ Bug-Fixes (Backend stabil, Frontend nicht getestet)
19. ❌ UI/UX-Verbesserungen (UI noch nicht gebaut)
20. ✅ Dokumentation (Backend gut dokumentiert)

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

- [ ] Goldschmied kann Timer per QR-Scan starten (Backend ✅, Frontend ❌)
- [ ] Quick-Actions funktionieren (Backend ✅, Frontend ❌)
- [ ] Aktivitäten sind wählbar und sortiert (Backend ✅, Frontend ❌)
- [ ] Timer läuft und zeigt korrekte Zeit (Backend ✅, Frontend ❌)
- [ ] Timer kann pausiert/gestoppt werden (Backend ✅, Frontend ❌)
- [ ] Unterbrechungen werden erfasst (Backend ✅, Frontend ❌)
- [ ] Lagerort kann geändert werden (Backend ✅, Frontend ❌)
- [x] Alle Daten werden korrekt in DB gespeichert (Backend ✅)
- [ ] Frontend zeigt Zeit-Einträge pro Auftrag (UI fehlt ❌)
- [x] Build ist erfolgreich (Backend ✅)
- [ ] Keine Console-Errors (Frontend nicht getestet ❌)

**Aktuelle Completion Rate:** 5/11 (45%) - Backend komplett, Frontend ausstehend

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

## CRITICAL GAPS IDENTIFIED (2025-11-09 Code Review)

### 🔴 P0 - CRITICAL BLOCKERS (Must-Have vor Production)

1. **Test Coverage: 0%** ❌
   - **Status:** Keine Tests vorhanden
   - **Impact:** DEALBREAKER - Kein Deployment ohne Tests
   - **Aufwand:** 20-30 Stunden
   - **Tasks:**
     - Unit tests für CostCalculationService
     - Integration tests für Customer API
     - E2E tests für Order-Workflow
     - Test coverage target: 80%+

2. **Metal Price API Integration** ❌
   - **Status:** Hardcoded 45 EUR/g für 18K Gold
   - **Impact:** DEALBREAKER - Preise müssen aktuell sein
   - **Aufwand:** 6-8 Stunden
   - **Tasks:**
     - Integration mit Gold-Preis-API (z.B. Metals API)
     - Täglicher Update-Cron-Job
     - Historische Preisverfolgung
     - Admin UI für manuelle Overrides

3. **Invoice Generation (Rechnungsstellung)** ❌
   - **Status:** Nicht implementiert
   - **Impact:** DEALBREAKER - Rechtlich erforderlich in Deutschland
   - **Aufwand:** 16-20 Stunden
   - **Tasks:**
     - PDF-Generierung mit WeasyPrint/ReportLab
     - Compliance mit deutschem Steuerrecht (§14 UStG)
     - Rechnungsnummern-Generator (fortlaufend)
     - Email-Versand mit Anhang
     - Storno/Korrektur-Funktion

4. **Production Deployment Guide** ❌
   - **Status:** Installation.md existiert, aber keine Production-Anleitung
   - **Impact:** CRITICAL - Niemand kann das System deployen
   - **Aufwand:** 6-8 Stunden
   - **Tasks:**
     - Environment-Variable Checklist
     - SSL/TLS Setup (Let's Encrypt)
     - Backup/Restore Prozeduren
     - Security Hardening Guide
     - Monitoring Setup (Logs, Metrics, Alerts)

### 🟡 P1 - HIGH PRIORITY (Should-Have)

5. **Frontend Implementation Gap** ⚠️
   - **Status:** Backend 100%, Frontend 40%
   - **Impact:** HIGH - Benutzer können Features nicht nutzen
   - **Aufwand:** 32-41 Stunden
   - **Tasks:**
     - CustomersPage (List + Create/Edit Form)
     - Time-Tracking UI (Timer-Widget, Quick-Actions Modal)
     - Calendar View für Deadlines
     - OrderDetailPage erweitert (Cost Breakdown, Time Entries Tab)

6. **Expanded Rate Limiting** ⚠️
   - **Status:** Nur /login hat Rate Limiting (5 req/min)
   - **Impact:** HIGH - Abuse-Protection unvollständig
   - **Aufwand:** 2-3 Stunden
   - **Tasks:**
     - Rate Limit auf /register, /customers, /orders POST
     - DDoS-Protection für alle Endpoints
     - IP-Blacklisting für wiederholte Verstöße

7. **Monitoring & Alerting** ⚠️
   - **Status:** Structured Logging vorhanden, aber keine Metrics
   - **Impact:** HIGH - Keine Visibility in Production
   - **Aufwand:** 10-12 Stunden
   - **Tasks:**
     - Prometheus Metrics Integration
     - Grafana Dashboards
     - Alert Rules (CPU, Memory, Error Rate, Response Time)
     - PagerDuty/Email Notifications

### 🟢 P2 - MEDIUM PRIORITY (Nice-to-Have)

8. **Customer History & Preferences** ⏳
   - **Status:** Customer-Tabelle existiert, aber keine Historie
   - **Impact:** MEDIUM - Aus GOLDSMITH_WORKSHOP_REQUIREMENTS.md P1
   - **Aufwand:** 8-10 Stunden
   - **Tasks:**
     - Ring-Größen Tracking
     - Material-Präferenzen (Gold 18K, Silber 925, etc.)
     - Allergie-Tracking (Nickel, etc.)
     - Kaufhistorie-Dashboard

9. **Payment Tracking** ⏳
   - **Status:** Nicht implementiert
   - **Impact:** MEDIUM - Aus GOLDSMITH_WORKSHOP_REQUIREMENTS.md P1
   - **Aufwand:** 12-16 Stunden
   - **Tasks:**
     - Payment-Tabelle (Anzahlung, Restzahlung, Ratenzahlung)
     - Payment-Status Tracking (bezahlt, offen, überfällig)
     - Zahlungserinnerungen per Email
     - Mahnwesen (automatisch nach 14/30/60 Tagen)

10. **API Documentation (Client Examples)** ⏳
    - **Status:** Auto-Generated Swagger existiert (/docs)
    - **Impact:** MEDIUM - Developer Experience
    - **Aufwand:** 3-4 Stunden
    - **Tasks:**
      - API_CLIENT_GUIDE.md mit curl-Beispielen
      - Python Client Code Examples
      - Authentication Flow Diagramm
      - Error Response Documentation

---

## RECOMMENDED NEXT STEPS (Prioritized Roadmap)

### Option A: Security-First (Production Readiness)
**Timeline:** 6-8 Wochen bis Production
**Ziel:** System sicher und deployfähig machen

**Week 1-2:**
- [ ] Test Coverage (Unit + Integration) - 20-30h
- [ ] Expanded Rate Limiting - 2-3h
- [ ] Production Deployment Guide - 6-8h

**Week 3-4:**
- [ ] Metal Price API Integration - 6-8h
- [ ] Invoice Generation (Basic) - 16-20h
- [ ] Monitoring & Alerting - 10-12h

**Week 5-6:**
- [ ] Frontend: CustomersPage - 12-16h
- [ ] Frontend: Time-Tracking UI - 12-16h
- [ ] Security Hardening (SSL, CORS, etc.) - 4-6h

**Week 7-8:**
- [ ] Load Testing & Performance Tuning - 8-10h
- [ ] User Manual & Documentation - 8-10h
- [ ] Beta Testing mit echten Goldschmiede-Kunden

**Pros:** Sichere, produktionsreife Basis
**Cons:** Dauert länger bis Features sichtbar sind

---

### Option B: Feature-First (Rapid Prototyping)
**Timeline:** 4-5 Wochen bis Beta
**Ziel:** Schnell sichtbare Features für Feedback

**Week 1-2:**
- [ ] Frontend: CustomersPage - 12-16h
- [ ] Frontend: Time-Tracking UI - 12-16h
- [ ] Metal Price API Integration - 6-8h

**Week 3:**
- [ ] Invoice Generation (Basic) - 16-20h
- [ ] Test Coverage (Critical Paths) - 10-15h

**Week 4-5:**
- [ ] Production Deployment Guide - 6-8h
- [ ] Monitoring & Alerting - 10-12h
- [ ] Beta Testing

**Pros:** Schnelle Feature-Delivery, frühe User-Feedback
**Cons:** Technische Schulden, weniger stabil

---

### Option C: Parallel Track (RECOMMENDED)
**Timeline:** 5-6 Wochen bis Production Beta
**Ziel:** Balance zwischen Features und Stabilität

**Week 1:**
- [ ] Test Coverage (CostCalculation, CustomerService) - 10-15h
- [ ] Metal Price API Integration - 6-8h
- [ ] Expanded Rate Limiting - 2-3h

**Week 2:**
- [ ] Frontend: CustomersPage - 12-16h
- [ ] Production Deployment Guide - 6-8h

**Week 3:**
- [ ] Invoice Generation (Basic) - 16-20h
- [ ] Integration Tests (Customer, Order APIs) - 8-10h

**Week 4:**
- [ ] Frontend: Time-Tracking UI - 12-16h
- [ ] Monitoring & Alerting - 10-12h

**Week 5:**
- [ ] Security Hardening (SSL, CORS) - 4-6h
- [ ] User Manual & Screenshots - 6-8h
- [ ] E2E Tests (Critical Workflows) - 6-8h

**Week 6:**
- [ ] Load Testing & Performance - 8-10h
- [ ] Bug Fixes & Polish - 8-10h
- [ ] Beta Deployment mit 1-2 Test-Kunden

**Pros:** Best of both worlds, risikominimiert
**Cons:** Erfordert gutes Zeit-Management

---

## NEXT IMMEDIATE ACTIONS (This Week)

1. **Code Review abschließen** ✅ DONE (CODE_REVIEW_2025-11-09.md erstellt)
2. **Implementation Plan aktualisieren** ✅ DONE (Dieses Dokument)
3. **Entscheidung:** Welche Option (A, B, oder C)?
4. **Sprint Planning:** Tasks für die nächsten 2 Wochen festlegen
5. **Git Workflow:** Pull Request erstellen für Feature-Branch → Main

---

## Los geht's! 🚀

**Aktueller Status:**
- Backend: 80-85% Complete ✅
- Frontend: 40% Complete ⚠️
- Tests: 0% Coverage ❌
- Documentation: 65% Complete ⚠️
- Production Readiness: 60% ⚠️

**Nächster Schritt:** Entscheidung zwischen Option A, B, oder C treffen!

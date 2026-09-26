# Verzeichnis von Verarbeitungstaetigkeiten (Art. 30 DSGVO)

**Verantwortlicher (Art. 4 Nr. 7 DSGVO):** `[AUSFUELLEN — Name der Goldschmiede]`, Inhaberin Anne `[AUSFUELLEN — Nachname]` (Entscheidung D-19: die Werkstatt, die mit den Kundinnen und Kunden Vertraege schliesst, ist Verantwortliche)
**Anschrift:** `[AUSFUELLEN — eingetragene Geschaeftsadresse]`
**Kontakt Datenschutzanliegen:** `[AUSFUELLEN — datenschutz@…]`
**Auftragsverarbeiter fuer Betrieb und Wartung des Systems:** Max Kull (Art. 28 DSGVO; AVV erforderlich, siehe `docs/legal/AVV-CHECKLIST.md`)
**Datenschutzbeauftragter:** keiner benannt (§38 Abs. 1 BDSG: Pflicht erst ab 20 Personen, die staendig mit der automatisierten Verarbeitung personenbezogener Daten beschaeftigt sind). Max Kull wird **nicht** als DSB gefuehrt: als Auftragsverarbeiter und Entwickler wuerde er sich selbst kontrollieren (Art. 38 Abs. 6 DSGVO). Bei Bedarf externe Beratung. **Vom Datenschutzberater zu bestaetigen.**
**Stand:** 2026-09-25 · **Version:** 1.2 · **Naechste Pflicht-Review:** 2027-04-17 (jaehrlich) oder bei jedem Milestone-Release

**Rechtsgrundlage des Verzeichnisses:** Art. 30 Abs. 1 DSGVO. Pflicht fuer jeden Verantwortlichen, auch unterhalb der 250-MA-Schwelle, wenn die Verarbeitung nicht nur gelegentlich erfolgt oder Risiken fuer Rechte/Freiheiten Betroffener bestehen. Scan-Logs + Mitarbeiter-Zeiterfassung + Kundendatenverarbeitung erfuellen diese Kriterien. **Aufbewahrung: 6 Jahre ab Beendigung der Taetigkeit** (Analogie HGB §257 Abs. 4).

**Verweise:**
- Audit-Grundlage: `V1.1-POST-WAVE5-COMPLIANCE-AUDIT.md` (Anna Becker, 2026-04-17) — Gesamtverdikt GRUEN (bedingt), Score 7/10 ohne Prozess-Dokumente.
- Technische und organisatorische Massnahmen: `docs/technical/security/TOMS.md` (die frueher zitierte `DPIA-LIGHT-TEMPLATE.md` existiert nicht; Verweise darauf in den Eintraegen unten sind durch TOMS.md ersetzt).
- Loeschkonzept je Tabelle: `docs/technical/RETENTION_SCHEDULE.md`.
- Datenpannen: `docs/technical/security/BREACH-RUNBOOK.md`. Kundeninformation Art. 13: `docs/legal/DATENSCHUTZHINWEISE-KUNDEN.md`.
- Daten-Inventar: Anhang A (siehe unten) verweist auf `PII-SCRUB-AUDIT.md` (97 Spalten) als Single-Source-of-Truth fuer Feld-Klassifikation.

---

## V1.1-001 — Zeit-Erfassung mit Scan-Origin

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-001 |
| **Zweck der Verarbeitung** | Arbeitszeit-Dokumentation pro Auftrag (Nachkalkulation); operative Ablaufsteuerung; Lohnabrechnungs-Grundlage. Erfassung des `input_source`-Kanals (camera/usb_hid/manual) ist notwendig fuer Diagnose von Workflow-Friktion, NICHT fuer Leistungskontrolle einzelner MA. |
| **Rechtsgrundlage** | Art. 6(1)(b) DSGVO (Arbeitsvertrag); BDSG §26(1) Satz 1 (Durchfuehrung Beschaeftigungsverhaeltnis); Art. 6(1)(c) DSGVO iVm HGB §257 (kaufmaennische Aufbewahrung). |
| **Betroffene Personen** | Mitarbeiter (Rollen: ADMIN, GOLDSMITH, APPRENTICE, VIEWER). Initial 5 Personen. |
| **Datenkategorien** | `time_entries.user_id`, `start_time`, `end_time`, `duration`, `activity_id`, `order_id`, `location`, `notes`, `extra_metadata` (JSONB, `scan_origin`-Schluessel). Klassifikation siehe `PII-SCRUB-AUDIT.md` Zeilen 41–42. |
| **Empfaenger** | Intern: ADMIN (Lohnabrechnung, Nachkalkulation), MA selbst (eigene Zeiten). Extern: Steuerberater (lesender Export bei Jahresabschluss), Finanzamt (nur bei Pruefung iSv AO §200). |
| **Drittland-Transfer** | Nein. Verarbeitung ausschliesslich in EU (selbst-gehostet, Podman, keine Cloud-Dienste). |
| **Loeschfristen** | `retention_class = financial_10y` (HGB §257 Abs. 4). Anonymisierung MA-FK bei Austritt via `anonymize_user()` → Sentinel `deleted_user_<HMAC>`, Zeiteintraege bleiben finanziell erhalten. |
| **TOMs** | Siehe TOMS.md: RBAC (`@require_permission`), JWT-abgeleiteter `user_id` (nie aus Payload), Pydantic-Strict-Schema `extra="forbid"`, Idempotency-Key UUIDv4, SQL-Injection-Schutz via ORM. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A (in-house Podman-Deployment); ggf. Hosting-Provider bei kuenftigem Cloud-Move — AVV nach Art. 28 DSGVO erforderlich. |

---

## V1.1-002 — Scan-Logging (scan_logs Audit-Trail)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-002 |
| **Zweck der Verarbeitung** | Audit-Trail fuer jeden QR-/Barcode-Scan zur (a) Fehlerdiagnose (fehlgeschlagene Scans zeigen Labelschaeden/Schulungsbedarf), (b) Workflow-Effizienz-Metriken auf Aggregat-Ebene (§14 Spec), (c) Nachvollziehbarkeit von Materialentnahmen (HGB/Feingehaltsgesetz-Konformitaet). **Ausdruecklich KEINE Leistungskontrolle einzelner Mitarbeiter** (vgl. MITARBEITER-INFORMATION-BDSG26.md und DPIA-LIGHT-TEMPLATE.md §2). |
| **Rechtsgrundlage** | Art. 6(1)(f) DSGVO (berechtigtes Interesse an Workflow-Optimierung und Materialdokumentation) iVm BDSG §26(1); Interessensabwaegung dokumentiert in DPIA-LIGHT-TEMPLATE.md §2 und §4 R1. |
| **Betroffene Personen** | Mitarbeiter mit ERP-Account (alle Rollen). |
| **Datenkategorien** | `scan_logs.user_id` (FK, nicht Klarname), `scanned_at`, `client_tap_at` (client-Zeitstempel, Verhaltens-Proxy), `raw_payload` (PREFIX:ID-Format, PII-frei by design — Spec §2.d), `resolved_type`, `resolved_id`, `resolution_path`, `action_taken`, `context` JSONB (Whitelist: `running_timer_id`, `current_order_id`, `current_location`, `device_type`, `input_source`, `client_version`), `offline_queued`, `synced_at`, `idempotency_key`. Referenz: Spec §2.a. |
| **Empfaenger** | Intern: ADMIN (aggregierte Dashboards ab ≥ 3 MA-Aggregat, keine Individual-KPI); MA selbst (eigene Scans via Art. 15). Extern: keine. |
| **Drittland-Transfer** | Nein. Scanner-Bibliothek `@yudiel/react-qr-scanner` wird lokal gebundelt; 0-Extern-Requests durch CSP `connect-src 'self'` verifiziert (Playwright-Test A14.4, Slice 13). |
| **Loeschfristen** | `retention_class = standard_24m`. Partitionierte Monats-Tabellen; Partitionen > 24 Monate werden automatisch archiviert oder geloescht. Bei Art. 17 Loeschung: `user_id` → Sentinel-FK, alle weiteren Felder bleiben (keine PII). |
| **TOMs** | Spec §2.b Payload-Validation (max 500 Zeichen, Control-Chars-Strip, Depth 3, 4-KiB-Ceiling), `StrictRequestBase` blockt `user_id/created_by/...`-Injection, Idempotency-Key UUIDv4, `X-Client-Created-At` ±30d-Fenster. Siehe TOMS.md. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## V1.1-003 — Barcode-Alias-Verknuepfung

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-003 |
| **Zweck der Verarbeitung** | Zuordnung externer Lieferanten-Barcodes (z. B. Fischer, Rio Grande, Cookson) zu internen Material-/Charge-Entitaeten fuer schnelle Wareneingaenge und Entnahmen. |
| **Rechtsgrundlage** | Art. 6(1)(b) DSGVO (Erfuellung Lieferanten-Vertrag — Materialdokumentation); Art. 6(1)(f) DSGVO (berechtigtes Interesse an effizienter Lagerhaltung). |
| **Betroffene Personen** | **Keine direkten personenbezogenen Daten von Kunden.** Mittelbar: `created_by`-FK auf `users`-Tabelle (= Mitarbeiter, der den Alias angelegt hat) → geringfuegige MA-Aktivitaetsspur. Lieferantendaten sind **juristische Personen** und fallen nicht unter DSGVO (Art. 4 Nr. 1). Einzelkaufleute als Lieferant waeren Ausnahme — Einzelfallpruefung bei Anlage. |
| **Datenkategorien** | `barcode_aliases.barcode_value`, `target_type`, `target_id`, `label`, `created_by` (user FK, ON DELETE RESTRICT), `created_at`. Referenz: Spec §1.c, `db/models.py:2276` (FK RESTRICT). |
| **Empfaenger** | Intern: GOLDSMITH, ADMIN (Anlage); alle Rollen (Lesen via `/scan/resolve`). Extern: keine. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | `retention_class` nicht gesetzt — Alias lebt solange der Lieferanten-Barcode aktiv ist. Soft-Delete via `active=false`; Hard-Delete nach ADMIN-Entscheidung. Bei MA-Austritt: `created_by` → Sentinel. |
| **TOMs** | Siehe TOMS.md. Alias-Rollen-Guards im AliasService (Spec §7.b). |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. Lieferanten-Stammdaten (Kontakt, Anschrift) werden separat unter V1.1-999 (Lieferanten — pre-V1.1) gefuehrt und sind nicht Teil dieser Aktivitaet. |

---

## V1.1-004 — Kundendatenloeschung (Art. 17 Erasure-Flow, H10-erweitert)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-004 |
| **Zweck der Verarbeitung** | Rechtskonforme Durchfuehrung des Kundenrechts auf Loeschung (Art. 17 DSGVO). Umfasst: (a) `scrub_customer_pii` auf 32 Freitext-Felder (siehe PII-SCRUB-AUDIT.md Zeilen 77–110), (b) `FileErasureService` fuer 5 Datei-Targets (valuation_certificates.pdf_path, order_photos.file_path, repair_photos.file_path, scrap_gold_items.photo_path, scrap_gold.receipt_pdf_path), (c) Transitive Kunden-Row-Anonymisierung nach 30-Tage-Grace-Period. |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm Art. 17 DSGVO (rechtliche Verpflichtung zur Loeschung). Parallel: Art. 30 Abs. 1(f) DSGVO (Dokumentation der Loeschfristen). |
| **Betroffene Personen** | Kunden, die einen Loeschantrag stellen. |
| **Datenkategorien** | Alle kundenbezogenen Freitextfelder (siehe PII-SCRUB-AUDIT.md Anhang A) + Datei-Artefakte (PDFs, Fotos, Signatur-Blobs). Audit-Eintrag in `gdpr_requests` (Zweck, Status, Zeitstempel). |
| **Empfaenger** | Intern: ADMIN (fuehrt Loeschung durch). Der Antragsteller selbst erhaelt Bestaetigung nach Art. 12 Abs. 3 DSGVO. Extern: ggf. Aufsichtsbehoerde bei Beschwerde nach Art. 77. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | **30 Tage Grace-Period** (Soft-Delete: `is_active=false`, `deletion_scheduled_at`). Danach Hard-Delete + File-Erasure. `customer_audit_logs` und `gdpr_requests`-Eintraege **bleiben erhalten** (Art.-17-(3)(e)-Ausnahme fuer Rechtsverteidigung + Art. 30-Pflicht). |
| **TOMs** | Path-Traversal-Guard (`resolve().is_relative_to(storage_root)`), HTTP 207 bei Partial-Erasure, `gdpr_requests.status` ∈ {`requested`,`completed`,`PARTIAL_FILE_ERASURE`,`failed`}. **H10 offen**: Row vor scrub schreiben (Deadline 2026-05-29 — siehe AUDIT §6). |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## V1.1-005 — Anonymisierung Mitarbeiter (anonymize_user)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-005 |
| **Zweck der Verarbeitung** | Art. 17-konforme Entfernung von MA-PII bei Austritt oder Loeschbegehren, unter Erhaltung referenzieller Integritaet fuer HGB/Feingehaltsgesetz-pflichtige Geschaeftsdatensaetze (Zeiteintraege, Hallmark-Verifikationen, Scrap-Gold-Protokolle). |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm Art. 17; Ausnahme Art. 17(3)(b) (Rechtsvorschrift HGB §257) und (e) (Rechtsverteidigung). |
| **Betroffene Personen** | Mitarbeiter (aktiv oder ausgeschieden). |
| **Datenkategorien** | `users.email`, `users.first_name`, `users.last_name`, `users.hashed_password` → Sentinel-Ueberschreibung. `anonymization_hash` = HMAC(ANONYMIZATION_SALT, user_id) zur Re-Identifikation ohne Plaintext-FK. 26 FK-Targets werden auf Sentinel-User umgeschrieben (ANONYMIZABLE_FK_TARGETS in `user_service.py:67-102`). |
| **Empfaenger** | Intern: ADMIN. Extern: keine — das Ergebnis ist, dass keine MA-PII mehr vorliegt. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | Sofort auf Antrag; Idempotent (mehrfache Aufrufe nicht-destruktiv). `is_deleted=true`, `deleted_at=now()` bleibt auf `users`-Row. |
| **TOMs** | Last-Admin-Guard (`user_service.py:362-548`), Transaktions-Rollback bei FK-Fehler, HMAC-Tracking in `gdpr_requests`, **ANONYMIZATION_SALT-Rotationsverbot** (H11 — `.env.example`-Kommentar Deadline 2026-06-01). Salt-Rotation nach erster Erasure fuehrt zu Orphaned-HMACs → dauerhaftes Rotationsverbot nach Inbetriebnahme. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## V1.1-006 — Dateiloeschung (FileErasureService fuer Art. 17)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-006 |
| **Zweck der Verarbeitung** | Loeschen kundenbezogener Dateien im Dateisystem (PDFs, Fotos, Belege) ausserhalb der DB-Zeilen, die bei `scrub_customer_pii` allein zurueckbleiben wuerden. Erfuellt Art. 17(1) „ohne unangemessene Verzoegerung" auch fuer Nicht-DB-Artefakte. |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm Art. 17. |
| **Betroffene Personen** | Kunden, deren Loeschbegehren in V1.1-004 eingereicht wurde. |
| **Datenkategorien** | 4 Datei-Pfade + physische Dateiinhalte: `valuation_certificates.pdf_path` (Schaetzgutachten mit Kunden-Name/Signatur), `order_photos.file_path`, `repair_photos.file_path`, `scrap_gold_items.photo_path`. **Nicht** geloescht (GDPR-01, 2026-09): `scrap_gold.receipt_pdf_path` (Altgold-Ankaufbeleg, §8 Abs. 4 GwG / §147 AO, Art. 17 Abs. 3 lit. b DSGVO). Siehe PII-SCRUB-AUDIT.md O1/O2. |
| **Empfaenger** | Intern: ADMIN (ausloesen); Dateisystem lokal. Extern: keine. |
| **Drittland-Transfer** | Nein. Files liegen auf lokalem Podman-Volume; kein S3/Drittland-Storage in V1.1. |
| **Loeschfristen** | Synchron mit V1.1-004 (30 Tage Grace + Execution). `gdpr_requests.status = PARTIAL_FILE_ERASURE` wenn einzelne Dateien nicht loeschbar (Netzwerk-Share offline, Read-Only) — ADMIN-Nacharbeit erforderlich. |
| **TOMs** | Pfad-Traversal-Guard Zeile 281–321 `file_erasure_service.py`, Symlink-Loop-Schutz, per-Target-Transaktion, Audit-Row in `gdpr_requests`. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## V1.1-007 — Punzierungs-Dokumentation (Hallmark Verification)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-007 |
| **Zweck der Verarbeitung** | Dokumentation der verpflichtenden Feingehalts-Punze nach Feingehaltsgesetz/DIN 8238 + Qualitaetskontrolle nach Spec §4.h. Verknuepft Auftrag (`orders.punzierung_verified_at`, `orders.punzierung_verified_by`) mit dem pruefenden Mitarbeiter. |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO (rechtliche Verpflichtung Feingehaltsgesetz §2, §6); Art. 6(1)(f) (Qualitaetsnachweis gegenueber Kunde). |
| **Betroffene Personen** | Mitarbeiter, die die Punze verifizieren (`punzierung_verified_by`). Mittelbar: Kunden, deren Schmuckstueck verifiziert wurde — keine direkten Kunden-PII in dieser Tabelle. |
| **Datenkategorien** | `orders.punzierung_verified_at`, `orders.punzierung_verified_by` (user FK, `db/models.py:457`, ON DELETE RESTRICT), `order_hallmarks.assay_office`, `certificate_number`, `notes`. |
| **Empfaenger** | Intern: GOLDSMITH (Eintrag), ADMIN (Audit). Extern: Pruefstelle (Pforzheim, Hanau) — Pruefpapiere mit Zertifikatsnummer. Aufsichtsbehoerde/Eichamt bei Pruefung. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | `retention_class = hallmark_10y` (10 Jahre, Feingehaltsgesetz/DIN 8238). Bei MA-Austritt: `punzierung_verified_by` → Sentinel; `verified_at` + Zertifikat bleiben. |
| **TOMs** | FK-RESTRICT auf `punzierung_verified_by`; QC-Advance-Guard in `order_service.advance_status()` (Spec §4.h). Audit-Log via `customer_audit_logs`. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: Externe Pruefstellen (z. B. Pforzheim) — eigenstaendig Verantwortliche, kein AVV erforderlich. |

---

## V1.1-008 — Legierungs-Override-Protokoll (Alloy Override Audit)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-008 |
| **Zweck der Verarbeitung** | Audit-Spur, wenn ein Mitarbeiter bewusst Material mit abweichender Legierung entnimmt (Spec §4.c Soll-/Ist-Legierungs-Guard). Schliesst die vom Meister Thomas benannte Luecke: bisher fiel eine falsche Legierungswahl am Verbrauchszeitpunkt nicht auf. |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO (HGB-konforme Materialdokumentation, Feingehaltsgesetz-Nachweiskette); Art. 6(1)(f) (Qualitaetssicherung + Regress-Abwehr bei Kundenbeschwerde). |
| **Betroffene Personen** | Mitarbeiter, die den Override setzen (`material_usage.user_id`). |
| **Datenkategorien** | `material_usage.override_reason` (TEXT NULL, **Freitext — PII-Risiko**, siehe DPIA-LIGHT-TEMPLATE.md §4 R2), `material_usage.override_reason_category` (VARCHAR(32), kontrolliertes Vokabular), `user_id` (RESTRICT), `alloy_override: true` im `extra_metadata`. Referenz: `db/models.py:943-946, 962`. |
| **Empfaenger** | Intern: ADMIN (Audit), GOLDSMITH (eigene Eintraege). Extern: ggf. Kunde bei Regress-Streitigkeit (nur `category`, nicht Freitext), Sachverstaendige. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | `retention_class = financial_10y` (HGB-Materialbeleg). MA-FK → Sentinel bei Austritt. |
| **TOMs** | **B3-UI-Guard offen** (deferred Slice 11, V1.1.5): Pydantic-Regex-Deny fuer deutsche Namensmuster (`\b(Frau|Herr|Familie|Fam\.?)\s+[A-ZAEOEUE]...`) auf `override_reason`. Bis dahin: quartalsweiser PII-Scan-Job + UI-Hinweis „Keine Kundennamen eintragen". |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## V1.1-009 — Altgold-Ankauf mit Kundensignatur (Scrap Gold Intake)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-009 |
| **Zweck der Verarbeitung** | Ankauf von Altgold von Privatkunden, gesetzlich vorgeschriebene Identifikations- und Dokumentationspflicht nach GwG (Geldwaeschegesetz) §§ 10, 12. Erfasst Kundensignatur als Nachweis der Uebergabe und Kaufpreis-Akzeptanz. |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm GwG §10 (Identifikationspflicht bei Bartransaktionen ≥ 10 000 € bzw. ≥ 2 000 € fuer Gueterhaendler mit hohem Bargeldanteil); Art. 6(1)(b) DSGVO (Kaufvertragsabwicklung). **eIDAS-Klassifikation der Signatur: einfache elektronische Signatur (Art. 3 Nr. 10 VO 910/2014)** — Details siehe `EIDAS-ALTGOLD-SIGNATUREN.md`. |
| **Betroffene Personen** | Privatkunden, die Altgold verkaufen. |
| **Datenkategorien** | `scrap_gold.customer_id` (nullable — Walk-in-Kunde moeglich), `signature_data` (base64 PNG), `notes`, `receipt_pdf_path`, `scrap_gold_items.description`, `photo_path` (File-Erasure-Target), `price_source`. Seit GDPR-01 (2026-09) werden Signatur, Notizen, Positionen und Beleg bei Art. 17 **nicht** mehr geschwaerzt (`RETAINED_RECORD_FIELDS`). |
| **Empfaenger** | Intern: GOLDSMITH (Ankauf), ADMIN (Financial Oversight). Extern: Finanzamt (Betriebspruefung), GwG-Aufsichtsbehoerde bei Verdachtsmeldung. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | `retention_class = financial_10y` (HGB §257 + GwG §8 Abs. 4). Bei Art. 17-Antrag des Kunden: Datensatz inkl. Signatur und Beleg bleibt unveraendert (Art. 17 Abs. 3 lit. b); `customers.retention_hold_until` (Jahresende des juengsten Belegs + 10 Jahre) markiert, ab wann geloescht werden darf; die Kundenzeile wird nach 30 Tagen anonymisiert. Nur Artikelfotos werden sofort geloescht. |
| **TOMs** | Signatur und Beleg aufbewahrt (GDPR-01), Foto per FileErasureService, Path-Traversal-Guard. **eIDAS-Empfehlung V1.2**: qualifizierte Signatur fuer Transaktionen > 5 000 € (siehe `EIDAS-ALTGOLD-SIGNATUREN.md`). |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## V1.1-010 — VIEWER-Rollen-Zugriff auf /orders/{id} (tolerierte Schwachstelle)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-010 |
| **Zweck der Verarbeitung** | Lesezugriff fuer Rolle VIEWER auf Auftragsdetails. Siehe Audit §5 Punkt 6 und V1.1-Amendments A14.7. |
| **Rechtsgrundlage** | Art. 6(1)(b) DSGVO iVm BDSG §26(1). |
| **Betroffene Personen** | Mitarbeiter; mittelbar Kunden-PII im Auftragskontext. |
| **Datenkategorien** | `orders.*` inkl. derzeit ungefilterter Finanzfelder (Preise, Materialkosten). |
| **Empfaenger** | Intern: VIEWER-Rolle (aktuell **inklusive** Finanzfeldern — Leak). |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | — |
| **TOMs — Status** | **Update 2026-09 (W1-04):** Finanz- und Designfelder werden fuer VIEWER serverseitig entfernt (`api/role_projection.py`, 22 Endpunkte); Eintrag bleibt zur Historie. Urspruenglich: **Tolerierte Schwachstelle mit Abhilfefrist 2026-07-31.** Maria hat das Finding in V1.1.5 gescoped (DECISIONS-2026-04-16 V7). Als Interim-Massnahme wird **VIEWER-Zugriff auf `/orders/{id}` audit-geloggt** (Anna-Forderung A14.7; Deadline 2026-06-01 vor V1-Ship). Monatliche DPO-Review der VIEWER-Access-Logs bis Fix live. Legal begruendet: dokumentierte Kenntnis + Mitigation durch Audit-Logging + verbindlicher Fix-Plan entspricht Art. 32(1) „Risikoangemessenheit" bei < 20 MA mit persoenlicher Kenntnis. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |
| **Re-Assessment** | Bei Ueberschreiten der Abhilfefrist 2026-07-31 ohne Fix: eskaliert zum Datenschutzvorfall-Kandidaten nach Art. 33 DSGVO-Pruefung, externe DPO-Beratung einholen (Trigger 6 per DPIA-LIGHT §11). |

---

## V1.2-001 — Kundeninfo & §649-BGB-Kostenfreigabe (Customer Updates)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.2-001 |
| **Zweck der Verarbeitung** | Auftragsbegleitende Information des Kunden (Fortschritt, Abholung, Kostenaenderung) und rechtssichere Einholung der Kundenzustimmung bei Ueberschreitung des Kostenvoranschlags nach §649 BGB. Die Zustimmung/Ablehnung wird als Beweis (Evidence-Logging) erfasst, NICHT als Klick-/Verhaltenstracking — es gibt kein Live-Portal; die Kommunikation laeuft per E-Mail/PDF, `token` ist nur ein portal-faehiger Referenz-Handle fuer die Zukunft. |
| **Rechtsgrundlage** | Art. 6(1)(b) DSGVO (Vertragserfuellung — Kundeninformation + §649 BGB Zustimmung zur Mehrverguetung); Art. 6(1)(c) iVm HGB §257 (kaufmaennische Aufbewahrung der Kostenfreigabe als Finanzbeleg). |
| **Betroffene Personen** | Kunden (Empfaenger der Kundeninfo bzw. Zustimmende einer Kostenaenderung). Mittelbar: Mitarbeiter (`sent_by`/`created_by`/`recorded_by`-FK). |
| **Datenkategorien** | `customer_updates`: `subject`, `body` (Freitext, design-IP-nah — SCRUB-Target ueber `order_id`/`repair_job_id`-Link), `photo_ids` (nur explizit ausgewaehlte OrderPhoto-UUIDs — nie Auto-Sharing), `kind`, `status`, `delivery_method`, `sent_at`, `token`. `cost_change_requests` (§649, Finanzdaten): `original_amount`, `new_amount`, `delta_percent`, `reason` (Freitext, rechtlich relevante Begruendung — SCRUB-Target), `line_items` (JSON), `response_method`, `response_evidence` (SCRUB-Target), `responded_at`, `status`. Referenz: `db/models.py:2653` (CustomerUpdate), `:2760` (CostChangeRequest). |
| **Empfaenger** | Intern: GOLDSMITH/ADMIN (Erstellen/Senden, Erfassen der Antwort); die Finanzfelder der Kostenaenderung nur ADMIN/GOLDSMITH, Zugriff audit-geloggt. Extern: der Kunde selbst (E-Mail/PDF). Keine Drittempfaenger. |
| **Drittland-Transfer** | Abhaengig vom E-Mail-Anbieter (Korrektur 2026-09, GDPR-15: der SMTP-Host ist zur Laufzeit durch ADMIN einstellbar und in der Praxis ein gehostetes Postfach, z. B. IONOS/Strato; kein lokaler Mailserver). EU-Anbieter waehlen. |
| **Loeschfristen** | `cost_change_requests`: `retention_class = financial_10y` (HGB §257 — die §649-Zustimmung ist Finanzbeleg; `order_id` ON DELETE RESTRICT). `customer_updates`: Skelett-Zeile bleibt fuer Art.-30-Nachweis erhalten (`order_id`/`repair_job_id` ON DELETE SET NULL); bei Art. 17 werden die Freitextinhalte (`body`, `reason`, `response_evidence`) via `scrub_customer_pii` auf `[REDACTED]` gesetzt, die Zeilen nicht geloescht. |
| **TOMs** | RBAC (`@require_permission`), Finanzfeld-Sichtbarkeit ADMIN/GOLDSMITH + Audit-Log der Lesezugriffe, Evidence-Logging statt Tracking, DB-partieller Unique-Index „ein-lebendes-§649-Notice pro Auftrag", Pydantic-XOR-Invariante (genau ein FK-Ziel gesetzt), `token` = uuid4. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV); **E-Mail-Anbieter der Goldschmiede (AVV nach Art. 28 DSGVO erforderlich, GDPR-15)**. |

---

## V1.3-001 — Statistischer Aufwandsschaetzer (Labor Estimator)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.3-001 |
| **Zweck der Verarbeitung** | Statistische Schaetzung des Arbeitsaufwands (Stunden) und der Arbeitskosten fuer neue Auftraege/Kostenvoranschlaege aus dem historischen Auftrags-/Zeitbestand (Median + interne P20/P80-Spanne, gruppiert nach Taetigkeit/Tier). **Neuer Zweck auf bereits vorhandenen Daten — es werden KEINE neuen Personendaten-Kategorien erhoben.** Der Korpus wird read-only live aus bestehenden Tabellen berechnet (keine neue Tabelle, keine neue Erhebung). |
| **Rechtsgrundlage** | Art. 6(1)(f) DSGVO (berechtigtes Interesse an belastbarer Kalkulation/Preisgenauigkeit). Die zugrunde liegenden Mitarbeiter-Zeitdaten wurden unter Art. 6(1)(b)/BDSG §26 erhoben (V1.1-001); die Weiterverwendung zur Schaetzung ist ein vereinbarer Folgezweck iSv Art. 6(4) DSGVO (Aggregat, keine Leistungskontrolle Einzelner). |
| **Betroffene Personen** | Mittelbar Mitarbeiter (deren aggregierte Zeiteintraege in den Korpus einfliessen). Keine direkten Kunden-PII — der Schaetzer verarbeitet Dauer/Taetigkeit, nicht Kundendaten. |
| **Datenkategorien** | Read-only-Aggregation aus `orders`, `time_entries`, `activities`, `interruptions` (abgeschlossene Auftraege → billable Netto-Dauer je Taetigkeit). Persistiert wird nur die Kalibrierung: `estimate_accuracy` (`estimated_hours`, `actual_hours`, `estimated_total`, `actual_total`, `estimator_version`, `order_id`) — Finanzdaten. Rohwerte wie `activity.hourly_rate` werden NIE an Aufrufer zurueckgegeben, nur aggregierte Kosten. Referenz: `services/labor_corpus_service.py`, `db/models.py:3114` (EstimateAccuracy). |
| **Empfaenger** | Intern: ADMIN/GOLDSMITH (Schaetzung + Kalibrierung, `GET /estimates/...` audit-geloggt). Kein VIEWER-Zugriff auf Finanzwerte. Extern: keine. |
| **Drittland-Transfer** | Nein. Rein statistische In-Prozess-Berechnung, kein externer ML-Dienst, kein Cloud-Transfer. |
| **Loeschfristen** | Kein neuer Personenbezug: der Korpus ist fluechtig (live berechnet, nicht gespeichert). `estimate_accuracy` ist an einen abgeschlossenen Auftrag gebunden (`order_id` ON DELETE RESTRICT, financial-Aufbewahrung); der mittelbare MA-Bezug verschwindet mit der Anonymisierung der zugrunde liegenden `time_entries` (V1.1-005). |
| **TOMs** | `insufficient_data` → alle Zahlenfelder `None` (keine Fabrikation aus zu wenigen Vergleichsauftraegen), stale/unbekannte `activity_id` wird ausgeschlossen statt falsch bepreist, `hourly_rate` nie in der Antwort, ADMIN/GOLDSMITH-only + Audit-Log der `estimates`-Reads (Financial-Data-Regel CLAUDE.md), Aggregat statt Individual-KPI. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## V1.3-002 — Automatisierte Loeschung (Cleanup-Job + Erasure-Endpoints)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.3-002 |
| **Zweck der Verarbeitung** | Automatisierte, fristgerechte Ausfuehrung von Loeschbegehren (Art. 17) nach Ablauf der 30-Tage-Grace-Period. Ergaenzt die Mechanismen aus V1.1-004/005/006 um (a) den geplanten Kunden-Cleanup-Job (`jobs.gdpr_cleanup` → `CustomerService.hard_delete_expired_customers`, systemd-Timer) und (b) die tatsaechlich verdrahteten Erasure-Endpoints, die es zuvor nicht gab: `DELETE /customers/{id}/gdpr-erase` und **neu** `POST /users/{id}/gdpr-erase` (Mitarbeiter, ruft `anonymize_user`). |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm Art. 17. Ausnahme Art. 17(3)(b): Kunden mit aufbewahrungspflichtigen Unterlagen (Rechnung/Kostenvoranschlag/Wertgutachten, §147 AO / §14b UStG — 10 Jahre; Altgold-Ankauf, §8 Abs. 4 GwG) werden **in-place anonymisiert** statt geloescht; die Unterlagen selbst bleiben unveraendert (GDPR-01), `customers.retention_hold_until` + Audit-Row `gdpr_retention_hold` dokumentieren Frist und Rechtsgrundlage. Ohne solche Unterlagen wird die Zeile hart geloescht. |
| **Betroffene Personen** | Kunden (nach Ablauf der Grace-Period) und Mitarbeiter (Austritt oder Loeschbegehren). |
| **Datenkategorien** | Kundenseitig: alle identifizierenden `customers`-Spalten → `[GELOESCHT]`/NULL bzw. Zeile geloescht, plus Datei-Artefakte (V1.1-006). Mitarbeiterseitig: `users`-PII → Sentinel (V1.1-005). Audit: `customer_audit_logs` (`gdpr_pii_scrub`, `gdpr_file_erasure`) + `gdpr_requests` (`erasure`, `erasure_cleanup`) bleiben erhalten. |
| **Empfaenger** | Intern: ADMIN (loest die Endpoints aus); der Cleanup-Job laeuft unbeaufsichtigt im Backend-Container. Bei Fehlern: WARNING-Benachrichtigung an alle aktiven ADMINs (systemd `OnFailure` → `/admin/notify-gdpr-cleanup`). Extern: ggf. Aufsichtsbehoerde bei Beschwerde. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | 30-Tage-Grace (Soft-Delete `deletion_scheduled_at`), danach taeglicher Cleanup (systemd-Timer). Ein Restore aus einem aelteren Backup (bis ~3 Monate) wuerde geloeschte Kunden zurueckbringen; `restore.sh` wendet deshalb vor dem Start das Loeschprotokoll erneut an (GDPR-07, V1.5-008; `GDPR_ERASURE_RETENTION.md` §4.2). Die fruehere Regel „Cleanup-Job nach Restore erneut ausfuehren" reichte nicht aus. |
| **TOMs** | Pro-Kunde-Transaktion (ein Fehler bricht den Lauf nicht ab), Fail-Loud-Exit-Code + systemd-Alert (keine still verschluckten Fehler), Audit-Row je Schritt, Log nur mit `customer_id`-PK (nie Namen/E-Mail), Last-Admin-Guard bei Mitarbeiter-Anonymisierung, idempotent. Vollstaendige Beschreibung: `docs/technical/GDPR_ERASURE_RETENTION.md`. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## Anhang A: Daten-Inventar

Der vollstaendige Feld-fuer-Feld-Nachweis, welche Spalte personenbezogene Daten enthaelt und wie sie im Art.-17-Pfad behandelt wird, ist die Datei:

**`PII-SCRUB-AUDIT.md`** (2026-04-17, 97 Spalten ueber 34 Tabellen, 32 SCRUB-Targets + 5 File-Erasure-Targets)

Diese Datei gilt als **Single-Source-of-Truth** fuer Klassifikations-Entscheidungen. Bei jeder Schema-Aenderung in `src/goldsmith_erp/db/models.py` ist das Audit-Dokument zu aktualisieren (CI-Lint-Empfehlung, out-of-scope V1.1 — siehe PII-SCRUB-AUDIT.md „Next actions" #4).

**Kategorien-Zusammenfassung:**
- 25 + 7 = **32 SCRUB-Targets** (covered by `CustomerService.scrub_customer_pii`)
- **5 File-Erasure-Targets** (covered by `FileErasureService`)
- **41 System-/Enum-Spalten** (nicht-personenbezogen)
- **15 customers-Row-Spalten** (Art. 17 via direkte Anonymisierung/Loeschung)
- **4 users-Spalten** (Slice-0 `anonymize_user`)
- **9 Audit-/GDPR-Spalten** (Art. 17(3)(e) Beweisausnahme)
- **7 Pfad-/URL-Spalten** (File-System-Referenzen, Art. 17 via FileErasureService)

---

## Anhang B: Nicht-V1.1-Verarbeitungstaetigkeiten (Verweis)

Pre-V1.1-Aktivitaeten werden in separaten Verzeichnis-Entries gepflegt (ausserhalb dieser Datei), u. a.:
- Kundenstammdaten-Verwaltung (V1.0-001)
- Auftragsverwaltung (V1.0-002)
- Materialbestand (V1.0-003)
- Kundenfoto-Dokumentation (V1.0-004)
- Rechnungsstellung (V1.0-005)
- Versicherungsschaetzung — `valuation_certificates` (V1.0-006)

Deadline fuer Nachtrag pre-V1.1-Entries: **2026-05-31** (vor V1-Ship-Day 2026-06-16). Dies ist eine dokumentierte Pflichtschuld, nicht Teil dieses V1.1-Scope.

---

## Aenderungsprotokoll

| Version | Datum | Aenderung | Autor |
|---|---|---|---|
| 1.0 | 2026-04-17 | Initial-Erstellung fuer V1-DPO-Checkpoint. 10 V1.1-Entries + Anhaenge. | Anna Becker (DPO/TUeV) |
| 1.1 | 2026-07-26 | V1.2/V1.3-Nachtrag (predatierte den Stand 2026-04-17): +V1.2-001 (Kundeninfo & §649-BGB-Kostenfreigabe), +V1.3-001 (statistischer Aufwandsschaetzer — neuer Zweck auf vorhandenen Daten, keine neuen Datenkategorien), +V1.3-002 (automatisierte Loeschung: Cleanup-Job + Mitarbeiter-/Kunden-Erasure-Endpoints). Querverweis auf `docs/technical/GDPR_ERASURE_RETENTION.md`. | Max Kull (Verantwortlicher) — DPO-Review Anna Becker ausstehend |
| 1.2 | 2026-09-25 | Verantwortliche korrigiert (Goldschmiede statt Max Kull, D-19); kein DSB mit Selbstkontroll-Konflikt; Max Kull als Auftragsverarbeiter; SMTP-Anbieter als Auftragsverarbeiter (GDPR-15); Restore-Regel durch Loeschprotokoll ersetzt (GDPR-07); +V1.5-001 bis V1.5-009 (Rechnungskopie, Auftragshistorie, Tagesuebersicht, Reparatur-Kundeninfo/automatische Mails, Metallpreis-Abruf, Echtzeit-Ereignisse, personenbezogene Schaetzgenauigkeit (Konflikt, GDPR-14), Datensicherung, Art.-15-Auskunft). | Audit-Fix W5 (Entwurf) — Freigabe durch die Verantwortliche ausstehend |

**Unterschrift Verantwortlicher:**

```
_________________________________________
Anne [Nachname], Inhaberin der Goldschmiede — Verantwortliche nach Art. 4 Nr. 7 DSGVO
Ort, Datum
```

---

## V1.4-001 — Einwilligungen und Gesundheitsdaten (Allergien)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.4-001 (GDPR-02 / GDPR-11, 2026-09) |
| **Zweck der Verarbeitung** | Nachweis von Einwilligungen je Zweck (`customer_consents`: `health_data`, `photo_use`, `email_contact`, `marketing`). Erste Anwendung: Allergien (z. B. Nickel) als Gesundheitsdaten, damit kein allergieausloesendes Material verarbeitet wird. |
| **Rechtsgrundlage** | Allergien: Art. 9 Abs. 2 lit. a DSGVO (ausdrueckliche Einwilligung); Einwilligungsnachweis: Art. 7 Abs. 1. Ohne aktive `health_data`-Einwilligung lehnt das System das Speichern von Allergien ab (HTTP 422). |
| **Betroffene Personen** | Kundinnen und Kunden. |
| **Datenkategorien** | Zweck, Art der Erteilung (`in_person`/`written`/`portal`), Textversion, Erteilt-/Widerrufen-Zeitpunkt, erfassende Person, Notiz (verschluesselt). Allergien: `customers.allergies` (verschluesselt), `customer_no_gos` Kategorie `allergy` (verschluesselt). |
| **Empfaenger** | Intern: nur GOLDSMITH und ADMIN (`CUSTOMER_HEALTH_VIEW`, `CONSENT_MANAGE`). VIEWER sieht weder Allergien noch Allergie-No-Gos. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | Widerruf (Art. 7 Abs. 3) loescht Allergien und Allergie-No-Gos sofort. Art. 17-Antrag: Allergien und alle Einwilligungen werden sofort geloescht; Art. 15-Auskunft enthaelt die Einwilligungshistorie. |
| **TOMs** | Verschluesselung at rest, Rollenprojektion im API (`CustomerRead` serialisiert Allergien nie), Audit-Rows `consent_granted`/`consent_revoked`, Audit-Middleware fuer `/customers/*`. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb/Wartung, AVV). Sonst: N/A. |

---

## Nachtrag 2026-09 (Version 1.2)

Die folgenden Einträge beschreiben Verarbeitungen, die mit dem Audit-Fix-Paket 2026-09 (`docs/review/2026-09-25/`) hinzugekommen oder geändert worden sind. Verantwortlicher ist bei allen Einträgen die Goldschmiede (siehe Kopf); Betrieb und Wartung des Systems durch Max Kull als Auftragsverarbeiter (AVV, `docs/legal/AVV-CHECKLIST.md`). TOMs: `docs/technical/security/TOMS.md`. Löschfristen: `docs/technical/RETENTION_SCHEDULE.md`.

## V1.5-001 — Unveränderliche Rechnungskopie (Invoice Snapshot)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-001 (GDPR-01 / BE-23, W1-10) |
| **Zweck der Verarbeitung** | Rechnungen so aufbewahren, wie sie ausgestellt wurden (GoBD: keine nachträgliche Veränderung von Buchungsbelegen). Bei Anlage wird ein JSON-Schnappschuss von Kunde, Positionen und Beträgen gespeichert; beim Versand (SENT) zusätzlich das PDF mit SHA-256-Prüfsumme, danach schreibgeschützt. Eine spätere Adressänderung oder Anonymisierung des Kunden verändert alte Rechnungen nicht mehr. |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. c DSGVO iVm §147 AO, §14b UStG, §257 HGB. |
| **Betroffene Personen** | Kundinnen und Kunden (Rechnungsempfänger). |
| **Datenkategorien** | `invoices.snapshot` (verschlüsselt: Name, Anschrift, Positionen, Beträge), `invoices.issued_pdf` (verschlüsselt), `issued_at`, Prüfsumme. |
| **Empfänger** | Intern: ADMIN, GOLDSMITH. Extern: Kunde, Steuerberater (eigener Verantwortlicher), Finanzverwaltung bei Prüfung. |
| **Drittland-Transfer** | Nein. |
| **Löschfristen** | 8 Jahre (Buchungsbeleg, BEG IV) — Code hält konservativ 10 Jahre (`RETENTION_YEARS`); **vom Steuerberater zu bestätigen**. Art. 17-Antrag: Legal Hold statt Löschung (Art. 17 Abs. 3 lit. b), `customers.retention_hold_until`. |
| **TOMs** | Verschlüsselung at rest, write-once nach Versand, Rollen ADMIN/GOLDSMITH, Audit-Log für Finanzzugriffe. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb, AVV). |

---

## V1.5-002 — Auftragshistorie (Order Events)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-002 (W2-07) |
| **Zweck der Verarbeitung** | Nachvollziehbarer Statusverlauf je Auftrag (von → nach, Zeitpunkt, Grund bei Pause/Storno), Anzeige als Zeitleiste im Auftrag. |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b DSGVO (Auftragsdurchführung); Art. 6 Abs. 1 lit. f (Nachweis bei Reklamation); für die Mitarbeiter-ID §26 BDSG. |
| **Betroffene Personen** | Kundinnen und Kunden (mittelbar über den Auftrag), Mitarbeitende (`user_id` der Statusänderung). |
| **Datenkategorien** | `order_events`: `order_id`, `from_status`, `to_status`, `user_id`, `reason` (Freitext, max. 500 Zeichen), `meta` (JSON), `created_at`. |
| **Empfänger** | Intern: alle Rollen mit Auftragszugriff. Art. 15-Auskunft enthält Statusverlauf ohne Mitarbeiter-ID und ohne Freitext. |
| **Drittland-Transfer** | Nein. |
| **Löschfristen** | Mit dem Auftrag (siehe RETENTION_SCHEDULE.md §3.2); bei Mitarbeiter-Anonymisierung wird `user_id` auf den Sentinel umgeschrieben. |
| **TOMs** | RBAC, keine Mitarbeiter-Rangliste auf Basis der Events, Art. 15-Export ohne Mitarbeiterkennung. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb, AVV). |

---

## V1.5-003 — Tagesübersicht (Dashboard „Heute“)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-003 (W2-03) |
| **Zweck der Verarbeitung** | Arbeitsplanung: fällige und überfällige Aufträge und Reparaturen, offene Kostenfreigaben, Übergaben an die angemeldete Person. Keine neue Datenerhebung, nur Anzeige vorhandener Daten. |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b DSGVO; §26 BDSG (Arbeitsorganisation). |
| **Betroffene Personen** | Kundinnen und Kunden (Name am Auftrag), Mitarbeitende (Übergaben). |
| **Datenkategorien** | Auftrags-/Reparatur-Titel, Termine, Status, Kundenname; Preise nur für ADMIN/GOLDSMITH (Rollenprojektion). |
| **Empfänger** | Intern, rollenabhängig; VIEWER ohne Finanz- und Designfelder. |
| **Drittland-Transfer** | Nein. |
| **Löschfristen** | Keine eigene Speicherung. |
| **TOMs** | Rollenprojektion (`api/role_projection.py`), keine Leistungskennzahlen einzelner Mitarbeitender. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb, AVV). |

---

## V1.5-004 — Kundeninfo zu Reparaturen und automatische Kundenmails

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-004 (W1-12, W2-02; ergänzt V1.2-001) |
| **Zweck der Verarbeitung** | Information der Kundin/des Kunden zu Reparaturen (Eingang, fertig zur Abholung) und automatische Mails zu Auftragsereignissen. Genau eine Mail je Ereignis (Dedupe-Schlüssel), nur aus kundenseitigen Feldern (nie interner Notiztext, GDPR-13), jede Mail als `customer_updates`-Zeile in „Kundeninfo“ sichtbar. |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b DSGVO (Vertragserfüllung). Werbliche Mails (Zufriedenheitsabfrage, Geburtstag) sind **nicht** umfasst und brauchen Einwilligung oder §7 Abs. 3 UWG (**vom Datenschutzberater zu bestätigen**). |
| **Betroffene Personen** | Kundinnen und Kunden. |
| **Datenkategorien** | E-Mail-Adresse, Betreff, Text, ggf. ausgewählte Fotos (EXIF entfernt, verkleinert), Versandzeitpunkt, Status. |
| **Empfänger** | Kunde; **E-Mail-Anbieter der Goldschmiede als Auftragsverarbeiter** (SMTP-Host, siehe AVV-CHECKLIST.md). |
| **Drittland-Transfer** | Abhängig vom Mail-Anbieter; EU-Anbieter wählen. Bei Anbietern mit US-Bezug Art. 44 ff. prüfen (**vom Datenschutzberater zu bestätigen**). |
| **Löschfristen** | `customer_updates`: 3 Jahre nach Auftragsende (Vorschlag, RETENTION_SCHEDULE.md); Art. 17: Freitext geschwärzt. Kopien im Postfach „Gesendet“ des Anbieters sind Teil der Löschung (Art. 17 Abs. 2). |
| **TOMs** | Dedupe-Unique-Index, Rollen ADMIN/GOLDSMITH für Versand, TLS zum SMTP-Server (STARTTLS 587 / SSL 465; Erzwingung auf allen Ports offen, W5-09). |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | E-Mail-Anbieter (AVV erforderlich); Max Kull (Betrieb, AVV). |

---

## V1.5-005 — Metallpreis-Abruf

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-005 (W2-15) |
| **Zweck der Verarbeitung** | Tagesaktuelle Edelmetallpreise für Kalkulation und Altgold-Bewertung (`METAL_PRICE_API_URL`), mit Veraltet-Kennzeichnung nach 24 h. |
| **Rechtsgrundlage** | Keine personenbezogenen Daten im Abruf (nur Metallart); technisch fällt beim Anbieter die IP-Adresse des Werkstatt-Servers an (Art. 6 Abs. 1 lit. f). |
| **Betroffene Personen** | Keine (Betriebs-IP). |
| **Datenkategorien** | Metallart, Preis, Zeitpunkt (`metal_price_history`). |
| **Empfänger** | Preis-API-Anbieter (erhält keine Kunden- oder Mitarbeiterdaten). |
| **Drittland-Transfer** | Abhängig vom Anbieter; ohne Personenbezug unkritisch. |
| **Löschfristen** | Preishistorie ohne Personenbezug; betrieblich. |
| **TOMs** | Timeout, keine Übertragung von Kundendaten, Anfrage enthält keine Kennung. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Keiner (kein AVV nötig, keine personenbezogenen Daten). |

---

## V1.5-006 — Echtzeit-Ereignisse (WebSocket)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-006 (W2-13) |
| **Zweck der Verarbeitung** | Andere angemeldete Geräte der Werkstatt wissen lassen, dass sich etwas geändert hat (Auftrag, Timer, Benachrichtigung), damit sie neu laden. |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b DSGVO; §26 BDSG. |
| **Betroffene Personen** | Mitarbeitende (Timer-Ereignisse mit Nutzer-ID); mittelbar Kunden (Auftrags-ID). |
| **Datenkategorien** | Nur Kennungen und Status: `action`, `source`, `order_id`, `status`, `location`, Timer-/Benachrichtigungs-IDs, Zeitstempel. **Keine** Preise, Titel, Beschreibungen, Namen (Whitelist in `core/ws_manager.py`). |
| **Empfänger** | Intern: angemeldete Sitzungen (authentifizierter `/ws/events`). |
| **Drittland-Transfer** | Nein. |
| **Löschfristen** | Keine Speicherung (flüchtige Redis-Pub/Sub-Nachricht). |
| **TOMs** | Authentifizierung am WebSocket, Feld-Whitelist, Client lädt Details über die rollenprojizierte REST-API. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb, AVV). |

---

## V1.5-007 — Schätzgenauigkeit je Goldschmied (personenbezogene Auswertung)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-007 (GDPR-14) |
| **Zweck der Verarbeitung** | `GET /analytics/goldsmith-accuracy/{user_id}`: persönliche Soll/Ist-Genauigkeit, beste/schlechteste Auftragstypen und Trend einer Person im Vergleich zum Werkstattdurchschnitt. GOLDSMITH sieht nur die eigenen Werte, **ADMIN die Werte jeder Person**. |
| **Rechtsgrundlage** | §26 BDSG / Art. 88 DSGVO — **offen**. |
| **Betroffene Personen** | Goldschmiedinnen und Goldschmiede. |
| **Datenkategorien** | Aggregierte Soll/Ist-Abweichungen je Person aus `time_entries`, `estimate_accuracy`. |
| **Empfänger** | Intern: die Person selbst; ADMIN. |
| **Drittland-Transfer** | Nein. |
| **Löschfristen** | Keine eigene Speicherung (live berechnet). |
| **TOMs** | Audit-Log jedes Abrufs; Selbstzugriff für GOLDSMITH. |
| **Status / Konflikt** | **Widerspricht der Mitarbeiterinformation** (`MITARBEITER-INFORMATION-BDSG26.md`: „keine Leistungskontrolle einzelner Mitarbeiter, Aggregate ab drei Personen“) und V1.1-001/V1.3-001. Entscheidung durch die Verantwortliche nötig: (a) ADMIN-Zugriff auf fremde Werte entfernen bzw. nur Aggregate ab drei Personen (Code-Änderung W5-09, `api/routers/analytics.py`), **oder** (b) Zweck und Rechtsgrundlage festlegen und die Mitarbeiterinformation vor der Nutzung ändern. Bis dahin: nicht für Personalentscheidungen nutzen. Bei Bestehen eines Betriebsrats §87 Abs. 1 Nr. 6 BetrVG. **Vom Datenschutzberater zu bestätigen.** |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb, AVV). |

---

## V1.5-008 — Datensicherung und Löschprotokoll

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-008 (GDPR-06, GDPR-07) |
| **Zweck der Verarbeitung** | Wiederherstellbarkeit (Art. 32 Abs. 1 lit. c) durch tägliche, verschlüsselte Datenbank-Sicherungen; Schutz vor dem Wiedereinspielen gelöschter Personen durch ein Löschprotokoll (Erasure-Ledger), das nach jedem Restore vor dem Start erneut angewendet wird. |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. c, f iVm Art. 32 DSGVO; Löschprotokoll: Art. 5 Abs. 2, Art. 17. |
| **Betroffene Personen** | Alle in der Datenbank erfassten Personen. |
| **Datenkategorien** | Vollständiger Datenbank-Dump (age/gpg-verschlüsselt, zusätzlich zur Feldverschlüsselung); Löschprotokoll nur mit IDs, Anfrageart und Zeitstempeln. |
| **Empfänger** | Intern: Betreiber. Extern: Off-Site-Speicher, falls `BACKUP_CLOUD_URL` gesetzt (**Auftragsverarbeiter, AVV, EU-Standort**). |
| **Drittland-Transfer** | Nein bei EU-Speicher; sonst Art. 44 ff. prüfen. |
| **Löschfristen** | Rotation 7 täglich / 4 wöchentlich / 3 monatlich (≈ 3 Monate); Löschprotokoll: solange ein Backup älter als der Eintrag existiert, plus 1 Jahr. |
| **TOMs** | Verschlüsselung (age mit offline aufbewahrtem privatem Schlüssel oder gpg AES256 mit Schlüsseldatei 0600), Dateirechte 0600/0700, Integritätsprüfung, Schlüsselhinterlegung im Tresor, vierteljährliche Restore-Probe. Details: `GDPR_ERASURE_RETENTION.md` §4. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb, AVV); Off-Site-Speicheranbieter (AVV). |

---

## V1.5-009 — Auskunft nach Art. 15 (Datenexport)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.5-009 (GDPR-05) |
| **Zweck der Verarbeitung** | Vollständige Auskunft an Kundinnen und Kunden: Stammdaten, Aufträge, Maße, No-Gos, Beratungen (inkl. eigener Wünsche und Angaben zum mitgebrachten Material, Entscheidung D-13), Einwilligungen, Rechnungen, Angebote, Altgold, Wertgutachten, Reparaturen, Kundeninfos, Kostenfreigaben, Foto-Metadaten, Statusverlauf, eigene DSGVO-Anfragen, Zugriffsprotokoll (was/wann, nicht wer) und die Angaben nach Art. 15 Abs. 1 lit. a–h. |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. c iVm Art. 15 DSGVO. |
| **Betroffene Personen** | Kundinnen und Kunden. |
| **Datenkategorien** | wie oben; zurückgehalten nach Art. 15 Abs. 4: Entwurfsarbeit der Goldschmiede, Mitarbeiterkennungen, interne Kalkulation; Fotos/PDFs/Unterschriften als Metadaten, Kopie auf Wunsch. |
| **Empfänger** | Die betroffene Person. |
| **Drittland-Transfer** | Nein. |
| **Löschfristen** | Nachweis `gdpr_requests(request_type='export')`: 3 Jahre (Vorschlag). |
| **TOMs** | Nur ADMIN, Rate-Limit 5 Exporte/Stunde, Audit-Row je Export. Abwägung D-13 **vom Datenschutzberater / Anwalt zu bestätigen**. |
| **Verantwortlicher** | Goldschmiede (siehe Kopf) |
| **Auftragsverarbeiter** | Max Kull (Betrieb, AVV). |

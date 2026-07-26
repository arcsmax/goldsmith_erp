# Verzeichnis von Verarbeitungstaetigkeiten (Art. 30 DSGVO)

**Verantwortlicher:** Max Kull, Goldsmith ERP (Einzelunternehmer)
**Anschrift:** `[AUSFUELLEN — eingetragene Geschaeftsadresse]`
**Kontakt Datenschutzanliegen:** `[AUSFUELLEN — datenschutz@yourdomain.de]`
**DPO-Funktionstraeger:** Max Kull (Selbstbestellung zulaessig < 20 MA, BDSG §38(1); Self-Review-Konflikt siehe DPIA-LIGHT-TEMPLATE.md §8)
**Stand:** 2026-07-26 · **Version:** 1.1 · **Naechste Pflicht-Review:** 2027-04-17 (jaehrlich) oder bei jedem Milestone-Release

**Rechtsgrundlage des Verzeichnisses:** Art. 30 Abs. 1 DSGVO. Pflicht fuer jeden Verantwortlichen, auch unterhalb der 250-MA-Schwelle, wenn die Verarbeitung nicht nur gelegentlich erfolgt oder Risiken fuer Rechte/Freiheiten Betroffener bestehen. Scan-Logs + Mitarbeiter-Zeiterfassung + Kundendatenverarbeitung erfuellen diese Kriterien. **Aufbewahrung: 6 Jahre ab Beendigung der Taetigkeit** (Analogie HGB §257 Abs. 4).

**Verweise:**
- Audit-Grundlage: `V1.1-POST-WAVE5-COMPLIANCE-AUDIT.md` (Anna Becker, 2026-04-17) — Gesamtverdikt GRUEN (bedingt), Score 7/10 ohne Prozess-Dokumente.
- Risiko-/TOM-Detailierung: `DPIA-LIGHT-TEMPLATE.md` §4–§5 (Leicht-DSFA).
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
| **TOMs** | Siehe DPIA-LIGHT-TEMPLATE.md §5: RBAC (`@require_permission`), JWT-abgeleiteter `user_id` (nie aus Payload), Pydantic-Strict-Schema `extra="forbid"`, Idempotency-Key UUIDv4, SQL-Injection-Schutz via ORM. |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A (in-house Podman-Deployment); ggf. Hosting-Provider bei kuenftigem Cloud-Move — AVV nach Art. 28 DSGVO erforderlich. |

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
| **TOMs** | Spec §2.b Payload-Validation (max 500 Zeichen, Control-Chars-Strip, Depth 3, 4-KiB-Ceiling), `StrictRequestBase` blockt `user_id/created_by/...`-Injection, Idempotency-Key UUIDv4, `X-Client-Created-At` ±30d-Fenster. Siehe DPIA-LIGHT-TEMPLATE.md §5. |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

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
| **TOMs** | Siehe DPIA-LIGHT-TEMPLATE.md §5. Alias-Rollen-Guards im AliasService (Spec §7.b). |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. Lieferanten-Stammdaten (Kontakt, Anschrift) werden separat unter V1.1-999 (Lieferanten — pre-V1.1) gefuehrt und sind nicht Teil dieser Aktivitaet. |

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
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

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
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

---

## V1.1-006 — Dateiloeschung (FileErasureService fuer Art. 17)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-006 |
| **Zweck der Verarbeitung** | Loeschen kundenbezogener Dateien im Dateisystem (PDFs, Fotos, Belege) ausserhalb der DB-Zeilen, die bei `scrub_customer_pii` allein zurueckbleiben wuerden. Erfuellt Art. 17(1) „ohne unangemessene Verzoegerung" auch fuer Nicht-DB-Artefakte. |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm Art. 17. |
| **Betroffene Personen** | Kunden, deren Loeschbegehren in V1.1-004 eingereicht wurde. |
| **Datenkategorien** | 5 Datei-Pfade + physische Dateiinhalte: `valuation_certificates.pdf_path` (Schaetzgutachten mit Kunden-Name/Signatur), `order_photos.file_path`, `repair_photos.file_path`, `scrap_gold_items.photo_path`, `scrap_gold.receipt_pdf_path` (Altgold-Beleg mit Signatur). Siehe PII-SCRUB-AUDIT.md O1/O2. |
| **Empfaenger** | Intern: ADMIN (ausloesen); Dateisystem lokal. Extern: keine. |
| **Drittland-Transfer** | Nein. Files liegen auf lokalem Podman-Volume; kein S3/Drittland-Storage in V1.1. |
| **Loeschfristen** | Synchron mit V1.1-004 (30 Tage Grace + Execution). `gdpr_requests.status = PARTIAL_FILE_ERASURE` wenn einzelne Dateien nicht loeschbar (Netzwerk-Share offline, Read-Only) — ADMIN-Nacharbeit erforderlich. |
| **TOMs** | Pfad-Traversal-Guard Zeile 281–321 `file_erasure_service.py`, Symlink-Loop-Schutz, per-Target-Transaktion, Audit-Row in `gdpr_requests`. |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

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
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | Externe Pruefstellen (z. B. Pforzheim) — eigenstaendig Verantwortliche, kein AVV erforderlich. |

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
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

---

## V1.1-009 — Altgold-Ankauf mit Kundensignatur (Scrap Gold Intake)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.1-009 |
| **Zweck der Verarbeitung** | Ankauf von Altgold von Privatkunden, gesetzlich vorgeschriebene Identifikations- und Dokumentationspflicht nach GwG (Geldwaeschegesetz) §§ 10, 12. Erfasst Kundensignatur als Nachweis der Uebergabe und Kaufpreis-Akzeptanz. |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm GwG §10 (Identifikationspflicht bei Bartransaktionen ≥ 10 000 € bzw. ≥ 2 000 € fuer Gueterhaendler mit hohem Bargeldanteil); Art. 6(1)(b) DSGVO (Kaufvertragsabwicklung). **eIDAS-Klassifikation der Signatur: einfache elektronische Signatur (Art. 3 Nr. 10 VO 910/2014)** — Details siehe `EIDAS-ALTGOLD-SIGNATUREN.md`. |
| **Betroffene Personen** | Privatkunden, die Altgold verkaufen. |
| **Datenkategorien** | `scrap_gold.customer_id` (nullable — Walk-in-Kunde moeglich), `signature_data` (base64 PNG, SCRUB-binary Target 25), `notes` (SCRUB Target 24), `receipt_pdf_path` (File-Erasure-Target), `scrap_gold_items.description` (SCRUB Target 26), `photo_path` (File-Erasure-Target), `price_source`. Siehe PII-SCRUB-AUDIT.md Zeilen 63–68. |
| **Empfaenger** | Intern: GOLDSMITH (Ankauf), ADMIN (Financial Oversight). Extern: Finanzamt (Betriebspruefung), GwG-Aufsichtsbehoerde bei Verdachtsmeldung. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | `retention_class = financial_10y` (HGB §257 + GwG §8 Abs. 4). Bei Art. 17-Antrag des Kunden: Datenminimierung auf das GwG-Minimum; Signatur und Foto werden nach Ablauf der GwG-Frist geloescht. |
| **TOMs** | Signatur binary-SCRUB, Foto per FileErasureService, Path-Traversal-Guard. **eIDAS-Empfehlung V1.2**: qualifizierte Signatur fuer Transaktionen > 5 000 € (siehe `EIDAS-ALTGOLD-SIGNATUREN.md`). |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

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
| **TOMs — Status** | **Tolerierte Schwachstelle mit Abhilfefrist 2026-07-31.** Maria hat das Finding in V1.1.5 gescoped (DECISIONS-2026-04-16 V7). Als Interim-Massnahme wird **VIEWER-Zugriff auf `/orders/{id}` audit-geloggt** (Anna-Forderung A14.7; Deadline 2026-06-01 vor V1-Ship). Monatliche DPO-Review der VIEWER-Access-Logs bis Fix live. Legal begruendet: dokumentierte Kenntnis + Mitigation durch Audit-Logging + verbindlicher Fix-Plan entspricht Art. 32(1) „Risikoangemessenheit" bei < 20 MA mit persoenlicher Kenntnis. |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |
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
| **Drittland-Transfer** | Nein. Versand via lokal konfiguriertem SMTP; kein Cloud-/Portal-Dienst. |
| **Loeschfristen** | `cost_change_requests`: `retention_class = financial_10y` (HGB §257 — die §649-Zustimmung ist Finanzbeleg; `order_id` ON DELETE RESTRICT). `customer_updates`: Skelett-Zeile bleibt fuer Art.-30-Nachweis erhalten (`order_id`/`repair_job_id` ON DELETE SET NULL); bei Art. 17 werden die Freitextinhalte (`body`, `reason`, `response_evidence`) via `scrub_customer_pii` auf `[REDACTED]` gesetzt, die Zeilen nicht geloescht. |
| **TOMs** | RBAC (`@require_permission`), Finanzfeld-Sichtbarkeit ADMIN/GOLDSMITH + Audit-Log der Lesezugriffe, Evidence-Logging statt Tracking, DB-partieller Unique-Index „ein-lebendes-§649-Notice pro Auftrag", Pydantic-XOR-Invariante (genau ein FK-Ziel gesetzt), `token` = uuid4. |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A (lokaler SMTP/Podman); bei kuenftigem externem Mailversand AVV nach Art. 28 DSGVO erforderlich. |

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
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

---

## V1.3-002 — Automatisierte Loeschung (Cleanup-Job + Erasure-Endpoints)

| Feld | Inhalt |
|---|---|
| **Lfd. Nr.** | V1.3-002 |
| **Zweck der Verarbeitung** | Automatisierte, fristgerechte Ausfuehrung von Loeschbegehren (Art. 17) nach Ablauf der 30-Tage-Grace-Period. Ergaenzt die Mechanismen aus V1.1-004/005/006 um (a) den geplanten Kunden-Cleanup-Job (`jobs.gdpr_cleanup` → `CustomerService.hard_delete_expired_customers`, systemd-Timer) und (b) die tatsaechlich verdrahteten Erasure-Endpoints, die es zuvor nicht gab: `DELETE /customers/{id}/gdpr-erase` und **neu** `POST /users/{id}/gdpr-erase` (Mitarbeiter, ruft `anonymize_user`). |
| **Rechtsgrundlage** | Art. 6(1)(c) DSGVO iVm Art. 17. Ausnahme Art. 17(3)(b): Kunden mit aufbewahrungspflichtigen Finanzunterlagen (Rechnung/Kostenvoranschlag/Wertgutachten, §147 AO — 10 Jahre) werden **in-place anonymisiert** statt geloescht; ohne solche Unterlagen wird die Zeile hart geloescht. |
| **Betroffene Personen** | Kunden (nach Ablauf der Grace-Period) und Mitarbeiter (Austritt oder Loeschbegehren). |
| **Datenkategorien** | Kundenseitig: alle identifizierenden `customers`-Spalten → `[GELOESCHT]`/NULL bzw. Zeile geloescht, plus Datei-Artefakte (V1.1-006). Mitarbeiterseitig: `users`-PII → Sentinel (V1.1-005). Audit: `customer_audit_logs` (`gdpr_pii_scrub`, `gdpr_file_erasure`) + `gdpr_requests` (`erasure`, `erasure_cleanup`) bleiben erhalten. |
| **Empfaenger** | Intern: ADMIN (loest die Endpoints aus); der Cleanup-Job laeuft unbeaufsichtigt im Backend-Container. Bei Fehlern: WARNING-Benachrichtigung an alle aktiven ADMINs (systemd `OnFailure` → `/admin/notify-gdpr-cleanup`). Extern: ggf. Aufsichtsbehoerde bei Beschwerde. |
| **Drittland-Transfer** | Nein. |
| **Loeschfristen** | 30-Tage-Grace (Soft-Delete `deletion_scheduled_at`), danach taeglicher Cleanup (systemd-Timer). Anonymisierte/geloeschte Kunden koennen bei einem Restore aus einem aelteren Backup fuer bis zu ~3 Monate zurueckkehren — Policy: Cleanup-Job nach jedem Restore erneut ausfuehren (siehe `GDPR_ERASURE_RETENTION.md`, Abschnitt „Backups und Loeschung"). |
| **TOMs** | Pro-Kunde-Transaktion (ein Fehler bricht den Lauf nicht ab), Fail-Loud-Exit-Code + systemd-Alert (keine still verschluckten Fehler), Audit-Row je Schritt, Log nur mit `customer_id`-PK (nie Namen/E-Mail), Last-Admin-Guard bei Mitarbeiter-Anonymisierung, idempotent. Vollstaendige Beschreibung: `docs/technical/GDPR_ERASURE_RETENTION.md`. |
| **Verantwortlicher** | Max Kull |
| **Auftragsverarbeiter** | N/A. |

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

**Unterschrift Verantwortlicher:**

```
_________________________________________
Max Kull, Verantwortlicher nach Art. 4 Nr. 7 DSGVO
Ort, Datum
```

# Löschkonzept und Aufbewahrungsfristen (Retention Schedule)

**Stand:** 2026-09-25 · **Findings:** GDPR-08, GDPR-16 (docs/review/2026-09-25/07-gdpr-privacy.md) · **Entscheidung:** D-08 (offen, Anne mit Datenschutzberater)
**Rechtsgrundlagen:** Art. 5 Abs. 1 lit. e, Art. 5 Abs. 2, Art. 17, Art. 30 Abs. 1 lit. f DSGVO

> **Status: Entwurf.** Die Fristen sind Vorschläge aus dem Audit und aus dem
> Code. Alle Fristen mit dem Hinweis **(StB)** sind **vom Steuerberater zu
> bestätigen**, alle mit **(DSB)** **vom Datenschutzberater zu bestätigen**.
> Bis zur schriftlichen Freigabe läuft der Retention-Sweep nur im
> Probelauf (`RETENTION_EXECUTE=false`, Standard).

## 1. Begriffe

| Aktion | Bedeutung im System |
|---|---|
| **Hart löschen** | Zeile wird mit `DELETE` entfernt; abhängige Zeilen per CASCADE / SET NULL. Dateien auf der Platte löscht `FileErasureService`. |
| **Anonymisieren** | Zeile bleibt (Fremdschlüssel aufbewahrungspflichtiger Belege lösen weiter auf), alle identifizierenden Spalten werden durch Platzhalter ersetzt (`CustomerService.anonymize_customer`, `UserService.anonymize_user` → `deleted_user_<HMAC>`). |
| **Freitext schwärzen** | Namen, Telefonnummern, E-Mail-Adressen in Freitextfeldern werden zu `[REDACTED]` (`CustomerService.scrub_customer_pii`, Liste `SCRUBBABLE_FIELDS`). |
| **Legal Hold** | Beleg bleibt **unverändert** (GoBD: keine Veränderung von Buchungsbelegen). `customers.retention_hold_until` hält fest, bis wann (Art. 17 Abs. 3 lit. b DSGVO). |
| **Rotation** | Datei wird durch den Backup-Zyklus überschrieben/gelöscht. |

Fristen laufen, wenn nicht anders angegeben, ab **Ende des Kalenderjahres**, in dem der Datensatz entstanden ist (§147 Abs. 4 AO, §257 Abs. 5 HGB).

## 2. Wer löscht was, wann

| Mechanismus | Auslöser | Status 2026-09-25 |
|---|---|---|
| Art. 17-Antrag `DELETE /customers/{id}/gdpr-erase` | ADMIN | läuft: deaktiviert, schwärzt Freitext, löscht Dateien, setzt Legal Hold und `deletion_scheduled_at = +30 Tage` |
| GDPR-Cleanup `jobs.gdpr_cleanup` | systemd-Timer täglich (`scripts/install-timers.sh`) | läuft: nach 30 Tagen hart löschen oder anonymisieren (bei Belegen) |
| Retention-Sweep `jobs.retention_sweep` | systemd-Timer wöchentlich (`scripts/install-timers.sh`) | **Probelauf** bis Freigabe D-08; deckt nur `scan_logs`, `time_entries`, `material_usage` ab |
| Löschwiederholung nach Restore `cli.gdpr_replay_erasures` | `scripts/restore.sh` | läuft (GDPR-07) |
| Backup-Rotation `scripts/backup.sh` | täglich (cron/Timer) | läuft: 7 täglich, 4 wöchentlich, 3 monatlich (≈ 3 Monate) |

**Sweep scharf schalten:** nach schriftlicher Freigabe in `.env.production`
`RETENTION_EXECUTE=true` setzen (gilt im Backend-Container). Einzelner
Probelauf trotz Freigabe: `python -m goldsmith_erp.jobs.retention_sweep --dry-run`.

## 3. Fristen je Tabelle

Legende Spalte „Automatisiert": **ja** = ein Job setzt es heute um, **Art. 17** = nur bei Löschantrag, **nein** = noch manuell / offen (siehe Abschnitt 4).

### 3.1 Kunden und Kundenkommunikation

| Tabelle | Klasse | Rechtsgrundlage | Frist | Löschen heißt | Automatisiert |
|---|---|---|---|---|---|
| `customers` | Stammdaten | Art. 6 Abs. 1 lit. b DSGVO | 3 Jahre nach letztem Kontakt ohne offene Belege, dann nachfragen oder löschen (DSB) | Hart löschen; bei Belegen anonymisieren + Legal Hold | Art. 17; inaktive Kunden: **nein** |
| `customer_measurements` | Stammdaten | Art. 6 Abs. 1 lit. b | wie `customers` | Hart löschen (CASCADE) | Art. 17 |
| `customer_no_gos` (inkl. Allergien) | Gesundheitsdaten (Art. 9) | Art. 9 Abs. 2 lit. a (Einwilligung) | bis Widerruf, spätestens mit dem Kunden | Hart löschen, sofort bei Widerruf | ja (Widerruf), Art. 17 |
| `customer_consents` | Einwilligungsnachweis | Art. 7 Abs. 1 | Nachweis 3 Jahre nach Widerruf (Verjährung §195 BGB) (DSB) | Hart löschen | Art. 17 (heute sofort — siehe 4.3) |
| `consultations` | Beratung | Art. 6 Abs. 1 lit. b (vorvertraglich) | nicht umgewandelte Beratungen: 24 Monate (DSB) | Hart löschen inkl. `consultation_photos` + Dateien | **nein** |
| `consultation_photos` | Skizzen/Fotos | Art. 6 Abs. 1 lit. b | wie `consultations` | Hart löschen + Datei | Art. 17 (Dateien) |
| `customer_updates` | Kundeninfo (E-Mail/PDF) | Art. 6 Abs. 1 lit. b | 3 Jahre nach Auftragsende (Gewährleistung + Verjährung) (DSB) | Freitext schwärzen, Skelettzeile bleibt | Art. 17 |
| `cost_change_requests` (§649 BGB) | Finanzbeleg | Art. 6 Abs. 1 lit. c iVm §257 HGB | 6 Jahre (Handelsbrief) (StB) | Freitext schwärzen (`reason`, `response_evidence`) | Art. 17 |
| `notifications` | interne Hinweise (können Kundennamen enthalten) | Art. 6 Abs. 1 lit. f | 12 Monate (DSB) | Hart löschen | **nein** |
| Redis-Portal-Tokens | Sitzung | Art. 6 Abs. 1 lit. b | 1 Stunde | Ablauf (TTL) | ja |

### 3.2 Aufträge, Reparaturen, Fotos

| Tabelle | Klasse | Rechtsgrundlage | Frist | Löschen heißt | Automatisiert |
|---|---|---|---|---|---|
| `orders` | `indefinite_business` / `hallmark_10y` | Art. 6 Abs. 1 lit. b, c | Gewährleistung 2 Jahre nach Übergabe + 3 Jahre Verjährung zum Jahresende; Punzierung ≥ 10 Jahre (StB) | Kundenbezug über Kunden-Anonymisierung; Auftragszeile bleibt | **nein** (bewusst ausgeschlossen, siehe `EXCLUDED_NOTE` im Sweep) |
| `order_events`, `order_status_history` | Auftragshistorie | Art. 6 Abs. 1 lit. b, f | wie `orders` | mit dem Auftrag | nein |
| `order_comments` | interner Freitext | Art. 6 Abs. 1 lit. b | wie `orders` | Freitext schwärzen | Art. 17 |
| `order_photos` | Fotos des Schmuckstücks | Art. 6 Abs. 1 lit. b | wie `orders`; Portfolio-Nutzung nur mit Einwilligung `photo_use` | Datei löschen, Zeile bleibt | Art. 17 |
| `repair_jobs` | Reparatur | Art. 6 Abs. 1 lit. b | 3 Jahre nach Abholung (DSB) | Freitext schwärzen; Kundenbezug über Anonymisierung | Art. 17 |
| `repair_photos` | Fotos | Art. 6 Abs. 1 lit. b | wie `repair_jobs` | Datei löschen | Art. 17 |
| `calendar_events` | Termine | Art. 6 Abs. 1 lit. b | 12 Monate nach Termin (DSB) | Hart löschen | nein |
| `order_handoffs` | interne Übergaben | Art. 6 Abs. 1 lit. b, §26 BDSG | wie `orders` | mit dem Auftrag | nein |

### 3.3 Finanz- und Aufbewahrungsbelege (Legal Hold)

| Tabelle | Klasse | Rechtsgrundlage | Frist | Löschen heißt | Automatisiert |
|---|---|---|---|---|---|
| `invoices`, `invoice_line_items` (inkl. `snapshot`, `issued_pdf`) | Buchungsbeleg | §147 Abs. 1 Nr. 4, Abs. 3 AO; §14b UStG | **8 Jahre** seit BEG IV (Code nutzt konservativ 10) (StB) | Legal Hold, unverändert; danach hart löschen | Hold ja; Löschen nach Ablauf **nein** |
| `quotes`, `quote_line_items` (inkl. Signatur) | Handelsbrief (angenommen) | §257 Abs. 1 Nr. 2, 3 HGB; §147 AO | 6 Jahre angenommen; nicht angenommene: 12 Monate (StB) | Legal Hold; heute werden **alle** Angebote gehalten (konservativ) | Hold ja; Löschen **nein** |
| `scrap_gold`, `scrap_gold_items` (Altgold, Signatur, Beleg-PDF) | Ankaufsbeleg / GwG | §147 AO; §8 Abs. 4 GwG (5 Jahre) | längere der beiden Fristen (StB) | Legal Hold | Hold ja; Löschen **nein** |
| `valuation_certificates` | Wertgutachten | §257 HGB | 6–10 Jahre (StB) | Legal Hold | Hold ja; Löschen **nein** |
| `time_entries`, `interruptions` | `financial_10y` | §257 HGB / §147 AO | 10 Jahre zum Jahresende (Code) — prüfen, ob 8 genügen (StB) | Hart löschen | **ja** (Sweep, Probelauf) |
| `material_usage` | `financial_10y` | §257 HGB / §147 AO | wie `time_entries` | Hart löschen | **ja** (Sweep, Probelauf) |
| `metal_purchases`, `inventory_adjustments` | Buchungsbeleg (kein Personenbezug) | §147 AO | 8–10 Jahre (StB) | Hart löschen | nein |
| `estimate_accuracy` | Kalkulation | §257 HGB | an Auftrag gebunden | mit dem Auftrag | nein |

### 3.4 Mitarbeitende und Protokolle

| Tabelle | Klasse | Rechtsgrundlage | Frist | Löschen heißt | Automatisiert |
|---|---|---|---|---|---|
| `users` | Beschäftigtendaten | §26 BDSG | bis Austritt; danach anonymisieren | Anonymisieren (`deleted_user_<HMAC>`) | Art. 17 (`POST /users/{id}/gdpr-erase`) |
| `scan_logs` | `standard_24m` | Art. 6 Abs. 1 lit. f | 24 Monate rollierend | Hart löschen | **ja** (Sweep, Probelauf) |
| `location_history` | Lagerort-Protokoll | Art. 6 Abs. 1 lit. f | 24 Monate (DSB) | Hart löschen | nein |
| `customer_audit_logs` | Rechenschaft (Art. 5 Abs. 2) | Art. 6 Abs. 1 lit. c, f | 3 Jahre; Einträge zu Art. 17-Löschungen so lange wie der Nachweis nötig ist (DSB) | Hart löschen; bei Löschantrag des Mitarbeiters anonymisieren | **nein** |
| `gdpr_requests` | Nachweis Betroffenenrechte | Art. 5 Abs. 2 | 3 Jahre nach Erledigung (DSB); **nicht vor** dem Ende der Backup-Rotation + Erasure-Ledger-Bedarf | Hart löschen | nein |
| Erasure-Ledger (Datei) | Nachweis + Restore-Schutz | Art. 5 Abs. 2, Art. 17 | so lange wie das älteste Backup + 1 Jahr | Zeilen älter als das älteste Backup entfernen | nein |
| Request-Logs (Container) | Betrieb | Art. 6 Abs. 1 lit. f | 14 Tage (Log-Rotation) (DSB) | Rotation | abhängig vom Host |

### 3.5 Ohne Personenbezug

`materials`, `activities`, `gemstones`, `metal_price_history`, `custom_metal_types`, `label_templates`, `barcode_aliases`, `order_items`, `notification_preferences`, `order_hallmarks`: kein oder nur mittelbarer Personenbezug; Aufbewahrung nach betrieblichem Bedarf bzw. mit dem Auftrag.

### 3.6 Backups

| Artefakt | Frist | Löschen heißt |
|---|---|---|
| Verschlüsselte DB-Dumps (`*.sql.gz.age` / `.gpg`) | ≈ 3 Monate (7 d / 4 w / 3 m) | Rotation in `backup.sh`; eine Löschung aus dem Live-System wirkt nach Restore über die Löschwiederholung (GDPR_ERASURE_RETENTION.md §4.2) |
| Off-Site-Kopien (`backup-sync.sh`) | wie lokal | beim Anbieter mitrotieren (AVV!) |

## 4. Offene Punkte (vor `RETENTION_EXECUTE=true`)

1. **Sweep-Abdeckung erweitern** (W5-07): inaktive Kunden, nicht umgewandelte Beratungen, nicht angenommene Angebote, `notifications`, `customer_audit_logs`, `calendar_events`, `location_history`. Jeder neue Eintrag braucht einen eigenen Test und ist Löschlogik mit Kaskaden (Dateien, Fremdschlüssel) — bewusst nicht in diesem Schritt ergänzt.
2. **Ablauf des Legal Hold**: nichts löscht heute Belege nach `retention_hold_until`. Braucht einen Job, der nach Fristablauf Rechnung/Angebot/Altgold samt anonymisiertem Kunden entfernt.
3. **8 statt 10 Jahre** (BEG IV) für Buchungsbelege: Code und Sweep nutzen `financial_10y` / `RETENTION_YEARS = 10`. Vom Steuerberater bestätigen lassen, dann anpassen (Übermaß ist selbst ein Verstoß gegen Art. 5 Abs. 1 lit. e).
4. **Einwilligungsnachweise**: heute werden `customer_consents` bei Art. 17 sofort gelöscht. Ob der Nachweis erteilter/widerrufener Einwilligungen (Art. 7 Abs. 1) länger aufbewahrt werden muss, vom Datenschutzberater bestätigen lassen.
5. **Freigabe D-08** schriftlich (Anne + Datenschutzberater), danach `RETENTION_EXECUTE=true`.

## 5. Freigabe

```
Freigegeben (Verantwortliche):  ______________________   Datum: __________
Geprüft (Datenschutzberater):    ______________________   Datum: __________
Fristen Finanzbelege (StB):      ______________________   Datum: __________
```

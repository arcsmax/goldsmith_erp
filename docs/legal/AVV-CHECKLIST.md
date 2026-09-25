# Checkliste Auftragsverarbeitung (AVV, Art. 28 DSGVO)

**Verantwortliche:** [Name der Goldschmiede], Inhaberin Anne [Nachname] (Entscheidung D-19)
**Stand:** 2026-09-25 · **Findings:** GDPR-06, GDPR-15 (docs/review/2026-09-25/07-gdpr-privacy.md)

> Die Einordnung als Auftragsverarbeiter, eigener Verantwortlicher oder „kein Personenbezug“ ist **vom Datenschutzberater zu bestätigen**, sobald feststeht, welche Anbieter tatsächlich genutzt werden (die Konfiguration ist zur Laufzeit änderbar, z. B. der SMTP-Host durch ADMIN).

## 1. Übersicht

| Dritter | Was er bekommt | Rolle | AVV nötig? | Wo im System | Status |
|---|---|---|---|---|---|
| **Max Kull** (Betrieb, Wartung, Updates, Datensicherung) | Vollzugriff auf Server, Datenbank, Backups, Schlüssel | Auftragsverarbeiter | **ja** | Server, `.env.production`, `scripts/` | [ ] AVV unterschrieben |
| **E-Mail-Anbieter** (z. B. IONOS, Strato, Google Workspace) | Empfängeradresse, Betreff, Text, Foto-Anhänge, Rechnungs-/Angebots-PDFs; Kopien im „Gesendet“-Ordner | Auftragsverarbeiter | **ja** (meist Standard-AVV im Kundenkonto des Anbieters) | `SMTP_HOST` (`admin_email.py`, `.env.production`) | [ ] Anbieter: ______ [ ] AVV abgeschlossen [ ] EU-Standort geprüft |
| **Speicheranbieter für Off-Site-Backups** | verschlüsselte Datenbank-Dumps, Löschprotokoll | Auftragsverarbeiter | **ja**, sobald `BACKUP_CLOUD_URL` gesetzt ist | `scripts/backup-sync.sh` | [ ] genutzt? [ ] AVV [ ] EU-Standort |
| **Hosting/Rechenzentrum** (nur falls der Server nicht in der Werkstatt steht) | alles | Auftragsverarbeiter | **ja** | — | [ ] entfällt (Server vor Ort) |
| **IT-Dienstleister für Hardware-Reparatur** (falls Festplatten das Haus verlassen) | ggf. unverschlüsselte Datenträger | Auftragsverarbeiter | **ja**, oder Datenträger vorher entfernen | — | [ ] Regel festlegen |
| **Steuerberater** | DATEV/lexoffice-Export, Rechnungen | **eigener Verantwortlicher** (§57 StBerG, berufliche Weisungsfreiheit) | **nein**, aber im Verzeichnis als Empfänger führen | `services/accounting_export_service.py` | [x] als Empfänger geführt |
| **Metallpreis-API** | nur Metallart; technisch die Server-IP | kein Personenbezug | **nein** | `METAL_PRICE_API_URL`, `metal_price_service.py` | [x] geprüft: keine Kunden-/Mitarbeiterdaten |
| **Prüfstellen für Punzierung** (z. B. Pforzheim) | Stück, Auftragsnummer | eigener Verantwortlicher | nein | V1.1-007 | [x] |
| **Versicherungen** (Wertgutachten übergibt der Kunde selbst) | — | — | nein | — | [x] |
| **Softwareanbieter von Abhängigkeiten, GitHub** | keine Produktivdaten (Code, CI mit Testdaten) | kein Personenbezug | nein, solange keine Echtdaten in Issues/Logs | `.github/` | [ ] Regel: keine Echtdaten in Issues |

## 2. Mindestinhalt jedes AVV (Art. 28 Abs. 3 DSGVO)

- [ ] Gegenstand, Dauer, Art und Zweck der Verarbeitung, Art der Daten, Kategorien Betroffener
- [ ] Verarbeitung nur auf dokumentierte Weisung
- [ ] Vertraulichkeitsverpflichtung der eingesetzten Personen
- [ ] Technische und organisatorische Maßnahmen (für den Betreiber: `docs/technical/security/TOMS.md` als Anlage)
- [ ] Unterauftragsverarbeiter nur mit Genehmigung (Liste als Anlage)
- [ ] Unterstützung bei Betroffenenrechten (Auskunft, Löschung inkl. Löschprotokoll/Restore)
- [ ] Unterstützung bei Datenpannen: Meldung an die Verantwortliche **unverzüglich**, spätestens innerhalb von [24] Stunden (damit die 72-h-Frist gehalten werden kann, siehe BREACH-RUNBOOK.md)
- [ ] Löschung oder Rückgabe aller Daten und Backups nach Vertragsende
- [ ] Nachweise und Kontrollrechte der Verantwortlichen

## 3. Besonderheiten Betreiber-AVV (Max Kull)

- Schlüssel (`ENCRYPTION_KEY`, `ANONYMIZATION_SALT`, Backup-Schlüssel) gehören der Verantwortlichen; der Betreiber hält Kopien nur zum Betrieb. Ausgedruckte Hinterlegung im Tresor der Inhaberin.
- Zugriff auf Produktivdaten nur für Betrieb, Fehlerbehebung und auf Weisung; keine Nutzung für Entwicklung oder Demos (Demo-Daten verwenden).
- Der Betreiber wird **nicht** als Datenschutzbeauftragter benannt (Selbstkontrolle, Art. 38 Abs. 6 DSGVO).
- Wird das System künftig für weitere Werkstätten betrieben: je Werkstatt eigener AVV und strikte Mandantentrennung.

## 4. Offene technische Punkte, die das Vertragsrisiko senken

- [ ] TLS zum Mailserver auf jedem Port erzwingen (W5-09; heute nur 587/465 abgesichert).
- [ ] Off-Site-Upload mit Authentifizierung statt „die URL ist das Passwort“ (GDPR-06, `backup-sync.sh`).
- [ ] `./uploads` (Fotos, PDFs) verschlüsselt mitsichern.

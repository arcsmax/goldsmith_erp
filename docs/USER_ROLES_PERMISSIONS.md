# Goldsmith ERP - Benutzerrollen und Berechtigungen

**RBAC (Role-Based Access Control) Referenz**
Version 1.0 | Stand: November 2025

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Die drei Rollen](#die-drei-rollen)
3. [Berechtigungsmatrix](#berechtigungsmatrix)
4. [Admin-Rolle](#admin-rolle)
5. [Goldsmith-Rolle](#goldsmith-rolle)
6. [Viewer-Rolle](#viewer-rolle)
7. [Wann welche Rolle?](#wann-welche-rolle)
8. [Ihre Rolle prüfen](#ihre-rolle-prüfen)
9. [Rolle wechseln lassen](#rolle-wechseln-lassen)
10. [Berechtigungsfehler verstehen](#berechtigungsfehler-verstehen)

---

## Überblick

Goldsmith ERP verwendet ein **Rollenbasiertes Berechtigungssystem (RBAC)**, um sicherzustellen, dass jeder Benutzer nur auf die Funktionen zugreifen kann, die für seine Arbeit notwendig sind.

### Warum Rollen?

✅ **Sicherheit**: Kritische Funktionen nur für autorisierte Personen
✅ **Klarheit**: Jeder weiß, was er darf und was nicht
✅ **Datenschutz**: Sensible Daten nur für berechtigte Nutzer
✅ **Kontrolle**: Admins behalten Übersicht über Zugriffsrechte

### Die drei Rollen im Überblick

| Rolle | Symbol | Zielgruppe | Zugriffslevel |
|-------|--------|------------|---------------|
| **Admin** | 👑 | Geschäftsinhaber, IT-Manager | Voller Zugriff |
| **Goldsmith** | 🔨 | Werkstatt-Mitarbeiter | Produktiv arbeiten |
| **Viewer** | 👁️ | Praktikanten, Buchhaltung | Nur ansehen |

---

## Die drei Rollen

### 👑 Admin (Administrator)

**Vollzugriff auf alle Systemfunktionen**

Admins sind die "Superuser" des Systems und haben keine Einschränkungen.

**Typische Nutzer**:
- Geschäftsinhaber
- IT-Verantwortliche
- Systemadministratoren

**Kernaufgaben**:
- Benutzerverwaltung
- Systemkonfiguration
- Materialstammdaten pflegen
- Alle Berichte und Auswertungen

---

### 🔨 Goldsmith (Goldschmied)

**Zugriff auf tägliche Produktivfunktionen**

Goldsmiths können alle Aufgaben erledigen, die für die tägliche Werkstattarbeit notwendig sind.

**Typische Nutzer**:
- Goldschmiede
- Werkstatt-Mitarbeiter
- Gesellen
- Meister

**Kernaufgaben**:
- Aufträge erstellen und bearbeiten
- Arbeitszeiten erfassen
- Materialbestände anpassen
- Kundendaten pflegen

---

### 👁️ Viewer (Betrachter)

**Nur-Lese-Zugriff ohne Änderungsmöglichkeiten**

Viewers können Informationen einsehen, aber nichts erstellen, bearbeiten oder löschen.

**Typische Nutzer**:
- Praktikanten
- Auszubildende
- Buchhaltung
- Externe Berater
- Management (Überblick)

**Kernaufgaben**:
- Aufträge ansehen
- Berichte lesen
- Materialbestände prüfen

---

## Berechtigungsmatrix

Eine vollständige Übersicht, wer was darf:

### Aufträge (Orders)

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Aufträge ansehen | ✅ | ✅ | ✅ |
| Auftrag erstellen | ✅ | ✅ | ❌ |
| Auftrag bearbeiten | ✅ | ✅ | ❌ |
| Auftrag löschen | ✅ | ❌ | ❌ |
| Materialien hinzufügen | ✅ | ✅ | ❌ |
| Status ändern | ✅ | ✅ | ❌ |
| Fotos hochladen | ✅ | ✅ | ❌ |

---

### Materialien (Materials)

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Materialien ansehen | ✅ | ✅ | ✅ |
| Material erstellen | ✅ | ❌ | ❌ |
| Material bearbeiten | ✅ | ❌ | ❌ |
| Material löschen | ✅ | ❌ | ❌ |
| Bestand anpassen | ✅ | ✅ | ❌ |
| Lagerberichte ansehen | ✅ | ✅ | ✅ |
| Lagerwert berechnen | ✅ | ✅ | ✅ |

> **Hinweis**: Goldsmiths können Bestände anpassen (z.B. bei Materialverbrauch), aber keine neuen Materialien anlegen.

---

### Zeiterfassung (Time Tracking)

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Zeit starten/stoppen | ✅ | ✅ | ❌ |
| Eigene Zeiten ansehen | ✅ | ✅ | ✅ |
| Alle Zeiten ansehen | ✅ | ❌ | ❌ |
| Zeiteinträge bearbeiten | ✅ | ✅ | ❌ |
| Zeiteinträge löschen | ✅ | ❌ | ❌ |
| Unterbrechungen hinzufügen | ✅ | ✅ | ❌ |
| Zeitberichte ansehen | ✅ | ✅ | ✅ |

> **Wichtig**: Goldsmiths sehen nur ihre eigenen Zeiteinträge. Admins sehen alle Zeiten.

---

### Aktivitäten (Activities)

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Aktivitäten ansehen | ✅ | ✅ | ✅ |
| Aktivität erstellen | ✅ | ✅ | ❌ |
| Aktivität bearbeiten | ✅ | ❌ | ❌ |
| Aktivität löschen | ✅ | ❌ | ❌ |

> **Hinweis**: Goldsmiths können eigene Aktivitäten erstellen (z.B. "Kettchen reparieren"), aber nicht bearbeiten oder löschen.

---

### Kunden (Customers)

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Kunden ansehen | ✅ | ✅ | ✅ |
| Kunde erstellen | ✅ | ✅ | ❌ |
| Kunde bearbeiten | ✅ | ✅ | ❌ |
| Kunde löschen | ✅ | ❌ | ❌ |

---

### Benutzer (Users)

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Benutzer ansehen | ✅ | ❌ | ❌ |
| Benutzer erstellen | ✅ | ❌ | ❌ |
| Benutzer bearbeiten | ✅ | ❌ | ❌ |
| Benutzer deaktivieren | ✅ | ❌ | ❌ |
| Rollen zuweisen | ✅ | ❌ | ❌ |
| Eigenes Profil bearbeiten | ✅ | ✅ | ✅ |

> **Wichtig**: Nur Admins können Benutzer verwalten. Jeder kann aber sein eigenes Profil bearbeiten.

---

### Berichte (Reports)

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Berichte ansehen | ✅ | ✅ | ✅ |
| Berichte exportieren | ✅ | ✅ | ❌ |

---

### Systemkonfiguration

| Funktion | Admin | Goldsmith | Viewer |
|----------|-------|-----------|--------|
| Systemeinstellungen | ✅ | ❌ | ❌ |
| Datenbank-Backup | ✅ | ❌ | ❌ |

---

## Admin-Rolle

### Vollständige Berechtigungen

Als Admin haben Sie **uneingeschränkten Zugriff** auf alle Funktionen:

#### Aufträge
- ✅ Alle Aktionen (Erstellen, Bearbeiten, Löschen)

#### Materialien
- ✅ Alle Aktionen (Erstellen, Bearbeiten, Löschen, Bestand anpassen)

#### Zeiterfassung
- ✅ Alle Zeiteinträge sehen
- ✅ Alle Zeiteinträge bearbeiten und löschen

#### Benutzer
- ✅ Benutzer erstellen und verwalten
- ✅ Rollen zuweisen
- ✅ Benutzer aktivieren/deaktivieren

#### Aktivitäten
- ✅ Alle Aktionen (Erstellen, Bearbeiten, Löschen)

#### Kunden
- ✅ Alle Aktionen (Erstellen, Bearbeiten, Löschen)

#### System
- ✅ Systemkonfiguration
- ✅ Backups erstellen
- ✅ Alle Berichte und Auswertungen

### Verantwortung

Mit großer Macht kommt große Verantwortung:

⚠️ **Admins sollten**:
- Benutzerkonten sorgfältig verwalten
- Regelmäßig Backups erstellen
- Rollen nur nach Bedarf zuweisen
- Kritische Aktionen dokumentieren

❌ **Admins sollten nicht**:
- Admin-Rechte an Unbefugte vergeben
- Produktivdaten ohne Backup löschen
- Systemeinstellungen ohne Grund ändern

---

## Goldsmith-Rolle

### Produktiv-Berechtigungen

Als Goldsmith können Sie alle täglichen Arbeitsaufgaben erledigen:

#### ✅ Was Sie können

**Aufträge**:
- Neue Aufträge erstellen
- Bestehende Aufträge bearbeiten
- Status ändern (Pending → In Progress → Completed)
- Materialien zu Aufträgen hinzufügen
- Fotos hochladen

**Materialien**:
- Materialbestand ansehen
- Bestand anpassen (bei Verbrauch)
- Lagerberichte ansehen

**Zeiterfassung**:
- Arbeitszeit starten und stoppen
- Eigene Zeiteinträge ansehen
- Eigene Zeiteinträge bearbeiten
- Aktivitäten zuordnen

**Aktivitäten**:
- Neue Aktivitäten erstellen (eigene)

**Kunden**:
- Neue Kunden anlegen
- Kundeninformationen bearbeiten

#### ❌ Was Sie nicht können

**Aufträge**:
- Aufträge löschen (nur Admin)

**Materialien**:
- Neue Materialien anlegen (nur Admin)
- Materialien löschen (nur Admin)
- Preise ändern (nur Admin)

**Zeiterfassung**:
- Zeiteinträge anderer Benutzer sehen
- Zeiteinträge löschen

**Benutzer**:
- Benutzer verwalten (nur Admin)

**System**:
- Systemkonfiguration (nur Admin)

### Typische Arbeitstage

**Morgens**:
1. Anmelden
2. Offene Aufträge prüfen
3. Arbeit an Auftrag starten
4. Zeit erfassen

**Tagsüber**:
1. Materialverbrauch dokumentieren
2. Zeiterfassung bei Pausen stoppen
3. Auftragsstatus aktualisieren
4. Fotos von Zwischenständen hochladen

**Abends**:
1. Zeiterfassung stoppen
2. Tagesfortschritt dokumentieren
3. Nächste Schritte notieren

---

## Viewer-Rolle

### Nur-Lese-Berechtigungen

Als Viewer können Sie Informationen einsehen, aber nichts verändern:

#### ✅ Was Sie können

**Aufträge**:
- Alle Aufträge ansehen
- Auftragsdetails lesen
- Materialzuordnungen sehen
- Fotos ansehen

**Materialien**:
- Materialbestand ansehen
- Lagerberichte ansehen
- Lagerwert prüfen

**Zeiterfassung**:
- Eigene Zeiteinträge ansehen
- Eigene Zeitberichte ansehen

**Kunden**:
- Kundenliste ansehen
- Kundendetails lesen

**Berichte**:
- Alle Berichte ansehen

#### ❌ Was Sie nicht können

Sie können **nichts** erstellen, bearbeiten oder löschen:

- ❌ Keine Aufträge erstellen/bearbeiten
- ❌ Keine Materialien ändern
- ❌ Keine Zeiterfassung
- ❌ Keine Kunden anlegen/bearbeiten
- ❌ Keine Benutzerverwaltung
- ❌ Keine Systemkonfiguration

### Typische Anwendungsfälle

**Praktikanten**:
- System kennenlernen
- Prozesse verstehen
- Ohne Risiko von Fehlbedienungen

**Buchhaltung**:
- Auftragswerte prüfen
- Materialkosten einsehen
- Berichte für Abrechnung

**Management**:
- Übersicht über Aufträge
- Materialverbrauch kontrollieren
- Berichte für Entscheidungen

---

## Wann welche Rolle?

### Entscheidungshilfe

| Situation | Empfohlene Rolle |
|-----------|------------------|
| Geschäftsinhaber mit vollem Systemzugriff | 👑 Admin |
| IT-Verantwortlicher für Systemwartung | 👑 Admin |
| Goldschmied in der Werkstatt (täglich) | 🔨 Goldsmith |
| Geselle, der Aufträge bearbeitet | 🔨 Goldsmith |
| Praktikant zum Lernen (ohne Änderungen) | 👁️ Viewer |
| Buchhaltung (nur Berichte ansehen) | 👁️ Viewer |
| Externer Berater (nur Einblick) | 👁️ Viewer |

### Rollenwechsel im Laufe der Zeit

Es ist normal, dass sich Rollen ändern:

- **Praktikant** → **Goldsmith** (nach Einarbeitung)
- **Goldsmith** → **Admin** (bei Übernahme von Verantwortung)
- **Admin** → **Goldsmith** (bei Spezialisierung auf Werkstatt)

---

## Ihre Rolle prüfen

### Im System

So sehen Sie Ihre aktuelle Rolle:

1. Klicken Sie rechts oben auf Ihren Namen
2. Im Dropdown-Menü steht: **"Rolle: [Ihre Rolle]"**

`[Screenshot: User-Menü mit Rollen-Anzeige]`

### Bei Berechtigungsproblemen

Wenn Sie eine Funktion nicht nutzen können:

1. Prüfen Sie Ihre Rolle
2. Schauen Sie in diese Matrix, ob die Funktion für Ihre Rolle freigeschaltet ist
3. Kontaktieren Sie Ihren Admin, falls Sie mehr Rechte benötigen

---

## Rolle wechseln lassen

### Anfrage stellen

Wenn Sie meinen, dass Ihre aktuelle Rolle nicht passt:

1. **Kontaktieren Sie Ihren Admin**:
   - E-Mail an: [admin@ihre-firma.de]
   - Telefon: [+49 XXX XXXXXXX]

2. **Begründen Sie die Anfrage**:
   - Welche Funktion benötigen Sie?
   - Warum ist die Funktion wichtig für Ihre Arbeit?
   - Wie oft benötigen Sie die Funktion?

3. **Admin prüft und entscheidet**:
   - Sicherheitsaspekte
   - Notwendigkeit
   - Alternative Lösungen

### Rollenwechsel durch Admin

Admins können Rollen über die Benutzerverwaltung ändern:

1. Zu **Benutzer** → **Benutzerliste**
2. Benutzer auswählen
3. **Rolle ändern** wählen
4. Neue Rolle zuweisen
5. Speichern

> **Hinweis**: Rollenwechsel werden sofort wirksam. Der Benutzer muss sich ggf. neu anmelden.

---

## Berechtigungsfehler verstehen

### HTTP 403 - Forbidden

Wenn Sie eine Aktion durchführen möchten, für die Sie keine Berechtigung haben, sehen Sie:

```
403 Forbidden
Permission denied: [PERMISSION_NAME]
Required role: Admin
```

**Was bedeutet das?**

- Sie haben nicht die erforderliche Rolle
- Die Aktion ist für Ihre Rolle gesperrt
- Kontaktieren Sie Ihren Admin, wenn Sie diese Funktion benötigen

`[Screenshot: 403-Fehler]`

### Häufige Fehler

| Fehlermeldung | Bedeutung | Lösung |
|---------------|-----------|--------|
| `Permission denied: ORDER_DELETE` | Sie dürfen Aufträge nicht löschen | Nur Admins können löschen |
| `Permission denied: USER_MANAGE` | Sie dürfen Benutzer nicht verwalten | Nur Admins können Benutzer verwalten |
| `Permission denied: MATERIAL_CREATE` | Sie dürfen keine Materialien anlegen | Admin fragen, Material anzulegen |
| `Permission denied: TIME_VIEW_ALL` | Sie dürfen nur eigene Zeiten sehen | Admins sehen alle Zeiten |

### Was tun bei Berechtigungsfehler?

1. **Prüfen Sie Ihre Rolle** (siehe oben)
2. **Schauen Sie in die Matrix**, ob die Funktion für Ihre Rolle verfügbar ist
3. **Kontaktieren Sie Ihren Admin**, falls Sie die Funktion benötigen
4. **Lesen Sie**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md) für weitere Hilfe

---

## Zusammenfassung

### Rollen-Übersicht

| Aspekt | Admin | Goldsmith | Viewer |
|--------|-------|-----------|--------|
| Zugriffslevel | Voll | Produktiv | Nur Lesen |
| Aufträge | Alle Aktionen | Erstellen, Bearbeiten | Nur ansehen |
| Materialien | Alle Aktionen | Bestand anpassen | Nur ansehen |
| Zeiterfassung | Alle Zeiten | Eigene Zeiten | Eigene Zeiten |
| Benutzer | Vollzugriff | Nein | Nein |
| System | Vollzugriff | Nein | Nein |

### Wichtigste Erkenntnisse

✅ **Drei Rollen**: Admin, Goldsmith, Viewer
✅ **RBAC**: Rollenbasierte Zugriffskontrolle
✅ **Granular**: Verschiedene Berechtigungen pro Funktion
✅ **Flexibel**: Rollen können von Admins geändert werden
✅ **Sicher**: Kritische Funktionen nur für autorisierte Nutzer

---

## Weitere Informationen

📖 **Erste Schritte**: [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md)
📖 **Benutzerverwaltung** (für Admins): [FEATURE_USER_MANAGEMENT.md](FEATURE_USER_MANAGEMENT.md)
📖 **Problemlösungen**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
📖 **Häufige Fragen**: [FAQ.md](FAQ.md)

---

**Bei Fragen zu Berechtigungen wenden Sie sich an Ihren Systemadministrator!** 🔐

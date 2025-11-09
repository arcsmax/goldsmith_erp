# Goldsmith ERP - Erste Schritte

**Benutzerhandbuch für Goldschmiede**
Version 1.0 | Stand: November 2025

---

## Inhaltsverzeichnis

1. [Was ist Goldsmith ERP?](#was-ist-goldsmith-erp)
2. [Systemvoraussetzungen](#systemvoraussetzungen)
3. [Zugriff auf das System](#zugriff-auf-das-system)
4. [Erste Anmeldung](#erste-anmeldung)
5. [Benutzerrollen verstehen](#benutzerrollen-verstehen)
6. [Dashboard-Übersicht](#dashboard-übersicht)
7. [Navigation](#navigation)
8. [Ihr Benutzerprofil einrichten](#ihr-benutzerprofil-einrichten)
9. [Test-Zugangsdaten](#test-zugangsdaten)
10. [Nächste Schritte](#nächste-schritte)

---

## Was ist Goldsmith ERP?

Goldsmith ERP ist ein modernes Verwaltungssystem speziell für Goldschmiedebetriebe. Es hilft Ihnen bei der:

- **Auftragsverwaltung**: Kundenaufträge erfassen, verfolgen und abschließen
- **Materialverwaltung**: Edelmetalle und Edelsteine im Blick behalten
- **Zeiterfassung**: Arbeitszeiten pro Auftrag dokumentieren
- **Kundenverwaltung**: Kundeninformationen und -historie pflegen
- **Berichtswesen**: Übersicht über Aufträge, Materialverbrauch und Arbeitszeiten

### Vorteile

✅ **Zentrale Datenverwaltung** - Alle Informationen an einem Ort
✅ **Zeitersparnis** - Schneller Zugriff auf Aufträge und Materialien
✅ **Transparenz** - Nachvollziehbare Arbeitszeiten und Kosten
✅ **Teamarbeit** - Mehrere Mitarbeiter können gleichzeitig arbeiten
✅ **Rechtssicherheit** - Lückenlose Dokumentation

---

## Systemvoraussetzungen

### Hardware

- Computer, Tablet oder Smartphone
- Internetzugang (empfohlen: schnelle Verbindung)
- Optional: QR/NFC-Scanner für Zeiterfassung

### Software

**Empfohlene Browser**:
- Google Chrome (Version 100+)
- Mozilla Firefox (Version 100+)
- Safari (Version 15+)
- Microsoft Edge (Version 100+)

**Nicht unterstützt**:
- Internet Explorer

> **Tipp**: Aktualisieren Sie Ihren Browser regelmäßig für beste Leistung und Sicherheit.

---

## Zugriff auf das System

### URL

Das Goldsmith ERP ist über folgende Adresse erreichbar:

```
http://localhost:3000
```

oder (wenn vom Administrator konfiguriert):

```
https://ihr-firmenname.goldsmith-erp.de
```

> **Hinweis**: Die genaue URL erhalten Sie von Ihrem Systemadministrator.

### Lesezeichen setzen

Speichern Sie die URL als Lesezeichen in Ihrem Browser:
1. Öffnen Sie die Goldsmith ERP-URL
2. Drücken Sie `Strg+D` (Windows) oder `Cmd+D` (Mac)
3. Vergeben Sie einen Namen wie "Goldsmith ERP"

---

## Erste Anmeldung

### Schritt 1: Login-Seite öffnen

Öffnen Sie die Goldsmith ERP-URL in Ihrem Browser.

`[Screenshot: Login-Seite mit E-Mail- und Passwort-Feldern]`

### Schritt 2: Zugangsdaten eingeben

Geben Sie Ihre Zugangsdaten ein:
- **E-Mail-Adresse**: Die von Ihrem Administrator zugewiesene E-Mail
- **Passwort**: Ihr persönliches Passwort

> **Wichtig**: Zugangsdaten sind personengebunden und dürfen nicht weitergegeben werden!

### Schritt 3: Anmelden

Klicken Sie auf **"Anmelden"**.

### Was passiert beim ersten Login?

Nach dem ersten Login sollten Sie:
1. ✅ Ihr Passwort ändern (siehe [Ihr Benutzerprofil einrichten](#ihr-benutzerprofil-einrichten))
2. ✅ Ihre Profildaten überprüfen (Name, E-Mail)
3. ✅ Die Systemoberfläche kennenlernen

---

## Benutzerrollen verstehen

Goldsmith ERP arbeitet mit einem **Rollenbasierten Berechtigungssystem (RBAC)**. Es gibt drei Rollen:

### 1. 👑 Admin (Administrator)

**Vollzugriff auf alle Funktionen**

- Kann alles erstellen, bearbeiten und löschen
- Verwaltet Benutzerkonten
- Konfiguriert Systemeinstellungen
- Sieht alle Berichte und Auswertungen

**Typisch für**: Geschäftsinhaber, IT-Verantwortliche

---

### 2. 🔨 Goldsmith (Goldschmied)

**Zugriff auf tägliche Arbeitsfunktionen**

Kann:
- ✅ Aufträge ansehen, erstellen und bearbeiten
- ✅ Materialien ansehen und Bestand anpassen
- ✅ Arbeitszeiten erfassen (eigene)
- ✅ Aktivitäten erstellen
- ✅ Kunden ansehen und pflegen
- ✅ Berichte ansehen

Kann nicht:
- ❌ Aufträge löschen
- ❌ Benutzer verwalten
- ❌ Materialien erstellen oder löschen
- ❌ Systemkonfiguration ändern

**Typisch für**: Mitarbeiter in der Werkstatt, ausführende Goldschmiede

---

### 3. 👁️ Viewer (Betrachter)

**Nur-Lese-Zugriff**

Kann:
- ✅ Aufträge ansehen
- ✅ Materialien ansehen
- ✅ Eigene Arbeitszeiten ansehen
- ✅ Kunden ansehen
- ✅ Berichte ansehen

Kann nicht:
- ❌ Nichts erstellen, bearbeiten oder löschen
- ❌ Keine Arbeitszeiten erfassen
- ❌ Keine Bestandsänderungen

**Typisch für**: Praktikanten, externe Berater, Buchhaltung

---

### Ihre Rolle prüfen

So sehen Sie Ihre aktuelle Rolle:
1. Klicken Sie rechts oben auf Ihren Namen
2. Im Dropdown-Menü steht Ihre Rolle (z.B. "Rolle: Goldsmith")

`[Screenshot: User-Menü mit Rollen-Anzeige]`

> **Weitere Informationen**: Details zu allen Berechtigungen finden Sie in [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

---

## Dashboard-Übersicht

Nach dem Login sehen Sie das **Dashboard** - Ihre zentrale Arbeitsoberfläche.

`[Screenshot: Dashboard mit Hauptbereichen markiert]`

### Hauptbereiche

1. **Kopfzeile** (oben)
   - Logo und Firmennamen
   - Hauptnavigation (Aufträge, Materialien, Zeiterfassung, etc.)
   - Benutzerprofil-Menü (rechts oben)

2. **Haupt-Inhaltsbereich** (Mitte)
   - Hier werden Ihre Arbeitsinhalte angezeigt
   - Listen, Formulare, Details

3. **Statusleiste** (unten, falls vorhanden)
   - Systemmeldungen
   - Laufende Zeiterfassung

---

## Navigation

### Hauptmenü

Das Hauptmenü befindet sich in der Kopfzeile:

| Menüpunkt | Beschreibung |
|-----------|--------------|
| **Aufträge** | Auftragsliste, neue Aufträge erstellen |
| **Materialien** | Materialbestand, Lagerübersicht |
| **Zeiterfassung** | Zeit starten/stoppen, Zeitübersicht |
| **Kunden** | Kundenliste, Kundenprofile |
| **Benutzer** | Benutzerverwaltung (nur für Admins) |
| **Berichte** | Auswertungen und Statistiken |

`[Screenshot: Hauptmenü mit allen Optionen]`

### Navigation-Tipps

**Breadcrumbs** (Brotkrümel-Navigation):
- Zeigt Ihren aktuellen Standort im System
- Beispiel: `Aufträge > Auftrag #42 > Details`
- Klicken Sie auf einen Eintrag, um zurückzuspringen

**Zurück-Button**:
- Jede Detailseite hat einen "Zurück"-Button
- Bringt Sie zur vorherigen Listenansicht

**Tab-Memory-System**:
- Das System merkt sich, welchen Tab Sie zuletzt geöffnet hatten
- Beim nächsten Besuch landen Sie automatisch dort

---

## Ihr Benutzerprofil einrichten

### Profil aufrufen

1. Klicken Sie rechts oben auf Ihren Namen
2. Wählen Sie **"Profil"** oder **"Einstellungen"**

`[Screenshot: Profil-Menü]`

### Profildaten überprüfen

Überprüfen Sie folgende Daten:
- ✅ Vorname und Nachname
- ✅ E-Mail-Adresse
- ✅ Rolle (nur lesbar, wird von Admin vergeben)

### Passwort ändern

So ändern Sie Ihr Passwort:

1. Gehen Sie zu **Profil > Passwort ändern**
2. Geben Sie Ihr **aktuelles Passwort** ein
3. Geben Sie Ihr **neues Passwort** ein (mindestens 8 Zeichen)
4. Bestätigen Sie das neue Passwort
5. Klicken Sie auf **"Speichern"**

**Sichere Passwörter**:
- Mindestens 8 Zeichen
- Kombination aus Buchstaben, Zahlen und Sonderzeichen
- Keine persönlichen Informationen (Geburtsdatum, Name)
- Nicht mit anderen Accounts teilen

---

## Test-Zugangsdaten

Für Schulungszwecke und Tests stehen folgende Benutzerkonten bereit:

### Admin-Zugang (voller Zugriff)
```
E-Mail: admin@goldsmith.local
Passwort: admin123
Rolle: Admin
```

### Goldsmith-Zugang (Werkstatt-Mitarbeiter)
```
E-Mail: goldsmith@goldsmith.local
Passwort: goldsmith123
Rolle: Goldsmith
```

### Viewer-Zugang (Nur-Lese-Zugriff)
```
E-Mail: viewer@goldsmith.local
Passwort: viewer123
Rolle: Viewer
```

> **Hinweis**: Diese Test-Accounts sollten nur zu Übungszwecken verwendet werden. Ändern Sie die Passwörter, wenn Sie das System produktiv einsetzen!

> **Wichtig**: In einer Produktivumgebung erhalten Sie persönliche Zugangsdaten von Ihrem Administrator.

---

## Nächste Schritte

Nachdem Sie sich erfolgreich angemeldet haben, empfehlen wir:

### 1. Berechtigungen verstehen
📖 Lesen Sie: [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)
- Detaillierte Übersicht aller Rollen
- Was Sie mit Ihrer Rolle tun können

### 2. Aufträge kennenlernen
📖 Lesen Sie: [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)
- Aufträge erstellen und verwalten
- Materialien zuordnen
- Status-Workflow verstehen

### 3. Zeiterfassung lernen
📖 Lesen Sie: [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md)
- Arbeitszeit starten und stoppen
- Aktivitäten auswählen
- Zeitberichte ansehen

### 4. Tägliche Workflows
📖 Lesen Sie: [DAILY_WORKFLOWS.md](DAILY_WORKFLOWS.md)
- Morgenroutine
- Typische Arbeitsabläufe
- Best Practices

---

## Probleme?

Falls Sie Schwierigkeiten beim Anmelden oder der ersten Nutzung haben:

📖 **Lesen Sie**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
📖 **Häufige Fragen**: [FAQ.md](FAQ.md)

**Kontakt**:
- Wenden Sie sich an Ihren Systemadministrator
- E-Mail: [admin-email@ihre-firma.de]
- Telefon: [+49 XXX XXXXXXX]

---

## Zusammenfassung

✅ Sie wissen jetzt, was Goldsmith ERP ist
✅ Sie können sich anmelden
✅ Sie verstehen die drei Benutzerrollen
✅ Sie kennen die Hauptnavigation
✅ Sie können Ihr Profil bearbeiten

**Viel Erfolg bei der Nutzung von Goldsmith ERP!** 🔨✨

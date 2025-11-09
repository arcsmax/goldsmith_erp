# Goldsmith ERP - Häufig gestellte Fragen (FAQ)

**Schnelle Antworten auf häufige Fragen**
Version 1.0 | Stand: November 2025

---

## Inhalt

1. [Allgemeine Fragen](#allgemeine-fragen)
2. [Account & Login](#account--login)
3. [Rollen & Berechtigungen](#rollen--berechtigungen)
4. [Aufträge](#aufträge)
5. [Materialien](#materialien)
6. [Zeiterfassung](#zeiterfassung)
7. [Kunden](#kunden)
8. [Technische Fragen](#technische-fragen)

---

## Allgemeine Fragen

### Was ist Goldsmith ERP?

**Antwort**: Goldsmith ERP ist ein spezialisiertes ERP-System für moderne Goldschmied-Betriebe. Es hilft Ihnen bei:
- Auftragsverwaltung
- Materialverwaltung
- Zeiterfassung
- Kundenverwaltung

Siehe: [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md)

---

### Für wen ist Goldsmith ERP gedacht?

**Antwort**: Für **Goldschmied-Werkstätten** jeder Größe:
- Einzelunternehmer
- Kleine Werkstätten (2-5 Mitarbeiter)
- Mittlere Betriebe (5-20 Mitarbeiter)

**Typische Nutzer**:
- Goldschmiede
- Werkstatt-Mitarbeiter
- Geschäftsführer
- Verwaltungs-Personal

---

### Kostet Goldsmith ERP etwas?

**Antwort**: Goldsmith ERP ist ein **Open-Source-Projekt**. Kosten fallen an für:
- Hosting (Server)
- Installation und Einrichtung
- Support (optional)

Für Details kontaktieren Sie Ihren Administrator.

---

### Kann ich Goldsmith ERP mobil nutzen?

**Antwort**: **Ja**, über den Browser Ihres Smartphones oder Tablets.

**Unterstützte Geräte**:
- ✅ Smartphones (iOS, Android)
- ✅ Tablets (iOS, Android)
- ✅ Desktop (Windows, macOS, Linux)

**Browser**:
- Chrome, Firefox, Safari, Edge (aktuelle Versionen)

**Hinweis**: Eine native App gibt es derzeit nicht, aber die Web-Version ist mobil-optimiert.

---

### Gibt es eine Demo-Version?

**Antwort**: **Ja**, nutzen Sie die Test-Accounts:

```
Admin: admin@goldsmith.local / admin123
Goldsmith: goldsmith@goldsmith.local / goldsmith123
Viewer: viewer@goldsmith.local / viewer123
```

Siehe: [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md)

---

## Account & Login

### Wie registriere ich mich?

**Antwort**: **Zwei Möglichkeiten**:

**Option 1: Selbstregistrierung**
1. Gehen Sie zur Login-Seite
2. Klicken Sie auf "Registrieren"
3. Geben Sie E-Mail und Passwort ein

**Option 2: Admin erstellt Account**
- Ihr Admin legt einen Account für Sie an
- Sie erhalten Ihre Zugangsdaten

Siehe: [FEATURE_USER_MANAGEMENT.md](FEATURE_USER_MANAGEMENT.md)

---

### Ich habe mein Passwort vergessen. Was tun?

**Antwort**:
1. Klicken Sie auf "Passwort vergessen?" (falls verfügbar)
2. Oder: Kontaktieren Sie einen **Admin**
3. Admin kann Ihr Passwort zurücksetzen

**Hinweis**: Aus Sicherheitsgründen können Passwörter nicht angezeigt, nur zurückgesetzt werden.

---

### Wie ändere ich mein Passwort?

**Antwort**:
1. Klicken Sie oben rechts auf Ihr **Profil**
2. Wählen Sie "Passwort ändern"
3. Geben Sie altes und neues Passwort ein
4. Klicken Sie auf "Speichern"

**Passwort-Anforderungen**: Mind. 8 Zeichen, eine Zahl, ein Buchstabe

---

### Warum kann ich mich nicht einloggen?

**Mögliche Ursachen**:
- Falsches Passwort
- Account ist deaktiviert
- E-Mail falsch geschrieben
- Caps Lock aktiviert

**Lösung**: Siehe [TROUBLESHOOTING.md - Login-Probleme](TROUBLESHOOTING.md#login-probleme)

---

### Wie lange bleibe ich eingeloggt?

**Antwort**: **7 Tage** (Standard).

Nach 7 Tagen Inaktivität müssen Sie sich neu anmelden.

**Hinweis**: Aus Sicherheitsgründen ist die Session-Dauer begrenzt.

---

## Rollen & Berechtigungen

### Welche Rollen gibt es?

**Antwort**: **3 Rollen**:

| Rolle | Symbol | Beschreibung |
|-------|--------|--------------|
| **Admin** | 👑 | Voller Zugriff, kann alles |
| **Goldsmith** | 🔨 | Werkstatt-Zugriff, kann Aufträge und Zeit tracken |
| **Viewer** | 👁️ | Nur-Lese-Zugriff, kann nur ansehen |

Siehe: [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

---

### Welche Rolle habe ich?

**Antwort**:
1. Klicken Sie oben rechts auf Ihr **Profil**
2. Ihre Rolle wird angezeigt (z.B. "Rolle: Goldsmith")

---

### Kann ich meine Rolle selbst ändern?

**Antwort**: **Nein**. Nur Admins können Rollen zuweisen.

Kontaktieren Sie einen Admin, falls Sie mehr Berechtigungen brauchen.

---

### Warum bekomme ich "403 Forbidden"-Fehler?

**Antwort**: Ihre Rolle hat nicht die nötigen Berechtigungen.

**Beispiel**: Viewer dürfen keine Aufträge erstellen.

**Lösung**:
- Prüfen Sie Ihre Rolle
- Kontaktieren Sie einen Admin
- Siehe: [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

---

## Aufträge

### Wie erstelle ich einen neuen Auftrag?

**Antwort**:
1. Klicken Sie auf "Aufträge" → "Neuer Auftrag"
2. Geben Sie Titel, Kunde, Beschreibung ein
3. Wählen Sie Abgabedatum
4. Klicken Sie auf "Auftrag erstellen"

**Wer darf Aufträge erstellen?**
- ✅ Admin
- ✅ Goldsmith
- ❌ Viewer

Siehe: [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)

---

### Wie ändere ich den Status eines Auftrags?

**Antwort**:
1. Öffnen Sie den Auftrag
2. Wählen Sie neuen Status:
   - 🟡 Pending (Ausstehend)
   - 🔵 In Progress (In Bearbeitung)
   - 🟢 Completed (Fertiggestellt)
3. Klicken Sie auf "Speichern"

---

### Kann ich Aufträge löschen?

**Antwort**: **Nur Admins** dürfen Aufträge löschen.

**Hinweis**: Seien Sie vorsichtig beim Löschen! Gelöschte Aufträge können nicht wiederhergestellt werden.

---

### Wie füge ich Materialien zu einem Auftrag hinzu?

**Antwort**:
1. Öffnen Sie den Auftrag
2. Gehen Sie zum Tab "Materialien"
3. Klicken Sie auf "Material hinzufügen"
4. Wählen Sie Material und Menge
5. Klicken Sie auf "Hinzufügen"

**Wichtig**: Der Materialbestand wird **automatisch reduziert**.

Siehe: [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)

---

### Wie lade ich Fotos zu einem Auftrag hoch?

**Antwort**:
1. Öffnen Sie den Auftrag
2. Gehen Sie zum Tab "Fotos"
3. Klicken Sie auf "Foto hochladen"
4. Wählen Sie Foto (max. 5 MB)
5. Klicken Sie auf "Hochladen"

**Empfohlen**: JPG oder PNG, max. 5 MB pro Foto.

---

## Materialien

### Wie erstelle ich ein neues Material?

**Antwort**: **Nur Admins** dürfen Materialien erstellen.

1. Klicken Sie auf "Materialien" → "Neues Material"
2. Geben Sie Name, Typ, Einheit, Bestand ein
3. Klicken Sie auf "Material erstellen"

Siehe: [FEATURE_MATERIAL_MANAGEMENT.md](FEATURE_MATERIAL_MANAGEMENT.md)

---

### Wie ändere ich den Material-Bestand?

**Antwort**:
1. Öffnen Sie die Materialliste
2. Klicken Sie auf das Material
3. Klicken Sie auf "Bestand anpassen"
4. Wählen Sie Operation:
   - **Hinzufügen (+)**: Nachschub erhalten
   - **Abziehen (-)**: Materialverbrauch
5. Geben Sie Menge ein
6. Klicken Sie auf "Speichern"

**Hinweis**: Beim Zuordnen zu Aufträgen wird der Bestand **automatisch reduziert**.

---

### Was bedeutet die rote Markierung bei Materialien?

**Antwort**: **Low Stock Alert** - Der Bestand ist unter dem Mindestbestand.

**Lösung**:
- Bestellen Sie Nachschub
- Oder: Passen Sie den Mindestbestand an

**Hinweis**: Dies ist nur eine Warnung, keine Fehlermeldung.

---

### Welche Material-Typen gibt es?

**Antwort**: **Zwei Haupttypen**:

1. **Edelmetalle** (Precious Metals):
   - Gold, Silber, Platin, Palladium
   - Einheit: Gramm (g)

2. **Edelsteine** (Gemstones):
   - Diamanten, Rubine, Smaragde, Saphire
   - Einheit: Karat (ct) oder Stück (pcs)

---

## Zeiterfassung

### Wie starte ich die Zeiterfassung?

**Antwort**:
1. Öffnen Sie einen Auftrag
2. Gehen Sie zum Tab "Zeiteinträge"
3. Klicken Sie auf "Zeit starten"
4. Wählen Sie Aktivität (z.B. "Sägen", "Löten")
5. Arbeiten Sie am Auftrag
6. Klicken Sie auf "Zeit stoppen"

**Hinweis**: Die UI wird in Woche 2-3 fertiggestellt. Das Backend funktioniert bereits.

Siehe: [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md)

---

### Welche Aktivitäten gibt es?

**Antwort**: **15 Standard-Aktivitäten** in 3 Kategorien:

**Fertigung**:
- Sägen, Feilen, Bohren, Löten, Polieren, usw.

**Verwaltung**:
- Material beschaffen, Kundengespräch, Dokumentation

**Warten**:
- Warten auf Material, Warten auf Kunde

Siehe: [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md)

---

### Kann ich meine Zeit nachträglich ändern?

**Antwort**: **Ja**, aber nur Admins dürfen Zeiteinträge bearbeiten.

Goldsmiths können nur ihre eigenen Zeiteinträge ansehen, nicht bearbeiten.

---

### Wer kann alle Zeiteinträge sehen?

**Antwort**: **Nur Admins**.

- Admins sehen alle Zeiteinträge
- Goldsmiths sehen nur ihre eigenen
- Viewers sehen nur ihre eigenen

---

## Kunden

### Wie erstelle ich einen neuen Kunden?

**Antwort**:
1. Klicken Sie auf "Kunden" → "Neuer Kunde"
2. Geben Sie Vor- und Nachname ein (Pflicht)
3. Optional: E-Mail, Telefon, Adresse
4. Klicken Sie auf "Kunde erstellen"

**Wer darf Kunden erstellen?**
- ✅ Admin
- ✅ Goldsmith
- ❌ Viewer

Siehe: [FEATURE_CUSTOMER_MANAGEMENT.md](FEATURE_CUSTOMER_MANAGEMENT.md)

---

### Wie sehe ich alle Aufträge eines Kunden?

**Antwort**:
1. Öffnen Sie die Kundenliste
2. Klicken Sie auf den Kunden
3. Sie sehen die **Kundenhistorie** mit allen Aufträgen

**Vorteile**:
- Schneller Überblick
- Stammkunden erkennen
- Nachvollziehbarkeit

---

### Kann ich Kunden löschen?

**Antwort**: **Nur Admins** dürfen Kunden löschen.

**Hinweis**: Seien Sie vorsichtig! Gelöschte Kunden können nicht wiederhergestellt werden.

---

## Technische Fragen

### Welche Browser werden unterstützt?

**Antwort**:
- ✅ Google Chrome 100+
- ✅ Mozilla Firefox 100+
- ✅ Safari 15+
- ✅ Microsoft Edge 100+
- ❌ Internet Explorer (nicht unterstützt!)

**Empfehlung**: Nutzen Sie immer die **neueste Browser-Version**.

---

### Funktioniert Goldsmith ERP offline?

**Antwort**: **Nein**, eine Internet-Verbindung ist erforderlich.

**Grund**: Goldsmith ERP ist eine Web-Anwendung, die auf einem Server läuft.

**Tipp**: Nutzen Sie eine **stabile Internet-Verbindung** (WLAN empfohlen).

---

### Sind meine Daten sicher?

**Antwort**: **Ja**, Goldsmith ERP nutzt:
- ✅ **HTTPS** (verschlüsselte Verbindung)
- ✅ **JWT-Tokens** (sichere Authentifizierung)
- ✅ **Passwort-Hashing** (Passwörter nie im Klartext)
- ✅ **Input-Validierung** (SQL-Injection-Schutz)
- ✅ **RBAC** (Rollbasierte Zugriffskontrolle)

Siehe: [ARCHITECTURE_REVIEW.md](../ARCHITECTURE_REVIEW.md) für Details.

---

### Kann ich Daten exportieren?

**Antwort**: **Derzeit nicht direkt**, aber:

**Für Admins/IT**:
- Datenbank-Export über PostgreSQL
- API-Zugriff für Skripte

**Geplante Features**:
- CSV-Export für Aufträge
- Excel-Export für Berichte
- PDF-Reports

Kontaktieren Sie Ihren Admin für einen Datenbank-Export.

---

### Gibt es eine API?

**Antwort**: **Ja**, Goldsmith ERP hat eine **RESTful API** (FastAPI).

**API-Dokumentation**: http://localhost:8000/docs (Swagger UI)

**Für Entwickler**:
- Siehe: [README.md](../README.md)
- Siehe: [CLAUDE.md](../CLAUDE.md)

---

### Wo finde ich die Server-Logs?

**Antwort**: **Nur für Admins/IT**:

```bash
make logs-backend
# Oder
podman-compose logs -f backend
```

Siehe: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

### Wie kann ich helfen / mitwirken?

**Antwort**: Goldsmith ERP ist **Open Source**!

**Möglichkeiten**:
- 🐛 Bugs melden (GitHub Issues)
- 💡 Features vorschlagen
- 💻 Code beitragen (Pull Requests)
- 📝 Dokumentation verbessern
- 🌍 Übersetzungen erstellen

**GitHub**: https://github.com/[repo]/goldsmith_erp

---

## Weitere Hilfe

### Wo finde ich mehr Dokumentation?

**Antwort**: Lesen Sie die **Feature-Guides**:

| Dokument | Inhalt |
|----------|--------|
| [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md) | Erste Schritte, Login, Rollen |
| [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md) | Rollen und Berechtigungen |
| [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md) | Aufträge verwalten |
| [FEATURE_MATERIAL_MANAGEMENT.md](FEATURE_MATERIAL_MANAGEMENT.md) | Materialien verwalten |
| [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md) | Zeit tracken |
| [FEATURE_CUSTOMER_MANAGEMENT.md](FEATURE_CUSTOMER_MANAGEMENT.md) | Kunden verwalten |
| [FEATURE_USER_MANAGEMENT.md](FEATURE_USER_MANAGEMENT.md) | Benutzer verwalten |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Probleme lösen |

---

### Ich habe eine Frage, die hier nicht beantwortet wird.

**Antwort**:
1. Lesen Sie die **Dokumentation** (siehe oben)
2. Schauen Sie in [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
3. Kontaktieren Sie Ihren **Admin**
4. Kontaktieren Sie den **Support**

---

## Zusammenfassung

✅ **Goldsmith ERP** ist ein Open-Source ERP für Goldschmiede
✅ **3 Rollen**: Admin (voller Zugriff), Goldsmith (Werkstatt), Viewer (nur lesen)
✅ **Hauptfunktionen**: Aufträge, Materialien, Zeiterfassung, Kunden
✅ **Browser**: Chrome, Firefox, Safari, Edge (aktuelle Versionen)
✅ **Test-Accounts** verfügbar (siehe [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md))

---

**Noch Fragen? Lesen Sie die Dokumentation oder kontaktieren Sie Support!** 📚✨

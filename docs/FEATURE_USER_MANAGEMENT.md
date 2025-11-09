# Goldsmith ERP - Benutzerverwaltung

**Benutzer-Accounts verwalten und Rollen zuweisen**
Version 1.0 | Stand: November 2025

---

## Überblick

Die **Benutzerverwaltung** ermöglicht Admins, Benutzer-Accounts zu erstellen, Rollen zuzuweisen und Benutzer zu aktivieren/deaktivieren.

### Hauptfunktionen

- 👥 **Benutzerliste** - Alle Benutzer auf einen Blick
- ➕ **Benutzer anlegen** - Neue Accounts erstellen (Admin-Funktion)
- 🔐 **Selbstregistrierung** - Benutzer registrieren sich selbst
- ✏️ **Profil bearbeiten** - Eigene Daten ändern
- 🔄 **Rolle zuweisen** - Admin weist Rollen zu
- 🚫 **Benutzer deaktivieren** - Account sperren (Soft Delete)
- ✅ **Benutzer aktivieren** - Gesperrten Account reaktivieren

---

## Zwei Arten der Benutzer-Erstellung

### Option 1: Selbstregistrierung (Öffentlich)

**Ohne Login möglich** - Jeder kann sich registrieren.

1. Gehen Sie zur Login-Seite
2. Klicken Sie auf **"Registrieren"** oder **"Account erstellen"**
3. Geben Sie Ihre Daten ein:
   - **E-Mail** (Pflicht, muss eindeutig sein)
   - **Passwort** (Pflicht, siehe Passwortanforderungen)
   - **Vorname** (optional)
   - **Nachname** (optional)
4. Klicken Sie auf **"Registrieren"**

**Ergebnis**:
- Neuer Account wird erstellt
- Standard-Rolle: **Viewer** (Nur-Lese-Zugriff)
- Admin muss Rolle später ändern, falls nötig

**Beispiel**:
```
E-Mail: neuer.mitarbeiter@goldsmith.local
Passwort: sicheres123
Vorname: Max
Nachname: Mustermann
→ Account wird mit Rolle "Viewer" erstellt
```

---

### Option 2: Admin erstellt Benutzer

**Nur Admins** können Benutzer für andere anlegen.

1. Klicken Sie im Hauptmenü auf **"Benutzer"**
2. Klicken Sie auf **"Neuer Benutzer"** oder **"+ Benutzer"**
3. Geben Sie die Benutzerdaten ein:
   - **E-Mail** (Pflicht)
   - **Passwort** (Pflicht)
   - **Vorname** (optional)
   - **Nachname** (optional)
   - **Rolle** (Admin / Goldsmith / Viewer)
4. Klicken Sie auf **"Benutzer erstellen"**

**Vorteile**:
- Admin kann **Rolle direkt zuweisen**
- Kein zusätzlicher Schritt nötig
- Kontrolle über neue Accounts

---

## Passwortanforderungen

### Regeln für sichere Passwörter

✅ **Erforderlich**:
- Mindestens **8 Zeichen**
- Mindestens **eine Zahl**
- Mindestens **ein Buchstabe**

❌ **Nicht erlaubt**:
- Weniger als 8 Zeichen
- Nur Zahlen (z.B. "12345678")
- Nur Buchstaben (z.B. "abcdefgh")

**Gute Passwort-Beispiele**:
```
✅ sicheres123
✅ Goldsmith2025
✅ MeinPasswort1
```

**Schlechte Passwort-Beispiele**:
```
❌ pass123 (zu kurz)
❌ 12345678 (keine Buchstaben)
❌ abcdefgh (keine Zahlen)
```

**Hinweis**: Passwörter werden **gehashed** gespeichert (sicher).

---

## Benutzerliste ansehen

### Wer darf die Benutzerliste sehen?

- ✅ **Admins**: Ja
- ❌ **Goldsmiths**: Nein
- ❌ **Viewers**: Nein

### Schritt-für-Schritt

1. Klicken Sie im Hauptmenü auf **"Benutzer"**
2. Sie sehen die **Benutzerliste**

### Angezeigte Informationen

| Spalte | Beschreibung |
|--------|--------------|
| **ID** | Benutzer-ID |
| **E-Mail** | E-Mail-Adresse |
| **Name** | Vor- und Nachname |
| **Rolle** | Admin / Goldsmith / Viewer |
| **Status** | Aktiv / Deaktiviert |
| **Erstellt** | Erstellungsdatum |

---

## Rolle zuweisen oder ändern

### Wer darf Rollen ändern?

- ✅ **Admins**: Ja
- ❌ **Goldsmiths**: Nein
- ❌ **Viewers**: Nein

### Schritt-für-Schritt

1. Öffnen Sie die **Benutzerliste**
2. Klicken Sie auf den gewünschten Benutzer
3. Klicken Sie auf **"Bearbeiten"**
4. Wählen Sie die neue **Rolle**:
   - **Admin** 👑 - Voller Zugriff
   - **Goldsmith** 🔨 - Werkstatt-Zugriff
   - **Viewer** 👁️ - Nur-Lese-Zugriff
5. Klicken Sie auf **"Speichern"**

**Beispiel**:
```
Benutzer: max.mustermann@goldsmith.local
Alte Rolle: Viewer
Neue Rolle: Goldsmith
→ Max kann jetzt Aufträge erstellen und Zeit tracken
```

**Siehe auch**: [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md) für Details zu Rollen und Berechtigungen.

---

## Benutzer deaktivieren

### Was bedeutet "Deaktivieren"?

- ✅ Account wird **gesperrt** (Soft Delete)
- ✅ Daten bleiben **erhalten**
- ✅ Benutzer kann sich **nicht einloggen**
- ✅ Kann später **reaktiviert** werden

**Unterschied zu "Löschen"**:
- Deaktivieren = **Temporär sperren** (reversibel)
- Löschen = **Permanent entfernen** (nicht implementiert)

### Wer darf Benutzer deaktivieren?

- ✅ **Admins**: Ja
- ❌ **Goldsmiths**: Nein
- ❌ **Viewers**: Nein

### Schritt-für-Schritt

1. Öffnen Sie die **Benutzerliste**
2. Klicken Sie auf den Benutzer
3. Klicken Sie auf **"Deaktivieren"**
4. Bestätigen Sie die Aktion

**Ergebnis**:
- Status wird auf **"Deaktiviert"** gesetzt
- Benutzer kann sich nicht mehr einloggen
- Daten (Aufträge, Zeiteinträge) bleiben erhalten

**Wann deaktivieren?**
- Mitarbeiter hat gekündigt
- Account wird nicht mehr benötigt
- Sicherheitsvorfall (Account kompromittiert)

---

## Benutzer aktivieren

### Wer darf Benutzer aktivieren?

- ✅ **Admins**: Ja
- ❌ **Goldsmiths**: Nein
- ❌ **Viewers**: Nein

### Schritt-für-Schritt

1. Öffnen Sie die **Benutzerliste**
2. Klicken Sie auf den deaktivierten Benutzer
3. Klicken Sie auf **"Aktivieren"**
4. Bestätigen Sie die Aktion

**Ergebnis**:
- Status wird auf **"Aktiv"** gesetzt
- Benutzer kann sich wieder einloggen

---

## Eigenes Profil bearbeiten

**Jeder Benutzer** kann sein eigenes Profil bearbeiten.

### Was kann ich ändern?

- ✅ **E-Mail** (muss eindeutig sein)
- ✅ **Vorname**
- ✅ **Nachname**
- ✅ **Passwort**

### Schritt-für-Schritt

1. Klicken Sie oben rechts auf Ihr **Profil-Symbol**
2. Wählen Sie **"Profil bearbeiten"**
3. Ändern Sie die gewünschten Felder
4. Klicken Sie auf **"Speichern"**

**Beispiel - E-Mail ändern**:
```
Alte E-Mail: max@example.com
Neue E-Mail: max.mustermann@goldsmith.local
→ Neue E-Mail wird gespeichert
```

**Siehe auch**: [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md) für Details zur Profil-Verwaltung.

---

## Passwort ändern

### Eigenes Passwort ändern

1. Öffnen Sie Ihr **Profil**
2. Klicken Sie auf **"Passwort ändern"**
3. Geben Sie ein:
   - Altes Passwort
   - Neues Passwort (mind. 8 Zeichen, eine Zahl, ein Buchstabe)
   - Neues Passwort bestätigen
4. Klicken Sie auf **"Passwort speichern"**

### Passwort zurücksetzen (Admin)

**Admins** können Passwörter für andere Benutzer zurücksetzen:

1. Öffnen Sie die **Benutzerliste**
2. Klicken Sie auf den Benutzer
3. Klicken Sie auf **"Bearbeiten"**
4. Geben Sie ein **neues Passwort** ein
5. Klicken Sie auf **"Speichern"**

**Hinweis**: Der Benutzer sollte das Passwort nach dem ersten Login ändern.

---

## Berechtigungen

| Aktion | Admin | Goldsmith | Viewer |
|--------|-------|-----------|--------|
| Eigenes Profil ansehen | ✅ | ✅ | ✅ |
| Eigenes Profil bearbeiten | ✅ | ✅ | ✅ |
| Eigenes Passwort ändern | ✅ | ✅ | ✅ |
| Benutzerliste ansehen | ✅ | ❌ | ❌ |
| Benutzer erstellen | ✅ | ❌ | ❌ |
| Benutzer bearbeiten | ✅ | ❌ | ❌ |
| Rolle zuweisen | ✅ | ❌ | ❌ |
| Benutzer deaktivieren | ✅ | ❌ | ❌ |
| Benutzer aktivieren | ✅ | ❌ | ❌ |
| Passwort zurücksetzen | ✅ | ❌ | ❌ |

---

## Best Practices

### Rollen sinnvoll zuweisen

✅ **Gut**:
- **Admin**: Nur Geschäftsführer oder IT-Verantwortliche
- **Goldsmith**: Werkstatt-Mitarbeiter
- **Viewer**: Aushilfen, externe Partner

❌ **Schlecht**:
- Alle Benutzer als Admin
- Rolle "Viewer" für Werkstatt-Mitarbeiter

**Regel**: Prinzip der minimalen Rechte!

---

### Inaktive Accounts deaktivieren

✅ **Gut**:
- Ehemalige Mitarbeiter sofort deaktivieren
- Nicht mehr benötigte Accounts sperren

❌ **Schlecht**:
- Alte Accounts aktiv lassen
- Passwörter teilen

**Regel**: Regelmäßig Benutzerliste prüfen!

---

### Sichere Passwörter verwenden

✅ **Gut**:
- Mindestens 8 Zeichen
- Buchstaben + Zahlen
- Nicht wiederverwendbar

❌ **Schlecht**:
- "password123"
- Gleiches Passwort wie E-Mail

**Regel**: Passwort-Manager verwenden!

---

### E-Mail-Adressen eindeutig halten

✅ **Gut**:
- Eine E-Mail = ein Account
- Eindeutige E-Mail-Adressen verwenden

❌ **Schlecht**:
- Gleiche E-Mail für mehrere Accounts
- E-Mail ändern, die schon existiert

**Regel**: System prüft Eindeutigkeit automatisch!

---

## Fehlerbehebung

### Problem: "Email already registered"

**Ursache**: E-Mail-Adresse wird bereits verwendet.

**Lösung**:
1. Andere E-Mail-Adresse verwenden
2. Oder: Bestehenden Account reaktivieren

---

### Problem: "Password must contain at least one number"

**Ursache**: Passwort enthält keine Zahl.

**Lösung**:
- Fügen Sie mindestens eine Zahl hinzu
- Beispiel: "sicheres123" statt "sicheres"

---

### Problem: Kann Benutzerliste nicht sehen

**Ursache**: Nur Admins dürfen Benutzerliste sehen.

**Lösung**:
- Fragen Sie einen Admin, Ihre Rolle zu ändern
- Oder: Nutzen Sie Ihr eigenes Profil (Menu → Profil)

---

## Zusammenfassung

✅ **Zwei Wege**: Selbstregistrierung (öffentlich) oder Admin erstellt Benutzer
✅ **Admins** verwalten Benutzer und weisen Rollen zu
✅ **Jeder** kann sein eigenes Profil bearbeiten
✅ **Deaktivieren** = Temporär sperren (Soft Delete)
✅ **Passwörter**: Mind. 8 Zeichen, eine Zahl, ein Buchstabe

---

**Verwalten Sie Ihre Benutzer sicher!** 🔐👥

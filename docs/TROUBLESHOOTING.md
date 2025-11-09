# Goldsmith ERP - Fehlerbehebung

**Häufige Probleme lösen**
Version 1.0 | Stand: November 2025

---

## Überblick

Diese Anleitung hilft Ihnen bei der Lösung häufiger Probleme mit dem Goldsmith ERP System.

### Inhalt

1. [Login-Probleme](#login-probleme)
2. [Berechtigungs-Fehler](#berechtigungs-fehler)
3. [Browser-Probleme](#browser-probleme)
4. [Dateneingabe-Fehler](#dateneingabe-fehler)
5. [System-Fehler](#system-fehler)
6. [Performance-Probleme](#performance-probleme)
7. [Support kontaktieren](#support-kontaktieren)

---

## Login-Probleme

### Problem: "Invalid credentials" / Falsches Passwort

**Symptom**: Nach Eingabe von E-Mail und Passwort erscheint die Fehlermeldung "Invalid credentials".

**Mögliche Ursachen**:
- Falsches Passwort eingegeben
- E-Mail-Adresse falsch geschrieben
- Caps Lock aktiviert

**Lösung**:
1. Prüfen Sie, ob **Caps Lock** aktiviert ist
2. Prüfen Sie die **E-Mail-Adresse** (Groß-/Kleinschreibung beachten)
3. Prüfen Sie das **Passwort** (mind. 8 Zeichen)
4. Nutzen Sie **"Passwort vergessen?"** (falls verfügbar)
5. Kontaktieren Sie einen **Admin** für Passwort-Reset

---

### Problem: "Account is inactive" / Account deaktiviert

**Symptom**: "This account has been deactivated" oder "Account is inactive".

**Ursache**: Ihr Account wurde von einem Admin deaktiviert.

**Lösung**:
- Kontaktieren Sie einen **Admin**
- Admin muss Ihren Account **reaktivieren**
- Siehe: [FEATURE_USER_MANAGEMENT.md](FEATURE_USER_MANAGEMENT.md)

---

### Problem: Login-Seite lädt nicht

**Symptom**: Login-Seite erscheint nicht oder lädt endlos.

**Mögliche Ursachen**:
- Server ist offline
- Netzwerkprobleme
- Browser-Probleme

**Lösung**:
1. Prüfen Sie Ihre **Internet-Verbindung**
2. Versuchen Sie es mit einem anderen **Browser**
3. Leeren Sie den **Browser-Cache** (Strg+Shift+Del)
4. Prüfen Sie, ob der Server läuft (Kontakt IT/Admin)

---

## Berechtigungs-Fehler

### Problem: "403 Forbidden" / Keine Berechtigung

**Symptom**: Fehlermeldung "You don't have permission to perform this action" oder "403 Forbidden".

**Ursache**: Ihre Rolle hat nicht die nötigen Berechtigungen.

**Beispiele**:
```
❌ Viewer versucht, Auftrag zu erstellen
❌ Goldsmith versucht, Benutzer zu löschen
❌ Nicht-Admin versucht, Rollen zu ändern
```

**Lösung**:
1. Prüfen Sie Ihre **Rolle** (Menu → Profil)
2. Siehe Berechtigungs-Matrix in [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)
3. Kontaktieren Sie einen **Admin**, falls Sie mehr Rechte brauchen
4. Admin kann Ihre **Rolle ändern** (z.B. von Viewer zu Goldsmith)

**Wer darf was?**

| Aktion | Admin | Goldsmith | Viewer |
|--------|-------|-----------|--------|
| Aufträge erstellen | ✅ | ✅ | ❌ |
| Zeit tracken | ✅ | ✅ | ❌ |
| Benutzer verwalten | ✅ | ❌ | ❌ |

---

### Problem: Kann eigene Daten nicht bearbeiten

**Symptom**: Button "Bearbeiten" fehlt oder ist ausgegraut.

**Mögliche Ursachen**:
- Falscher Bereich (z.B. fremdes Profil)
- Technischer Fehler

**Lösung**:
1. Prüfen Sie, ob Sie im **eigenen Profil** sind
2. Gehen Sie zu **Menu → Profil**
3. Jeder darf sein **eigenes Profil** bearbeiten
4. Falls Problem bleibt: Browser-Cache leeren

---

## Browser-Probleme

### Problem: Layout sieht kaputt aus

**Symptom**: Buttons fehlen, Seite sieht komisch aus, keine Farben.

**Mögliche Ursachen**:
- Alter Browser
- CSS wurde nicht geladen
- JavaScript deaktiviert

**Lösung**:
1. **Browser aktualisieren** (Chrome 100+, Firefox 100+, Safari 15+, Edge 100+)
2. **JavaScript aktivieren** (erforderlich!)
3. **Browser-Cache leeren** (Strg+Shift+Del)
4. Seite neu laden (F5 oder Strg+R)
5. Versuchen Sie einen **anderen Browser**

**Unterstützte Browser**:
```
✅ Google Chrome 100+
✅ Mozilla Firefox 100+
✅ Safari 15+
✅ Microsoft Edge 100+
❌ Internet Explorer (nicht unterstützt!)
```

---

### Problem: Seite bleibt weiß oder lädt nicht

**Symptom**: Nach Login nur weiße Seite oder endloses Laden.

**Lösung**:
1. **F5** drücken (Seite neu laden)
2. **Browser-Konsole** öffnen (F12 → Console)
3. Prüfen Sie auf **JavaScript-Fehler** (rote Meldungen)
4. Browser-Cache und Cookies löschen
5. Anderen Browser testen

---

### Problem: Session abgelaufen

**Symptom**: "Your session has expired, please log in again".

**Ursache**: Token ist abgelaufen (Standard: 7 Tage Gültigkeit).

**Lösung**:
- Melden Sie sich **neu an**
- Ihre Daten werden gespeichert
- Kein Datenverlust

**Hinweis**: Aus Sicherheitsgründen läuft die Session nach 7 Tagen ab.

---

## Dateneingabe-Fehler

### Problem: "Email already registered"

**Symptom**: Beim Erstellen eines Benutzers: "Email already registered".

**Ursache**: E-Mail-Adresse wird bereits verwendet.

**Lösung**:
1. Verwenden Sie eine **andere E-Mail-Adresse**
2. Oder: Suchen Sie den **bestehenden Benutzer**
3. Oder: Reaktivieren Sie den **deaktivierten Account**

---

### Problem: "Password must contain at least one number"

**Symptom**: Passwort wird nicht akzeptiert.

**Ursache**: Passwort erfüllt nicht die Anforderungen.

**Passwort-Anforderungen**:
- Mindestens **8 Zeichen**
- Mindestens **eine Zahl**
- Mindestens **ein Buchstabe**

**Lösung**:
```
❌ Falsch: "password" (keine Zahl)
❌ Falsch: "12345678" (keine Buchstaben)
❌ Falsch: "pass1" (zu kurz)
✅ Richtig: "sicheres123"
✅ Richtig: "Goldsmith2025"
```

---

### Problem: "Quantity must be greater than 0"

**Symptom**: Beim Material anlegen oder Bestand ändern.

**Ursache**: Menge muss positiv sein.

**Lösung**:
- Geben Sie eine **positive Zahl** ein
- Beispiel: 10, 50.5, 100
- Nicht: 0, -10

---

### Problem: Material-Bestand wird rot angezeigt

**Symptom**: Material-Eintrag ist rot markiert.

**Ursache**: Bestand ist unter dem **Mindestbestand** (Low Stock Alert).

**Lösung**:
1. Bestellen Sie **Nachschub**
2. Passen Sie den **Mindestbestand** an (falls zu hoch)
3. Siehe: [FEATURE_MATERIAL_MANAGEMENT.md](FEATURE_MATERIAL_MANAGEMENT.md)

**Hinweis**: Dies ist nur eine **Warnung**, keine Fehlermeldung.

---

## System-Fehler

### Problem: "500 Internal Server Error"

**Symptom**: "500 Internal Server Error" oder "Something went wrong".

**Ursache**: Server-seitiger Fehler (Backend-Problem).

**Lösung**:
1. **Warten Sie 1-2 Minuten** und versuchen Sie es erneut
2. Prüfen Sie, ob **Server läuft** (Kontakt IT/Admin)
3. Schauen Sie in die **Server-Logs** (nur für IT)
4. Kontaktieren Sie **Support**

**Für Admins - Logs prüfen**:
```bash
make logs-backend
# Oder
podman-compose logs -f backend
```

---

### Problem: "Network Error" / Verbindungsfehler

**Symptom**: "Network Error" oder "Failed to fetch".

**Mögliche Ursachen**:
- Backend ist offline
- Falsche Backend-URL
- Firewall blockiert Verbindung

**Lösung**:
1. Prüfen Sie **Internet-Verbindung**
2. Prüfen Sie, ob Backend läuft (für IT):
   ```bash
   make status
   # Oder
   podman-compose ps
   ```
3. Prüfen Sie Backend-URL (`.env`-Datei)
4. Prüfen Sie Firewall-Einstellungen

---

### Problem: Daten werden nicht gespeichert

**Symptom**: Nach "Speichern" sind Daten weg oder nicht aktualisiert.

**Mögliche Ursachen**:
- Netzwerkfehler
- Validierungs-Fehler (nicht sichtbar)
- Browser-Cache

**Lösung**:
1. Prüfen Sie **Browser-Konsole** (F12 → Console)
2. Schauen Sie nach **roten Fehlermeldungen**
3. Versuchen Sie es **erneut**
4. Leeren Sie **Browser-Cache**
5. Verwenden Sie einen **anderen Browser**

---

## Performance-Probleme

### Problem: System ist langsam

**Symptom**: Seiten laden langsam, Aktionen dauern lange.

**Mögliche Ursachen**:
- Langsame Internet-Verbindung
- Server überlastet
- Zu viele Browser-Tabs offen
- Alte Hardware

**Lösung**:
1. Prüfen Sie Ihre **Internet-Geschwindigkeit**
2. Schließen Sie **unnötige Tabs**
3. **Neustart** des Browsers
4. **Neustart** des Computers
5. Für IT: Prüfen Sie Server-Ressourcen

---

### Problem: Uploads dauern sehr lange

**Symptom**: Fotos hochladen dauert Minuten.

**Ursache**: Große Dateien oder langsame Verbindung.

**Lösung**:
1. **Komprimieren Sie Fotos** vor dem Upload
2. Empfohlene Größe: **< 5 MB pro Foto**
3. Nutzen Sie **schnellere Internet-Verbindung** (z.B. WLAN statt mobil)
4. Laden Sie **weniger Fotos gleichzeitig** hoch

---

## Support kontaktieren

### Wann sollten Sie Support kontaktieren?

- ✅ Problem lässt sich nicht mit dieser Anleitung lösen
- ✅ System-Fehler ("500 Internal Server Error")
- ✅ Daten sind verschwunden
- ✅ Technische Fragen zur Installation

### Was Sie bereithalten sollten

1. **Fehlermeldung** (Screenshot oder Text)
2. **Ihre Rolle** (Admin / Goldsmith / Viewer)
3. **Browser** und **Version** (z.B. Chrome 120)
4. **Was Sie getan haben** (Schritte zur Reproduktion)
5. **Wann** das Problem aufgetreten ist

### Support-Kanäle

- **Admin kontaktieren** (bei Berechtigungs-Problemen)
- **IT-Support** (bei technischen Problemen)
- **GitHub Issues** (für Entwickler): https://github.com/[repo]/issues

---

## Häufige Fehler-Codes

| Code | Bedeutung | Lösung |
|------|-----------|--------|
| **400** | Bad Request | Eingabe prüfen (z.B. Passwort zu kurz) |
| **401** | Unauthorized | Neu anmelden |
| **403** | Forbidden | Fehlende Berechtigung (Admin kontaktieren) |
| **404** | Not Found | Ressource existiert nicht |
| **500** | Server Error | IT kontaktieren, Logs prüfen |

---

## Checkliste: Erste Schritte bei Problemen

Bevor Sie Support kontaktieren, probieren Sie:

- [ ] **Seite neu laden** (F5)
- [ ] **Browser-Cache leeren** (Strg+Shift+Del)
- [ ] **Anderen Browser** testen
- [ ] **Neu anmelden** (Logout → Login)
- [ ] **Browser-Konsole** prüfen (F12 → Console)
- [ ] **Internet-Verbindung** prüfen
- [ ] **Dokumentation** lesen (diese Anleitung)

---

## Tipps zur Fehlervermeidung

### 1. Regelmäßig speichern

✅ **Speichern Sie oft** während der Arbeit
✅ Prüfen Sie, ob Daten gespeichert wurden

### 2. Browser aktuell halten

✅ **Auto-Updates aktivieren**
✅ Mindestens einmal pro Monat Browser aktualisieren

### 3. Starke Passwörter verwenden

✅ **Mindestens 8 Zeichen**
✅ Buchstaben + Zahlen kombinieren

### 4. Berechtigungen kennen

✅ **Kennen Sie Ihre Rolle** (Admin / Goldsmith / Viewer)
✅ Siehe [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

### 5. Dokumentation nutzen

✅ Lesen Sie die **Feature-Guides**:
- [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md)
- [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)
- [FEATURE_MATERIAL_MANAGEMENT.md](FEATURE_MATERIAL_MANAGEMENT.md)

---

## Zusammenfassung

✅ **Erst selbst probieren**: Seite neu laden, Cache leeren, Rolle prüfen
✅ **Browser aktuell halten**: Chrome 100+, Firefox 100+, Safari 15+
✅ **Berechtigungen kennen**: Admin / Goldsmith / Viewer
✅ **Logs prüfen** (für IT): `make logs-backend`
✅ **Support kontaktieren**: Mit Fehlermeldung, Browser-Info, Schritten

---

**Die meisten Probleme lassen sich schnell lösen!** 🔧✨

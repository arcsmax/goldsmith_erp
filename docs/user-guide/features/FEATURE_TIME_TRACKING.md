# Goldsmith ERP - Zeiterfassung

**Arbeitszeit präzise dokumentieren**
Version 1.0 | Stand: November 2025

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Was ist Zeiterfassung?](#was-ist-zeiterfassung)
3. [Aktivitäten verstehen](#aktivitäten-verstehen)
4. [Zeiterfassung starten](#zeiterfassung-starten)
5. [Zeiterfassung stoppen](#zeiterfassung-stoppen)
6. [Laufende Zeit ansehen](#laufende-zeit-ansehen)
7. [Eigene Zeiteinträge ansehen](#eigene-zeiteinträge-ansehen)
8. [Zeiteinträge bearbeiten](#zeiteinträge-bearbeiten)
9. [Unterbrechungen hinzufügen](#unterbrechungen-hinzufügen)
10. [Zeitberichte pro Auftrag](#zeitberichte-pro-auftrag)
11. [Berechtigungen](#berechtigungen)
12. [Best Practices](#best-practices)

---

## Überblick

Die **Zeiterfassung** dokumentiert, wie viel Zeit Sie für welchen Auftrag aufwenden. Dies hilft bei der Kalkulation, Nachverfolgung und Abrechnung.

### Hauptfunktionen

- ⏱️ **Zeit starten/stoppen** - Timer für Arbeitszeit
- 📋 **Aktivitäten zuordnen** - Was wurde gemacht?
- ⏸️ **Unterbrechungen erfassen** - Pausen dokumentieren
- 📊 **Zeitberichte** - Arbeitszeit pro Auftrag ansehen
- ⭐ **Bewertungen** - Komplexität und Qualität dokumentieren

> **⚠️ Wichtiger Hinweis**: Das Backend für Zeiterfassung ist vollständig implementiert. Die Benutzeroberfläche (UI) wird in **Woche 2-3** fertiggestellt. Diese Dokumentation beschreibt die geplante Funktionsweise.

---

## Was ist Zeiterfassung?

**Zeiterfassung** bedeutet, dass Sie dokumentieren:
- Wann haben Sie mit der Arbeit begonnen?
- Wann haben Sie die Arbeit beendet?
- An welchem Auftrag haben Sie gearbeitet?
- Welche Tätigkeit haben Sie ausgeführt?

### Warum Zeit erfassen?

✅ **Kostenkalkulation**: Was kostet ein Auftrag wirklich?
✅ **Transparenz**: Nachvollziehbare Arbeitszeiten
✅ **Optimierung**: Wo geht am meisten Zeit drauf?
✅ **Abrechnung**: Basis für Rechnungen
✅ **Planung**: Wie lange dauern ähnliche Aufträge?

### Beispiel

```
Auftrag: Ring Reparatur - Frau Müller
Aktivität: Löten
Start: 15.11.2025, 10:00 Uhr
Ende: 15.11.2025, 11:30 Uhr
Dauer: 1:30 Stunden
Bewertung: Komplexität 3/5, Qualität 5/5
```

---

## Aktivitäten verstehen

**Aktivitäten** beschreiben, **was** Sie während der Zeiterfassung gemacht haben.

### Die drei Kategorien

#### 1. 🔨 Fabrication (Fertigung)

Produktive Werkstattarbeit:
- **Sägen** 🪚 - Metall zuschneiden
- **Feilen** ⚒️ - Oberflächen glätten
- **Löten** 🔥 - Verbindungen herstellen
- **Polieren** ✨ - Oberflächen veredeln
- **Fassen (Steine)** 💎 - Edelsteine einsetzen
- **Gravieren** ✍️ - Text oder Muster einarbeiten
- **Emaillieren** 🎨 - Email-Beschichtung

#### 2. 📋 Administration (Verwaltung)

Administrative Tätigkeiten:
- **Kundenberatung** 👥 - Gespräche mit Kunden
- **Angebot erstellen** 📝 - Kostenvoranschläge
- **Dokumentation** 📋 - Fotos, Notizen
- **Qualitätskontrolle** 🔍 - Prüfung fertiger Arbeiten

#### 3. ⏳ Waiting (Warten)

Nicht-produktive Zeiten:
- **Warten auf Material** ⏳ - Materiallieferung
- **Warten auf Kundenfeedback** 💬 - Rückfragen
- **Pause** ☕ - Kaffeepause, Mittagspause
- **Unterbrechung** ⚠️ - Unvorhergesehene Störungen

### Standard-Aktivitäten vs. Eigene

**Standard-Aktivitäten**:
- Vom System vordefiniert
- Für alle Benutzer verfügbar
- Können nicht gelöscht werden

**Eigene Aktivitäten** (nur Goldsmiths):
- Sie können eigene Aktivitäten erstellen
- Beispiel: "Kettchen reparieren" (spezifisch für Ihre Werkstatt)
- Nur Sie sehen diese Aktivität

---

## Zeiterfassung starten

### Voraussetzungen

- Sie benötigen die Berechtigung `TIME_TRACK`
- Rolle: **Admin** oder **Goldsmith**
- Keine laufende Zeiterfassung (nur eine gleichzeitig!)

### Schritt-für-Schritt-Anleitung

#### 1. Zeiterfassung öffnen

- Klicken Sie im Hauptmenü auf **"Zeiterfassung"**
- Oder klicken Sie auf **"Zeit starten"** auf der Übersichtsseite

`[Screenshot: Zeiterfassung-Button im Hauptmenü]`

#### 2. Auftrag wählen

Wählen Sie den **Auftrag**, an dem Sie arbeiten:
- Dropdown-Liste mit allen offenen Aufträgen
- Suche nach Auftragstitel oder Kundennamen

```
Beispiel: "Ring Reparatur - Frau Müller (#42)"
```

`[Screenshot: Auftrags-Dropdown]`

#### 3. Aktivität wählen

Wählen Sie die **Aktivität**, die Sie durchführen:
- Dropdown-Liste mit allen Aktivitäten
- Filtern nach Kategorie (optional)

```
Beispiel: "Löten 🔥"
```

`[Screenshot: Aktivitäts-Dropdown]`

#### 4. Lagerort (optional)

Falls Ihr Betrieb mehrere Standorte hat:
```
Beispiel: "Werkstatt 1"
```

#### 5. Timer starten

- Klicken Sie auf **"Zeit starten"**
- Timer läuft ab sofort
- Sie sehen die **laufende Zeit** in der Statusleiste

`[Screenshot: Laufender Timer]`

### Erfolgsanzeige

Nach dem Start sehen Sie:
```
✅ Zeiterfassung gestartet
Auftrag: Ring Reparatur - Frau Müller
Aktivität: Löten
Seit: 10:00 Uhr
```

---

## Zeiterfassung stoppen

### Wann stoppen?

Stoppen Sie die Zeit, wenn:
- Die Arbeit am Auftrag abgeschlossen ist
- Sie zu einem anderen Auftrag wechseln
- Sie eine Pause machen
- Feierabend ist

### Schritt-für-Schritt-Anleitung

#### 1. Stopp-Button klicken

- Klicken Sie auf **"Zeit stoppen"** in der Statusleiste
- Oder gehen Sie zu **Zeiterfassung** → **"Laufende Zeit stoppen"**

`[Screenshot: Zeit stoppen Button]`

#### 2. Zusatzinformationen (optional)

**Komplexität** (1-5 Sterne):
```
Wie kompliziert war die Arbeit?
1 = Sehr einfach
5 = Sehr komplex
```

**Qualität** (1-5 Sterne):
```
Wie zufrieden sind Sie mit dem Ergebnis?
1 = Nacharbeit nötig
5 = Perfekt
```

**Nacharbeit erforderlich?**
```
☐ Ja, Nacharbeit nötig
```

**Notizen** (optional):
```
Beispiel:
Fassung war schwieriger als erwartet.
Stein musste zweimal neu gefasst werden.
```

#### 3. Speichern

- Klicken Sie auf **"Zeit stoppen & speichern"**
- Zeiteintrag wird gespeichert
- Timer stoppt

`[Screenshot: Stopp-Dialog mit Bewertungen]`

### Was passiert?

- **Endzeitpunkt** wird gesetzt
- **Dauer** wird automatisch berechnet
- **Eintrag** wird gespeichert
- **Aktivitäts-Statistik** wird aktualisiert

---

## Laufende Zeit ansehen

### Wo sehen Sie die laufende Zeit?

**Statusleiste** (unten):
```
⏱️ Läuft seit 10:00 Uhr | Auftrag: Ring Reparatur | Löten | 1:32:45
```

**Zeiterfassungs-Seite**:
```
Laufende Zeiterfassung
Auftrag: Ring Reparatur - Frau Müller (#42)
Aktivität: Löten
Gestartet: 15.11.2025, 10:00 Uhr
Laufzeit: 1:32:45

[Zeit stoppen]
```

`[Screenshot: Laufende Zeiterfassung Ansicht]`

### API-Endpunkt

Für Entwickler:
```
GET /api/time-tracking/running
```

---

## Eigene Zeiteinträge ansehen

### Zur Zeitübersicht

1. Klicken Sie auf **Zeiterfassung** im Hauptmenü
2. Wählen Sie **"Meine Zeiteinträge"**

`[Screenshot: Zeiteinträge-Liste]`

### Was Sie sehen

Liste Ihrer Zeiteinträge:

| Auftrag | Aktivität | Start | Ende | Dauer | Komplexität | Qualität |
|---------|-----------|-------|------|-------|-------------|----------|
| Ring #42 | Löten | 10:00 | 11:30 | 1:30h | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Kette #38 | Polieren | 13:00 | 14:15 | 1:15h | ⭐⭐ | ⭐⭐⭐⭐⭐ |

### Filtern und Sortieren

**Nach Datum filtern**:
- Letzte 7 Tage
- Letzte 30 Tage
- Dieser Monat
- Benutzerdefinierter Zeitraum

**Sortieren nach**:
- Datum (neueste/älteste zuerst)
- Dauer (längste/kürzeste zuerst)
- Auftrag

---

## Zeiteinträge bearbeiten

### Wer darf bearbeiten?

- ✅ **Admins**: Alle Zeiteinträge
- ✅ **Goldsmiths**: Nur eigene Zeiteinträge
- ❌ **Viewers**: Keine Bearbeitung

### Warum bearbeiten?

- Vergessene Bewertungen nachtragen
- Notizen hinzufügen
- Fehlerhafte Zeiten korrigieren

### Bearbeitung

1. Öffnen Sie Ihre **Zeiteinträge**
2. Klicken Sie auf einen Eintrag
3. Klicken Sie auf **"Bearbeiten"**
4. Ändern Sie:
   - Komplexität
   - Qualität
   - Nacharbeit-Flag
   - Notizen
   - ⚠️ **Nicht änderbar**: Auftrag, Aktivität, Start/End-Zeit
5. Klicken Sie auf **"Speichern"**

`[Screenshot: Zeiteintrag bearbeiten]`

---

## Unterbrechungen hinzufügen

### Was sind Unterbrechungen?

**Unterbrechungen** sind Pausen während der Arbeitszeit:
- Telefongespräch
- Kundenbesuch
- Materialsuche
- Unvorhergesehene Störungen

### Warum Unterbrechungen erfassen?

- **Genauere Zeitmessung**: Produktive vs. unproduktive Zeit
- **Analyse**: Wie viele Unterbrechungen pro Tag?
- **Optimierung**: Störquellen identifizieren

### Unterbrechung hinzufügen

Es gibt derzeit keinen manuellen "Unterbrechung hinzufügen"-Dialog auf der
Auftragsseite. Unterbrechungen werden über den QR-/NFC-Scan am
Werkbank-Platz erfasst.

### Automatische Berechnung

Die **Netto-Arbeitszeit** wird automatisch berechnet:
```
Gesamtzeit: 2:00 Stunden
Unterbrechungen: 0:25 Stunden
Netto-Arbeitszeit: 1:35 Stunden
```

---

## Zeitberichte pro Auftrag

### Übersicht

Auf der **Auftragsdetailseite** (Tab "Arbeit", Abschnitt Zeiterfassung) sehen Sie alle Zeiten für diesen Auftrag.

`[Screenshot: Arbeit-Tab, Abschnitt Zeiterfassung]`

### Was Sie sehen

**Liste aller Zeiteinträge**:
- Mitarbeiter (wer?)
- Aktivität (was?)
- Dauer (wie lange?)
- Datum

**Gesamtzeit**:
```
Gesamtarbeitszeit: 5:45 Stunden
Anzahl Einträge: 4
```

### Wer sieht was?

| Rolle | Sichtbarkeit |
|-------|--------------|
| **Admin** | Alle Zeiteinträge aller Mitarbeiter |
| **Goldsmith** | Nur eigene Zeiteinträge |
| **Viewer** | Nur eigene Zeiteinträge |

---

## Berechtigungen

### Zeiterfassungs-Berechtigungen

| Aktion | Admin | Goldsmith | Viewer |
|--------|-------|-----------|--------|
| Zeit starten/stoppen | ✅ | ✅ | ❌ |
| Eigene Zeiten ansehen | ✅ | ✅ | ✅ |
| Alle Zeiten ansehen | ✅ | ❌ | ❌ |
| Eigene Zeiten bearbeiten | ✅ | ✅ | ❌ |
| Zeiteinträge löschen | ✅ | ❌ | ❌ |
| Unterbrechungen hinzufügen | ✅ | ✅ | ❌ |
| Zeitberichte ansehen | ✅ | ✅ | ✅ |

**Wichtig**:
- Goldsmiths sehen **nur ihre eigenen** Zeiteinträge
- Admins sehen **alle** Zeiteinträge (für Auswertungen)

> **Weitere Informationen**: Details zu allen Berechtigungen finden Sie in [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

---

## Best Practices

### Zeiterfassung starten

✅ **Gut**:
- Zeit **sofort** beim Start der Arbeit starten
- Richtige Aktivität wählen
- Richtigen Auftrag wählen

❌ **Schlecht**:
- Stunden später nachträglich Zeit erfassen
- Falsche Aktivität oder Auftrag
- Zeit vergessen zu starten

**Regel**: Start = sofort, wenn Arbeit beginnt!

---

### Aktivitäten wählen

✅ **Gut**:
- Passende Aktivität für die Tätigkeit
- Beispiel: Löten beim Löten, nicht "Polieren"

❌ **Schlecht**:
- Immer die gleiche Aktivität wählen
- Unpassende Aktivitäten

**Regel**: Aktivität = was ich wirklich mache.

---

### Unterbrechungen dokumentieren

✅ **Gut**:
- Längere Unterbrechungen (>5 Min.) erfassen
- Grund angeben
- Dauer schätzen

❌ **Schlecht**:
- Alle Unterbrechungen ignorieren
- Produktive und unproduktive Zeit vermischen

**Regel**: Ab 5 Minuten = Unterbrechung erfassen.

---

### Bewertungen abgeben

✅ **Gut**:
- Ehrliche Bewertung von Komplexität
- Realistische Qualitätsbewertung
- Nacharbeit-Flag setzen, wenn nötig

❌ **Schlecht**:
- Immer 5 Sterne (keine Aussagekraft)
- Bewertungen weglassen
- Nacharbeit verschweigen

**Regel**: Ehrliche Bewertungen helfen bei Optimierung!

---

### Zeit stoppen

✅ **Gut**:
- Zeit **sofort** beim Ende der Arbeit stoppen
- Bewertungen zeitnah abgeben
- Notizen hinzufügen, wenn relevant

❌ **Schlecht**:
- Timer stundenlang laufen lassen
- Zeit vergessen zu stoppen
- Keine Bewertungen

**Regel**: Stopp = sofort, wenn Arbeit endet!

---

### Zeitberichte nutzen

✅ **Gut**:
- Regelmäßig eigene Zeiten prüfen
- Muster erkennen (welche Aktivität dauert lange?)
- Für Optimierung nutzen

❌ **Schlecht**:
- Berichte nie ansehen
- Keine Analyse

**Regel**: Daten nutzen, um besser zu werden!

---

## Zusammenfassung

### Workflow-Übersicht

1. **Zeit starten**
   - Auftrag + Aktivität wählen
   - Timer läuft
2. **Arbeiten**
   - Konzentriert am Auftrag arbeiten
   - Unterbrechungen dokumentieren
3. **Zeit stoppen**
   - Bewertungen abgeben
   - Notizen hinzufügen
4. **Berichte ansehen**
   - Eigene Zeiten prüfen
   - Muster erkennen

### Wichtigste Erkenntnisse

✅ **Zeiterfassung** dokumentiert Arbeitsaufwand
✅ **Aktivitäten** beschreiben, was gemacht wurde
✅ **Start/Stopp** sollte sofort erfolgen
✅ **Bewertungen** helfen bei Optimierung
✅ **Unterbrechungen** für genauere Zeitmessung
✅ **Goldsmiths** sehen nur eigene Zeiten

---

## Weitere Informationen

📖 **Auftragsverwaltung**: [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)
📖 **Berechtigungen**: [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)
📖 **Tägliche Workflows**: [DAILY_WORKFLOWS.md](DAILY_WORKFLOWS.md)

---

**Dokumentieren Sie Ihre Arbeitszeit präzise!** ⏱️📊

---

## ⚠️ Hinweis zur Implementierung

Das Backend für die Zeiterfassung ist **vollständig implementiert und getestet**. Die Benutzeroberfläche (UI) wird in **Woche 2-3** der Entwicklung fertiggestellt.

**Aktueller Stand**:
- ✅ API-Endpunkte funktionsfähig
- ✅ Zeit starten/stoppen (Backend)
- ✅ Aktivitäten-Verwaltung (Backend)
- ✅ Zeitberichte (Backend)
- ⏳ UI in Entwicklung (geplant: Woche 2-3)

**Für Entwickler**:
API-Dokumentation verfügbar unter: `http://localhost:8000/docs`

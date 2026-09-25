# Goldsmith ERP - Auftragsverwaltung

**Komplettanleitung für die Arbeit mit Aufträgen**
Version 1.0 | Stand: November 2025

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Was ist ein Auftrag?](#was-ist-ein-auftrag)
3. [Auftragsliste ansehen](#auftragsliste-ansehen)
4. [Neuen Auftrag erstellen](#neuen-auftrag-erstellen)
5. [Auftragsdetails verstehen](#auftragsdetails-verstehen)
6. [Auftrag bearbeiten](#auftrag-bearbeiten)
7. [Materialien zu Aufträgen hinzufügen](#materialien-zu-aufträgen-hinzufügen)
8. [Auftragsstatus ändern](#auftragsstatus-ändern)
9. [Fotos zu Aufträgen hinzufügen](#fotos-zu-aufträgen-hinzufügen)
10. [Zeiterfassung für Aufträge](#zeiterfassung-für-aufträge)
11. [Aufträge suchen und filtern](#aufträge-suchen-und-filtern)
12. [Auftrag löschen](#auftrag-löschen)
13. [Berechtigungen](#berechtigungen)
14. [Best Practices](#best-practices)

---

## Überblick

Die **Auftragsverwaltung** ist das Herzstück von Goldsmith ERP. Hier verwalten Sie alle Kundenaufträge von der Anfrage bis zur Fertigstellung.

### Hauptfunktionen

- 📋 **Aufträge erstellen** - Neue Kundenaufträge erfassen
- 👀 **Aufträge ansehen** - Details und Status prüfen
- ✏️ **Aufträge bearbeiten** - Informationen aktualisieren
- 💎 **Materialien zuordnen** - Welche Materialien werden verwendet?
- ⏱️ **Zeit erfassen** - Arbeitszeit pro Auftrag dokumentieren
- 📸 **Fotos hinzufügen** - Visuelle Dokumentation
- 📊 **Status verfolgen** - Von "Ausstehend" bis "Abgeschlossen"

---

## Was ist ein Auftrag?

Ein **Auftrag** in Goldsmith ERP repräsentiert einen Kundenauftrag in Ihrer Werkstatt.

### Typische Aufträge

- **Ring reparieren** (Kunde: Maria Müller)
- **Halskette anfertigen** (Kunde: Thomas Schmidt)
- **Armband kürzen** (Kunde: Anna Weber)
- **Trauringe gravieren** (Kunde: Familie Becker)

### Was gehört zu einem Auftrag?

Jeder Auftrag enthält:

1. **Grundinformationen**
   - Titel (z.B. "Ring Reparatur - Frau Müller")
   - Beschreibung (Details des Auftrags)
   - Kunde (wer hat bestellt?)

2. **Zeitplanung**
   - Abgabedatum (Deadline)
   - Erstellungsdatum
   - Letzte Aktualisierung

3. **Status**
   - Pending (Ausstehend)
   - In Progress (In Bearbeitung)
   - Completed (Abgeschlossen)

4. **Zusatzinformationen**
   - Materialien (welche Edelmetalle/Steine?)
   - Zeiteinträge (Arbeitsaufwand)
   - Fotos (Vorher/Nachher)

---

## Auftragsliste ansehen

### Zur Auftragsliste navigieren

1. Klicken Sie im Hauptmenü auf **"Aufträge"**
2. Sie sehen die **Auftragsliste** mit allen Aufträgen

`[Screenshot: Auftragsliste mit mehreren Aufträgen]`

### Was Sie sehen

Die Auftragsliste zeigt:

| Spalte | Beschreibung |
|--------|--------------|
| **ID** | Eindeutige Auftragsnummer (z.B. #42) |
| **Titel** | Auftragstitel |
| **Kunde** | Kundenname |
| **Status** | Aktueller Status (Badge) |
| **Abgabedatum** | Deadline |
| **Erstellt am** | Erstellungsdatum |

### Farbcodes für Status

- 🟡 **Pending** (Gelb) - Noch nicht begonnen
- 🔵 **In Progress** (Blau) - In Bearbeitung
- 🟢 **Completed** (Grün) - Fertiggestellt

---

## Neuen Auftrag erstellen

### Schritt-für-Schritt-Anleitung

#### 1. Neuen Auftrag starten

- Klicken Sie auf **"Neuer Auftrag"** oder **"+ Auftrag"**
- Das Formular öffnet sich

`[Screenshot: Button "Neuer Auftrag"]`

#### 2. Grundinformationen eingeben

**Titel** (Pflichtfeld):
```
Beispiel: Ring Reparatur - Frau Müller
```
- Kurz und prägnant
- Enthält Auftragsart und Kunde
- Maximal 200 Zeichen

**Beschreibung** (Pflichtfeld):
```
Beispiel:
Goldring 585 hat Fassung verloren.
Stein muss neu gefasst werden.
Ringweite prüfen und ggf. anpassen.
```
- Detaillierte Auftragsbeschreibung
- Was soll gemacht werden?
- Besonderheiten beachten
- Maximal 2000 Zeichen

**Kunde** (Pflichtfeld):
- Wählen Sie aus der Kundenliste
- Oder erstellen Sie einen neuen Kunden (Button "+ Neuer Kunde")

#### 3. Zeitplanung

**Abgabedatum** (Pflichtfeld):
- Klicken Sie auf das Kalender-Icon
- Wählen Sie das gewünschte Datum
- ⚠️ Datum muss in der Zukunft liegen

`[Screenshot: Datepicker für Abgabedatum]`

#### 4. Status festlegen

**Anfangsstatus** (optional):
- Standard: **Pending** (Ausstehend)
- Falls sofort begonnen: **In Progress**
- Falls bereits fertig: **Completed** (selten bei Neuanlage)

#### 5. Speichern

- Klicken Sie auf **"Auftrag erstellen"**
- Sie werden zur Auftragsdetailseite weitergeleitet
- Erfolgsmeldung: ✅ "Auftrag erfolgreich erstellt"

`[Screenshot: Erfolgsmeldung nach Erstellung]`

---

## Auftragsdetails verstehen

### Detailseite öffnen

Klicken Sie in der Auftragsliste auf einen Auftrag, um die Detailseite zu öffnen.

`[Screenshot: Auftragsdetailseite]`

### Tab-System

Die Detailseite verwendet **Tabs** (Registerkarten) für verschiedene Bereiche.
Früher gab es bis zu 14 einzelne Tabs; heute sind es fünf zusammengefasste
Tabs (Übersicht, Arbeit, Fotos, Kunde, Verlauf):

#### Tab 1: Übersicht

Zeigt alle Grundinformationen:
- Titel und Beschreibung
- Kunde
- Status
- Abgabedatum
- Erstellungs- und Aktualisierungsdatum

Aktionen:
- **Bearbeiten** - Auftrag ändern (Button)
- **Status ändern** - Dropdown für Status
- **Löschen** - Auftrag entfernen (nur Admin)

#### Tab 2: Arbeit

Bündelt alles, was am Werkbank-Platz und rund um die Kalkulation passiert,
in Abschnitten innerhalb eines Tabs (früher eigene Tabs: Zeiterfassung,
Materialien, Metall, Arbeitszettel, Kosten, Soll/Ist, Altgold, Übergabe):

- **Zeiterfassung** - Liste aller Zeiteinträge, Aktivität, Dauer,
  Mitarbeiter, Gesamtarbeitszeit, **Zeit erfassen** (Button)
- **Materialien** - Materialliste (Name, Menge, Einheit), Gesamtwert,
  **+ Material hinzufügen** (Button)
- **Metall** - Metallverbrauch, sofern der Auftrag einen Metalltyp hat
- **Arbeitszettel** - Arbeitsschritte und Notizen der Goldschmiedin/des
  Goldschmieds
- **Kosten** und **Soll/Ist** - nur mit Finanzberechtigung (ADMIN,
  GOLDSMITH) sichtbar
- **Altgold** - erfasstes Altgold (Ankauf) zu diesem Auftrag
- **Übergabe** - Übergabeprotokoll bei Abholung

`[Screenshot: Arbeit-Tab]`

#### Tab 3: Fotos

Zeigt hochgeladene Fotos:
- Vorher-Bilder
- Arbeitsfortschritt
- Nachher-Bilder
- **+ Foto hochladen** (Button)

`[Screenshot: Fotos-Tab]`

#### Tab 4: Kunde

Kundeninformationen und Kommunikation zu diesem Auftrag (Kundeninfo,
Nachrichtenverlauf).

#### Tab 5: Verlauf

Die vollständige Zeitlinie des Auftrags: Statuswechsel, Kundenupdates,
Fotos und Zeiteinträge in einer gemeinsamen Historie.

### Tab-Memory-System

Das System merkt sich, welchen Tab Sie zuletzt geöffnet hatten:
- Öffnen Sie z.B. "Arbeit" bei Auftrag #42
- Beim nächsten Besuch von Auftrag #42 öffnet sich automatisch "Arbeit"
- Spart Zeit bei wiederholten Besuchen

---

## Auftrag bearbeiten

### Bearbeitungsmodus aktivieren

1. Öffnen Sie die Auftragsdetailseite
2. Klicken Sie auf **"Bearbeiten"**
3. Das Formular wird editierbar

`[Screenshot: Bearbeiten-Button]`

### Was kann bearbeitet werden?

- ✅ Titel
- ✅ Beschreibung
- ✅ Kunde (Neuzuordnung möglich)
- ✅ Abgabedatum
- ✅ Status
- ❌ ID (nicht änderbar)
- ❌ Erstellungsdatum (nicht änderbar)

### Änderungen speichern

1. Nehmen Sie Ihre Änderungen vor
2. Klicken Sie auf **"Speichern"**
3. Erfolgsmeldung: ✅ "Auftrag aktualisiert"

### Abbrechen

- Klicken Sie auf **"Abbrechen"**
- Änderungen werden verworfen
- Sie kehren zur Ansicht zurück

---

## Materialien zu Aufträgen hinzufügen

### Warum Materialien zuordnen?

- Dokumentation des Materialverbrauchs
- Kostenberechnung
- Bestandsverwaltung
- Nachvollziehbarkeit

### Material hinzufügen

#### Schritt 1: Materialien-Abschnitt öffnen

1. Öffnen Sie die Auftragsdetailseite
2. Klicken Sie auf Tab **"Arbeit"** und öffnen Sie den Abschnitt **"Materialien"**

#### Schritt 2: Material auswählen

1. Klicken Sie auf **"+ Material hinzufügen"**
2. Dialog öffnet sich

`[Screenshot: Material hinzufügen Dialog]`

#### Schritt 3: Material und Menge angeben

**Material** (Dropdown):
- Wählen Sie aus vorhandenen Materialien
- Beispiel: "Gold 750 (18K)"

**Menge** (Zahlenfeld):
```
Beispiel: 5.2
```
- In der Einheit des Materials
- z.B. Gramm für Gold, Stück für Steine

#### Schritt 4: Hinzufügen

- Klicken Sie auf **"Hinzufügen"**
- Material wird der Liste hinzugefügt
- Materialbestand wird **automatisch reduziert** (bei Goldsmiths)

### Material entfernen

- Klicken Sie auf das **🗑️ Löschen-Icon** neben dem Material
- Bestätigen Sie die Löschung
- Material wird entfernt
- Bestand wird **zurückgebucht**

### Mehrere Materialien

Sie können beliebig viele Materialien hinzufügen:
- Gold 750 (5.2g)
- Diamant 0.5ct (1 Stück)
- Silber 925 (12.0g)

---

## Auftragsstatus ändern

### Die drei Status

| Status | Bedeutung | Wann verwenden? |
|--------|-----------|-----------------|
| 🟡 **Pending** | Ausstehend | Auftrag angelegt, aber noch nicht begonnen |
| 🔵 **In Progress** | In Bearbeitung | Arbeit hat begonnen |
| 🟢 **Completed** | Abgeschlossen | Auftrag fertiggestellt und ausgeliefert |

### Status ändern

#### Variante 1: Auf der Detailseite

1. Öffnen Sie die Auftragsdetailseite
2. Klicken Sie auf das **Status-Dropdown**
3. Wählen Sie den neuen Status
4. Status wird sofort gespeichert

`[Screenshot: Status-Dropdown]`

#### Variante 2: Beim Bearbeiten

1. Klicken Sie auf **"Bearbeiten"**
2. Ändern Sie den Status im Formular
3. Klicken Sie auf **"Speichern"**

### Typischer Status-Workflow

```
Neuer Auftrag
    ↓
🟡 Pending (Ausstehend)
    ↓
Arbeit beginnt
    ↓
🔵 In Progress (In Bearbeitung)
    ↓
Arbeit abgeschlossen
    ↓
🟢 Completed (Fertiggestellt)
```

---

## Fotos zu Aufträgen hinzufügen

### Warum Fotos?

- **Dokumentation** des Ausgangszustands
- **Fortschritt** zeigen (Zwischenstände)
- **Ergebnis** festhalten (Vorher/Nachher)
- **Kundenkommunikation** verbessern

### Foto hochladen

#### Schritt 1: Fotos-Tab öffnen

1. Öffnen Sie die Auftragsdetailseite
2. Klicken Sie auf Tab **"Fotos"**

#### Schritt 2: Foto auswählen

1. Klicken Sie auf **"+ Foto hochladen"**
2. Dialog öffnet sich

`[Screenshot: Foto hochladen Dialog]`

#### Schritt 3: Datei auswählen

- Klicken Sie auf **"Datei auswählen"**
- Wählen Sie ein Foto von Ihrem Gerät
- **Unterstützte Formate**: JPG, PNG, WEBP
- **Maximale Größe**: 10 MB

#### Schritt 4: Beschreibung (optional)

Geben Sie eine Beschreibung ein:
```
Beispiel: Ausgangszustand - Fassung locker
```

#### Schritt 5: Hochladen

- Klicken Sie auf **"Hochladen"**
- Foto wird gespeichert
- Vorschau wird angezeigt

### Foto-Tipps

✅ **Gute Fotos**:
- Ausreichend Licht
- Scharfes Bild
- Nah genug für Details
- Mehrere Winkel

❌ **Schlechte Fotos**:
- Zu dunkel
- Unscharf
- Zu weit weg
- Nur ein Foto

### Fotos ansehen

- In der Foto-Galerie werden alle Fotos als Miniaturansichten angezeigt
- Klicken Sie auf ein Foto, um es in voller Größe zu sehen
- Beschreibung wird unter dem Foto angezeigt

### Foto löschen

- Klicken Sie auf das **🗑️ Löschen-Icon**
- Bestätigen Sie die Löschung
- Foto wird permanent entfernt

---

## Zeiterfassung für Aufträge

### Übersicht

Im Abschnitt "Zeiterfassung" des Tabs "Arbeit" sehen Sie:
- Alle erfassten Arbeitszeiten für diesen Auftrag
- Mitarbeiter, Aktivität, Dauer
- Gesamtarbeitszeit

`[Screenshot: Arbeit-Tab, Abschnitt Zeiterfassung]`

### Zeit erfassen

Es gibt zwei Wege, Zeit für einen Auftrag zu erfassen:

#### Weg 1: Über den Auftrag

1. Öffnen Sie die Auftragsdetailseite
2. Klicken Sie auf Tab **"Arbeit"** und öffnen Sie den Abschnitt **"Zeiterfassung"**
3. Klicken Sie auf **"Zeit erfassen"**
4. Wählen Sie die Aktivität
5. Timer startet automatisch

#### Weg 2: Über die Zeiterfassung

1. Gehen Sie zu **Zeiterfassung** im Hauptmenü
2. Klicken Sie auf **"Zeit starten"**
3. Wählen Sie den Auftrag
4. Wählen Sie die Aktivität
5. Timer startet

> **Weitere Informationen**: Ausführliche Anleitung zur Zeiterfassung finden Sie in [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md)

### Zeitbericht pro Auftrag

Die Zeiteinträge-Liste zeigt:

| Spalte | Beschreibung |
|--------|--------------|
| **Mitarbeiter** | Wer hat gearbeitet? |
| **Aktivität** | Was wurde gemacht? (z.B. "Löten") |
| **Start** | Startzeit |
| **Ende** | Endzeit |
| **Dauer** | Arbeitszeit in Stunden:Minuten |

**Gesamtzeit**:
```
Beispiel: 3:45 Stunden (3 Stunden 45 Minuten)
```

---

## Aufträge suchen und filtern

### Suchfunktion

Oben rechts in der Auftragsliste befindet sich ein **Suchfeld**.

`[Screenshot: Suchfeld]`

**Suche nach**:
- Auftragstitel
- Kundennamen
- Auftragsnummer

Beispiel:
```
Eingabe: "Müller"
Ergebnis: Alle Aufträge von Kunden mit "Müller" im Namen
```

### Filter nach Status

Filtern Sie Aufträge nach Status:

1. Klicken Sie auf **"Filter"** oder das Filter-Icon
2. Wählen Sie einen oder mehrere Status:
   - ☐ Pending
   - ☐ In Progress
   - ☐ Completed
3. Klicken Sie auf **"Anwenden"**

`[Screenshot: Status-Filter]`

**Beispiel-Anwendungen**:
- Nur offene Aufträge: **Pending** + **In Progress**
- Nur abgeschlossene Aufträge: **Completed**
- Alle Aufträge: Alle Filter deaktivieren

### Sortierung

Klicken Sie auf die Spaltenüberschriften, um zu sortieren:

- **ID**: Aufsteigend/Absteigend
- **Titel**: Alphabetisch A-Z/Z-A
- **Abgabedatum**: Älteste/Neueste zuerst
- **Erstellt am**: Älteste/Neueste zuerst

`[Screenshot: Sortier-Icons in Spaltenüberschriften]`

---

## Auftrag löschen

### ⚠️ Wichtig: Nur Admins können löschen

Aus Sicherheitsgründen können nur **Admins** Aufträge löschen.

**Warum?**
- Verhindert versehentliches Löschen
- Schützt wichtige Daten
- Sichert Dokumentation

### Löschvorgang (nur für Admins)

1. Öffnen Sie die Auftragsdetailseite
2. Klicken Sie auf **"Löschen"** (roter Button)
3. Bestätigungsdialog erscheint:
   ```
   Möchten Sie diesen Auftrag wirklich löschen?
   Diese Aktion kann nicht rückgängig gemacht werden!
   ```
4. Klicken Sie auf **"Ja, löschen"**

`[Screenshot: Lösch-Bestätigung]`

### Was wird gelöscht?

Beim Löschen eines Auftrags werden **alle zugehörigen Daten** entfernt:
- ❌ Auftragsinformationen
- ❌ Materialzuordnungen (Materialien bleiben, aber Zuordnung wird gelöscht)
- ❌ Zeiteinträge (werden gelöscht!)
- ❌ Fotos (werden permanent gelöscht!)

> **Tipp**: Setzen Sie Aufträge lieber auf Status "Completed" statt zu löschen. So bleibt die Historie erhalten.

---

## Berechtigungen

### Wer darf was?

| Aktion | Admin | Goldsmith | Viewer |
|--------|-------|-----------|--------|
| Aufträge ansehen | ✅ | ✅ | ✅ |
| Auftrag erstellen | ✅ | ✅ | ❌ |
| Auftrag bearbeiten | ✅ | ✅ | ❌ |
| Auftrag löschen | ✅ | ❌ | ❌ |
| Materialien hinzufügen | ✅ | ✅ | ❌ |
| Status ändern | ✅ | ✅ | ❌ |
| Fotos hochladen | ✅ | ✅ | ❌ |

> **Weitere Informationen**: Details zu allen Berechtigungen finden Sie in [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

---

## Best Practices

### Auftragstitel

✅ **Gut**:
- "Ring Reparatur - Maria Müller"
- "Halskette 585er Gold - Thomas Schmidt"
- "Trauringe gravieren - Familie Becker"

❌ **Schlecht**:
- "Auftrag 1" (zu vage)
- "Ring" (nicht spezifisch genug)
- "asdfgh" (unverständlich)

**Regel**: Titel sollte Auftragsart + Kunde enthalten.

---

### Beschreibung

✅ **Gut**:
```
Goldring 585 hat Fassung verloren.
Stein muss neu gefasst werden.
Ringweite prüfen und ggf. anpassen.
Kunde wünscht Fertigstellung bis 15.12.
```

❌ **Schlecht**:
```
Ring reparieren
```

**Regel**: So detailliert wie möglich. Alle Kundenwünsche dokumentieren.

---

### Abgabedatum

✅ **Gut**:
- Realistisches Datum setzen
- Puffer für Unvorhergesehenes
- Mit Kunden abgesprochen

❌ **Schlecht**:
- Zu optimistische Termine
- Keine Puffer
- Willkürliche Daten

**Regel**: Lieber einen Tag mehr einplanen als Stress haben.

---

### Status aktualisieren

✅ **Gut**:
- Status immer aktuell halten
- Pending → In Progress beim Start
- In Progress → Completed bei Fertigstellung

❌ **Schlecht**:
- Status monatelang auf "Pending"
- Vergessen, auf "Completed" zu setzen

**Regel**: Status = aktueller Arbeitsstand.

---

### Materialien dokumentieren

✅ **Gut**:
- Alle verwendeten Materialien erfassen
- Korrekte Mengen angeben
- Direkt beim Verbrauch erfassen

❌ **Schlecht**:
- Materialien nachträglich schätzen
- Materialverbrauch vergessen
- Ungenaue Mengen

**Regel**: Lieber zu genau als zu ungenau dokumentieren.

---

### Fotos machen

✅ **Gut**:
- Vorher-Fotos IMMER machen
- Zwischenstände dokumentieren
- Nachher-Fotos für Kundenkommunikation
- Mehrere Winkel fotografieren

❌ **Schlecht**:
- Nur ein Foto
- Schlechte Beleuchtung
- Keine Vorher-Bilder

**Regel**: Ein Foto mehr ist besser als eins zu wenig.

---

## Zusammenfassung

### Workflow-Übersicht

1. **Neuen Auftrag erstellen**
   - Titel, Beschreibung, Kunde, Abgabedatum
2. **Materialien hinzufügen**
   - Welche Edelmetalle/Steine werden verwendet?
3. **Status auf "In Progress" setzen**
   - Arbeit beginnt
4. **Arbeitszeit erfassen**
   - Timer starten/stoppen
5. **Fotos dokumentieren**
   - Vorher, während, nachher
6. **Status auf "Completed" setzen**
   - Auftrag fertiggestellt

### Wichtigste Erkenntnisse

✅ **Aufträge** sind das Herzstück des Systems
✅ **Materialien**, **Zeiten** und **Fotos** gehören zum Auftrag
✅ **Status** zeigt den aktuellen Stand
✅ **Nur Admins** können Aufträge löschen
✅ **Tab-System** strukturiert die Informationen

---

## Weitere Informationen

📖 **Zeiterfassung**: [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md)
📖 **Materialverwaltung**: [FEATURE_MATERIAL_MANAGEMENT.md](FEATURE_MATERIAL_MANAGEMENT.md)
📖 **Kundenverwaltung**: [FEATURE_CUSTOMER_MANAGEMENT.md](FEATURE_CUSTOMER_MANAGEMENT.md)
📖 **Berechtigungen**: [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

---

**Viel Erfolg bei der Auftragsverwaltung!** 📋✨

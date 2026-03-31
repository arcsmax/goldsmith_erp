# Goldsmith ERP - Materialverwaltung

**Lagerbestand und Materialien im Griff**
Version 1.0 | Stand: November 2025

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Was sind Materialien?](#was-sind-materialien)
3. [Materialliste ansehen](#materialliste-ansehen)
4. [Materialdetails verstehen](#materialdetails-verstehen)
5. [Neues Material anlegen](#neues-material-anlegen)
6. [Material bearbeiten](#material-bearbeiten)
7. [Bestand anpassen](#bestand-anpassen)
8. [Niedrige Lagerbestände](#niedrige-lagerbestände)
9. [Lagerwert berechnen](#lagerwert-berechnen)
10. [Materialien zu Aufträgen zuordnen](#materialien-zu-aufträgen-zuordnen)
11. [Berechtigungen](#berechtigungen)
12. [Best Practices](#best-practices)

---

## Überblick

Die **Materialverwaltung** hilft Ihnen, Edelmetalle und Edelsteine im Blick zu behalten und den Materialverbrauch zu dokumentieren.

### Hauptfunktionen

- 📦 **Materialien ansehen** - Alle Materialien auf einen Blick
- ➕ **Materialien anlegen** - Neue Materialien erfassen (Admin)
- ✏️ **Materialien bearbeiten** - Preise und Beschreibungen aktualisieren (Admin)
- 📊 **Bestand anpassen** - Zu- und Abgänge dokumentieren
- ⚠️ **Niedrigstände überwachen** - Warnung bei zu wenig Bestand
- 💰 **Lagerwert berechnen** - Gesamtwert aller Materialien

---

## Was sind Materialien?

**Materialien** in Goldsmith ERP sind Edelmetalle, Edelsteine und andere Verbrauchsmaterialien.

### Typische Materialien

#### Edelmetalle
- Gold 750 (18K)
- Gold 585 (14K)
- Gold 333 (8K)
- Silber 925 (Sterling)
- Platin 950

#### Edelsteine
- Diamant (verschiedene Größen)
- Rubin
- Saphir
- Smaragd
- Halbedelsteine

#### Sonstige
- Fassungen
- Verschlüsse
- Ketten
- Werkzeugverbrauch

### Was gehört zu einem Material?

Jedes Material enthält:

1. **Grundinformationen**
   - Name (z.B. "Gold 750 (18K)")
   - Beschreibung (Details, Besonderheiten)

2. **Wirtschaftsdaten**
   - Stückpreis (Preis pro Einheit)
   - Bestand (aktueller Lagerbestand)
   - Einheit (g, kg, Stück, ct)

3. **Berechnete Werte**
   - Lagerwert (Bestand × Stückpreis)

---

## Materialliste ansehen

### Zur Materialliste navigieren

1. Klicken Sie im Hauptmenü auf **"Materialien"**
2. Sie sehen die **Materialliste**

`[Screenshot: Materialliste mit mehreren Materialien]`

### Was Sie sehen

Die Materialliste zeigt:

| Spalte | Beschreibung |
|--------|--------------|
| **ID** | Material-ID (z.B. #5) |
| **Name** | Materialname |
| **Beschreibung** | Kurzbeschreibung |
| **Stückpreis** | Preis pro Einheit |
| **Bestand** | Aktueller Lagerbestand |
| **Einheit** | Maßeinheit (g, kg, Stück, ct) |

### Sortierung

Standardmäßig alphabetisch nach Namen sortiert.

Klicken Sie auf Spaltenüberschriften, um anders zu sortieren:
- **Name**: A-Z / Z-A
- **Stückpreis**: Niedrigster/Höchster zuerst
- **Bestand**: Wenigster/Meister zuerst

---

## Materialdetails verstehen

### Detailseite öffnen

Klicken Sie in der Materialliste auf ein Material, um die Detailseite zu öffnen.

`[Screenshot: Material-Detailseite]`

### Was Sie sehen

**Grundinformationen**:
- Name
- Beschreibung
- Erstellungsdatum

**Bestandsdaten**:
- Aktueller Bestand
- Einheit
- Stückpreis
- Lagerwert (berechnet)

**Verwendung**:
- In wie vielen Aufträgen verwendet?
- Liste der Aufträge (falls vorhanden)

**Aktionen** (je nach Rolle):
- **Bearbeiten** (nur Admin)
- **Bestand anpassen** (Admin und Goldsmith)
- **Löschen** (nur Admin)

---

## Neues Material anlegen

### ⚠️ Nur für Admins

Nur **Administratoren** können neue Materialien anlegen.

**Warum?**
- Verhindert Duplikate
- Sichert einheitliche Benennung
- Kontrolliert Stammdaten

### Schritt-für-Schritt-Anleitung (für Admins)

#### 1. Neues Material starten

- Klicken Sie auf **"Neues Material"** oder **"+ Material"**
- Das Formular öffnet sich

`[Screenshot: Button "Neues Material"]`

#### 2. Name eingeben (Pflichtfeld)

```
Beispiel: Gold 750 (18K)
```

**Hinweise**:
- Eindeutig und verständlich
- Inkl. Legierung oder Bezeichnung
- Maximal 200 Zeichen

**Gute Namen**:
- Gold 750 (18K)
- Silber 925 (Sterling)
- Diamant 0.5ct VSI
- Platin 950

#### 3. Beschreibung (optional)

```
Beispiel:
Hochwertiges Gelbgold mit 75% Goldanteil.
Für Ringe, Ketten und Anhänger geeignet.
```

- Detailinformationen
- Verwendungszwecke
- Besonderheiten
- Maximal 1000 Zeichen

#### 4. Stückpreis (Pflichtfeld)

```
Beispiel: 55.80
```

**Format**: Euro pro Einheit

- Bei Gold/Silber: Preis pro Gramm
- Bei Steinen: Preis pro Karat oder Stück
- Maximal: 100.000 Euro

> **Tipp**: Aktualisieren Sie Preise regelmäßig (z.B. bei Goldpreisänderungen)

#### 5. Anfangsbestand (Pflichtfeld)

```
Beispiel: 125.5
```

- Aktueller Lagerbestand
- In der gewählten Einheit
- Muss ≥ 0 sein
- Maximal: 1.000.000 Einheiten

#### 6. Einheit (Pflichtfeld)

Wählen Sie die Maßeinheit:
- **g** - Gramm (für Edelmetalle)
- **kg** - Kilogramm (für große Mengen)
- **ct** - Karat (für Edelsteine)
- **Stück** - Für zählbare Teile

```
Beispiel: g (für Gramm)
```

#### 7. Speichern

- Klicken Sie auf **"Material erstellen"**
- Erfolgsmeldung: ✅ "Material erfolgreich erstellt"

`[Screenshot: Erfolgsmeldung]`

---

## Material bearbeiten

### ⚠️ Nur für Admins

Nur **Administratoren** können Materialien bearbeiten.

### Was kann bearbeitet werden?

- ✅ Name
- ✅ Beschreibung
- ✅ Stückpreis
- ✅ Bestand (aber besser über "Bestand anpassen"!)
- ✅ Einheit
- ❌ ID (nicht änderbar)

### Bearbeitungsvorgang

1. Öffnen Sie die Material-Detailseite
2. Klicken Sie auf **"Bearbeiten"**
3. Ändern Sie die gewünschten Felder
4. Klicken Sie auf **"Speichern"**

`[Screenshot: Material bearbeiten]`

### Preis aktualisieren

So aktualisieren Sie z.B. den Goldpreis:

1. Öffnen Sie das Material "Gold 750 (18K)"
2. Klicken Sie auf **"Bearbeiten"**
3. Ändern Sie den **Stückpreis**:
   - Alt: 55.80 €/g
   - Neu: 58.20 €/g
4. Klicken Sie auf **"Speichern"**

> **Wichtig**: Die Preisänderung gilt ab sofort für alle neuen Berechnungen!

---

## Bestand anpassen

### Wer darf Bestände anpassen?

- ✅ **Admins**: Vollzugriff
- ✅ **Goldsmiths**: Können Bestände anpassen
- ❌ **Viewers**: Keine Bestandsänderungen

### Warum Bestände anpassen?

**Zugang (Bestand erhöhen)**:
- Wareneinkauf
- Rücklieferungen
- Inventur-Korrekturen

**Abgang (Bestand reduzieren)**:
- Materialverbrauch für Aufträge
- Ausschuss/Verlust
- Inventur-Korrekturen

### Bestand anpassen

#### Schritt 1: Material öffnen

1. Navigieren Sie zur **Materialliste**
2. Klicken Sie auf das gewünschte Material

#### Schritt 2: Anpassung starten

- Klicken Sie auf **"Bestand anpassen"**
- Dialog öffnet sich

`[Screenshot: Bestand anpassen Dialog]`

#### Schritt 3: Operation wählen

**Option 1: Hinzufügen (+)**
```
Wählen Sie: "Hinzufügen"
Menge: 50
```
→ Bestand wird um 50 erhöht

**Option 2: Abziehen (-)**
```
Wählen Sie: "Abziehen"
Menge: 12.5
```
→ Bestand wird um 12.5 reduziert

#### Schritt 4: Menge eingeben

Geben Sie die Menge ein, die hinzugefügt oder abgezogen werden soll.

**Beispiele**:
- `50` - Fünfzig Gramm Gold hinzufügen
- `0.5` - Ein halbes Karat Diamant abziehen
- `125.8` - 125,8 Gramm Silber abziehen

#### Schritt 5: Speichern

- Klicken Sie auf **"Anpassen"**
- Bestand wird sofort aktualisiert
- Erfolgsmeldung: ✅ "Bestand angepasst"

`[Screenshot: Bestandsänderung Erfolgsmeldung]`

### Automatische Bestandsänderungen

Bestände werden **automatisch reduziert**, wenn:
- Materialien einem Auftrag zugeordnet werden
- Goldsmiths Materialien hinzufügen

Bestände werden **automatisch erhöht**, wenn:
- Materialien von einem Auftrag entfernt werden

> **Wichtig**: Dokumentieren Sie externe Bestandsänderungen (Einkauf, Verlust) manuell!

---

## Niedrige Lagerbestände

### Low-Stock-Alert

Das System warnt Sie automatisch bei niedrigen Lagerbeständen.

### Warnung ansehen

1. Gehen Sie zu **Materialien** → **Niedrige Bestände**
2. Oder klicken Sie auf das **⚠️ Warnung-Icon** (falls vorhanden)

`[Screenshot: Niedrige Bestände Seite]`

### Was Sie sehen

Liste aller Materialien mit Bestand ≤ Schwellenwert:

| Material | Aktueller Bestand | Schwellenwert | Status |
|----------|------------------|---------------|--------|
| Gold 750 | 5.2g | 10g | ⚠️ Niedrig |
| Diamant 0.5ct | 2 Stück | 5 Stück | ⚠️ Niedrig |

### Schwellenwert einstellen

Standardmäßig: **10 Einheiten**

Sie können den Schwellenwert ändern:
```
URL: /materialien/niedrige-bestaende?threshold=20
```
→ Zeigt alle Materialien mit Bestand ≤ 20

### Aktion bei niedrigem Bestand

1. **Nachbestellen**: Kontaktieren Sie Ihren Lieferanten
2. **Bestand auffüllen**: Erfassen Sie den Wareneingang
3. **Bestand anpassen**: Fügen Sie die neuen Materialien hinzu

---

## Lagerwert berechnen

### Was ist der Lagerwert?

Der **Lagerwert** ist der Gesamtwert aller Materialien im Lager.

**Formel**:
```
Lagerwert = Summe(Bestand × Stückpreis)
```

**Beispiel**:
- Gold 750: 125g × 58€/g = 7.250€
- Silber 925: 500g × 0.80€/g = 400€
- Diamant 0.5ct: 10 Stück × 250€/Stück = 2.500€
- **Gesamt**: 10.150€

### Lagerwert ansehen

1. Gehen Sie zu **Materialien** → **Lagerwert**
2. Oder klicken Sie auf **"Lagerwert berechnen"**

`[Screenshot: Lagerwert-Seite]`

### Was Sie sehen

```
Gesamtlagerwert: 10.150,00 €
Währung: EUR
Stand: 15.11.2025, 14:30 Uhr
```

### Wofür nutzen?

- **Buchhaltung**: Für Jahresabschluss
- **Versicherung**: Wert des Lagerbestands
- **Controlling**: Kapitalbi ndung überwachen
- **Planung**: Liquidität prüfen

---

## Materialien zu Aufträgen zuordnen

### Übersicht

Wenn Sie Materialien für einen Auftrag verwenden, ordnen Sie diese dem Auftrag zu.

### Warum zuordnen?

- ✅ **Dokumentation** des Materialverbrauchs
- ✅ **Kostenberechnung** pro Auftrag
- ✅ **Bestandsführung** (automatische Abgänge)
- ✅ **Nachvollziehbarkeit** (was wurde wofür verwendet?)

### Material zuordnen

1. Öffnen Sie den **Auftrag**
2. Gehen Sie zum Tab **"Materialien"**
3. Klicken Sie auf **"+ Material hinzufügen"**
4. Wählen Sie das Material aus der Liste
5. Geben Sie die **Menge** ein
6. Klicken Sie auf **"Hinzufügen"**

`[Screenshot: Material zu Auftrag hinzufügen]`

### Automatische Bestandsreduktion

Wenn Sie ein Material einem Auftrag zuordnen:
- Bestand wird **automatisch reduziert**
- Beispiel: 5.2g Gold → Bestand sinkt von 125g auf 119.8g

### Material wieder entfernen

Wenn Sie ein Material von einem Auftrag entfernen:
- Bestand wird **automatisch erhöht**
- Beispiel: 5.2g Gold werden zurückgebucht → Bestand steigt von 119.8g auf 125g

> **Weitere Informationen**: Ausführliche Anleitung in [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)

---

## Berechtigungen

### Wer darf was?

| Aktion | Admin | Goldsmith | Viewer |
|--------|-------|-----------|--------|
| Materialien ansehen | ✅ | ✅ | ✅ |
| Material erstellen | ✅ | ❌ | ❌ |
| Material bearbeiten | ✅ | ❌ | ❌ |
| Material löschen | ✅ | ❌ | ❌ |
| Bestand anpassen | ✅ | ✅ | ❌ |
| Lagerwert ansehen | ✅ | ✅ | ✅ |
| Niedrige Bestände ansehen | ✅ | ✅ | ✅ |

**Warum diese Aufteilung?**

- **Admins** verwalten Stammdaten (Materialanlage, Preise)
- **Goldsmiths** passen Bestände bei Verbrauch an
- **Viewers** haben Einblick für Planung/Buchhaltung

> **Weitere Informationen**: Details zu allen Berechtigungen finden Sie in [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)

---

## Best Practices

### Materialnamen

✅ **Gut**:
- "Gold 750 (18K)"
- "Silber 925 (Sterling)"
- "Diamant 0.5ct VSI"
- "Platin 950"

❌ **Schlecht**:
- "Gold" (nicht spezifisch)
- "Material 1" (nicht beschreibend)
- "g750" (unklar)

**Regel**: Name sollte Materialart und Legierung/Spezifikation enthalten.

---

### Preise aktualisieren

✅ **Gut**:
- Regelmäßig (z.B. monatlich) Goldpreise aktualisieren
- Bei größeren Schwankungen sofort anpassen
- Dokumentieren, wann Preise geändert wurden

❌ **Schlecht**:
- Jahrelang gleiche Preise
- Preise vergessen zu aktualisieren

**Regel**: Edelmetallpreise mindestens monatlich prüfen.

---

### Bestand dokumentieren

✅ **Gut**:
- Materialverbrauch sofort erfassen
- Einkäufe zeitnah eintragen
- Inventur regelmäßig durchführen

❌ **Schlecht**:
- Materialien nachträglich schätzen
- Monate ohne Bestandsaktualisierung
- Keine Inventur

**Regel**: Bestand = Realität. Dokumentieren Sie zeitnah!

---

### Schwellenwerte nutzen

✅ **Gut**:
- Schwellenwerte für häufig verwendete Materialien setzen
- Regelmäßig Niedrigstände prüfen
- Rechtzeitig nachbestellen

❌ **Schlecht**:
- Warnung ignorieren
- Erst bestellen, wenn Bestand bei 0
- Keine Überwachung

**Regel**: Prävention ist besser als Engpässe!

---

### Lagerwert überwachen

✅ **Gut**:
- Monatlich Lagerwert berechnen
- Trends beobachten (steigt/sinkt?)
- Für Jahresabschluss dokumentieren

❌ **Schlecht**:
- Nie Lagerwert prüfen
- Kapitalbindung ignorieren

**Regel**: Lagerwert ist wichtige Kennzahl!

---

## Zusammenfassung

### Workflow-Übersicht

1. **Materialien anlegen** (Admin)
   - Name, Preis, Anfangsbestand, Einheit
2. **Materialien für Aufträge verwenden**
   - Zuordnung zu Aufträgen
   - Automatische Bestandsreduktion
3. **Bestand überwachen**
   - Niedrigstände prüfen
   - Rechtzeitig nachbestellen
4. **Bestand anpassen**
   - Nach Einkauf: Hinzufügen
   - Bei Verlust: Abziehen
5. **Preise aktualisieren** (Admin)
   - Regelmäßig Edelmetallpreise anpassen

### Wichtigste Erkenntnisse

✅ **Materialien** sind zentrale Stammdaten
✅ **Nur Admins** legen Materialien an
✅ **Goldsmiths** passen Bestände an
✅ **Automatische Bestandsführung** bei Auftragszuordnung
✅ **Niedrigstände überwachen** verhindert Engpässe
✅ **Lagerwert** ist wichtige Kennzahl

---

## Weitere Informationen

📖 **Auftragsverwaltung**: [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)
📖 **Berechtigungen**: [USER_ROLES_PERMISSIONS.md](USER_ROLES_PERMISSIONS.md)
📖 **Berichte** (zukünftig): Materialverbrauch-Berichte

---

**Behalten Sie Ihre Materialien im Griff!** 💎📊

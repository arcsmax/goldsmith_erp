# Goldsmith ERP - Tägliche Arbeitsabläufe

**Typische Workflows für den Goldschmied-Alltag**
Version 1.0 | Stand: November 2025

---

## Überblick

Diese Anleitung zeigt Ihnen **praktische Arbeitsabläufe** für den täglichen Einsatz von Goldsmith ERP.

### Für wen ist diese Anleitung?

- 🔨 **Goldsmiths** - Werkstatt-Mitarbeiter
- 👑 **Admins** - Geschäftsführer, Betriebsleiter
- 👁️ **Viewers** - Aushilfen (eingeschränkt)

---

## Morgen-Routine

### Schritt 1: Anmelden

1. Öffnen Sie **http://localhost:3000** (oder Ihre Server-URL)
2. Geben Sie **E-Mail** und **Passwort** ein
3. Klicken Sie auf **"Anmelden"**

**Test-Login** (für Demo):
```
E-Mail: goldsmith@goldsmith.local
Passwort: goldsmith123
```

---

### Schritt 2: Dashboard prüfen

Nach dem Login sehen Sie das **Dashboard**.

**Was sollten Sie prüfen?**

✅ **Neue Aufträge**:
- Gibt es neue Aufträge mit Status "Pending"?
- Welche Aufträge sind dringend?

✅ **Laufende Aufträge**:
- Welche Aufträge sind "In Progress"?
- An welchem Auftrag arbeite ich heute weiter?

✅ **Material-Warnungen**:
- Gibt es rote Warnungen (Low Stock)?
- Muss ich Material bestellen?

**Beispiel**:
```
Dashboard zeigt:
- 3 neue Aufträge (Pending)
- 2 laufende Aufträge (In Progress)
- 1 Material-Warnung (Gold 750 - nur noch 10g)
→ Entscheidung: Gold nachbestellen!
```

---

### Schritt 3: Prioritäten setzen

Fragen Sie sich:

1. **Welcher Auftrag ist am dringendsten?** (Abgabedatum prüfen)
2. **Gibt es Aufträge, die auf Material warten?**
3. **Kann ich einen Auftrag heute fertigstellen?**

**Tipp**: Sortieren Sie Aufträge nach **Abgabedatum** (aufsteigend).

---

## Neuen Auftrag anlegen

### Szenario: Kunde kommt mit Auftrag

Ein Kunde möchte einen **Ring anfertigen** lassen.

### Schritt-für-Schritt

1. Klicken Sie auf **"Aufträge"** → **"Neuer Auftrag"**
2. Geben Sie ein:
   - **Titel**: "Ehering Gold 750"
   - **Kunde**: Wählen Sie Kunde aus Liste (oder erstellen Sie neuen Kunden)
   - **Beschreibung**: "Ehering in 750er Gold, Größe 58, poliert"
   - **Abgabedatum**: Wählen Sie Datum (z.B. in 2 Wochen)
3. Klicken Sie auf **"Auftrag erstellen"**

**Ergebnis**:
- Neuer Auftrag mit Status "Pending"
- Auftrag erscheint in der Auftragsliste

---

### Materialien hinzufügen

1. Öffnen Sie den Auftrag
2. Gehen Sie zum Tab **"Materialien"**
3. Klicken Sie auf **"Material hinzufügen"**
4. Wählen Sie:
   - **Material**: "Gold 750"
   - **Menge**: 10 (Gramm)
5. Klicken Sie auf **"Hinzufügen"**

**Wichtig**: Der Material-Bestand wird **automatisch reduziert**!

```
Bestand Gold 750:
Vorher: 100g
Nachher: 90g (100g - 10g)
```

Siehe: [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)

---

## An einem Auftrag arbeiten

### Szenario: Arbeit an Ehering beginnen

Sie beginnen mit der Arbeit am Ehering.

### Schritt 1: Status ändern

1. Öffnen Sie den Auftrag
2. Ändern Sie Status von **"Pending"** zu **"In Progress"**
3. Klicken Sie auf **"Speichern"**

**Ergebnis**: Auftrag erscheint unter "Laufende Aufträge".

---

### Schritt 2: Zeiterfassung starten

**Hinweis**: Die UI wird in Woche 2-3 fertiggestellt. Hier beschreiben wir die geplante Funktionsweise.

1. Gehen Sie zum Tab **"Arbeit"** (Abschnitt Zeiterfassung)
2. Klicken Sie auf **"Zeit starten"**
3. Wählen Sie **Aktivität**: "Sägen" (oder passende Aktivität)
4. Optional: Geben Sie **Notizen** ein

**Ergebnis**: Timer läuft, Sie können mit der Arbeit beginnen.

Siehe: [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md)

---

### Schritt 3: Während der Arbeit

**Arbeiten Sie am Auftrag** - das System trackt Ihre Zeit.

**Wenn Sie unterbrochen werden** (z.B. Telefon): Es gibt keinen manuellen
"Pause"-Button mehr in der Zeiterfassung. Unterbrechungen werden derzeit
über den QR-/NFC-Scan am Werkbank-Platz erfasst (siehe
[FEATURE_TIME_TRACKING.md](features/FEATURE_TIME_TRACKING.md)).

**Wenn Sie die Aktivität wechseln** (z.B. von Sägen zu Löten):
1. Klicken Sie auf **"Zeit stoppen"**
2. Klicken Sie auf **"Zeit starten"**
3. Wählen Sie neue Aktivität: "Löten"

---

### Schritt 4: Zeiterfassung stoppen

Wenn Sie fertig sind:

1. Klicken Sie auf **"Zeit stoppen"**
2. Geben Sie ein:
   - **Komplexität**: 1-5 Sterne (Schwierigkeitsgrad)
   - **Qualität**: 1-5 Sterne (Qualität Ihrer Arbeit)
   - **Notizen**: Optional
3. Klicken Sie auf **"Speichern"**

**Beispiel**:
```
Aktivität: Sägen
Dauer: 45 Minuten
Komplexität: 3/5 (mittelschwer)
Qualität: 4/5 (gut)
Notizen: "Ringe-Rohling vorbereitet"
```

---

## Fotos dokumentieren

### Szenario: Arbeitsschritte fotografieren

Sie möchten den Fortschritt dokumentieren.

### Schritt-für-Schritt

1. Öffnen Sie den Auftrag
2. Gehen Sie zum Tab **"Fotos"**
3. Klicken Sie auf **"Foto hochladen"**
4. Wählen Sie Foto (max. 5 MB, JPG/PNG)
5. Optional: Geben Sie **Beschreibung** ein (z.B. "Nach dem Sägen")
6. Klicken Sie auf **"Hochladen"**

**Vorteile**:
- Kunde kann Fortschritt sehen
- Dokumentation für spätere Referenz
- Nachvollziehbarkeit

**Tipp**: Fotografieren Sie wichtige Arbeitsschritte!

Siehe: [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md)

---

## Auftrag fertigstellen

### Szenario: Ehering ist fertig

Der Ehering ist poliert und fertig zur Abholung.

### Schritt-für-Schritt

1. Öffnen Sie den Auftrag
2. Ändern Sie Status zu **"Completed"** 🟢
3. Optional: Laden Sie **Foto des fertigen Produkts** hoch
4. Klicken Sie auf **"Speichern"**

**Ergebnis**:
- Auftrag ist abgeschlossen
- Kunde kann benachrichtigt werden
- Zeiteinträge und Materialverbrauch sind dokumentiert

---

## Material nachbestellen

### Szenario: Material-Warnung

Das Dashboard zeigt: **Gold 750 - Nur noch 10g** (rot markiert).

### Schritt-für-Schritt

**Option 1: Material bestellen** (außerhalb des Systems):
1. Bestellen Sie Material bei Ihrem Lieferanten
2. Warten Sie auf Lieferung

**Option 2: Nach Lieferung - Bestand anpassen**:
1. Klicken Sie auf **"Materialien"**
2. Öffnen Sie **"Gold 750"**
3. Klicken Sie auf **"Bestand anpassen"**
4. Wählen Sie **"Hinzufügen (+)"**
5. Geben Sie Menge ein (z.B. 100g)
6. Klicken Sie auf **"Speichern"**

**Ergebnis**:
```
Bestand Gold 750:
Vorher: 10g (rot markiert)
Nachher: 110g (grün, keine Warnung mehr)
```

Siehe: [FEATURE_MATERIAL_MANAGEMENT.md](FEATURE_MATERIAL_MANAGEMENT.md)

---

## Feierabend-Routine

### Schritt 1: Offene Zeiteinträge prüfen

**Wichtig**: Alle Zeiteinträge sollten gestoppt sein!

1. Gehen Sie zu **"Zeiterfassung"** (falls verfügbar)
2. Prüfen Sie: Läuft noch ein Timer?
3. Falls ja: **Stoppen Sie den Timer**

**Tipp**: Vergessen Sie nicht, Ihre Zeit zu stoppen!

---

### Schritt 2: Status-Update geben

Fragen Sie sich:

- ✅ Welche Aufträge habe ich heute bearbeitet?
- ✅ Gibt es Aufträge, die morgen fertig werden?
- ✅ Brauche ich Material für morgen?

**Optional**: Notieren Sie sich Prioritäten für morgen.

---

### Schritt 3: Abmelden

1. Klicken Sie oben rechts auf Ihr **Profil**
2. Wählen Sie **"Abmelden"**

**Hinweis**: Aus Sicherheitsgründen sollten Sie sich immer abmelden!

---

## Typische Szenarien

### Szenario 1: Eilauftrag kommt rein

**Situation**: Kunde braucht Ring **morgen**.

**Workflow**:
1. ✅ Auftrag anlegen (Titel: "EILAUFTRAG: Ring...")
2. ✅ Abgabedatum: Morgen
3. ✅ Materialien hinzufügen
4. ✅ Status: "In Progress"
5. ✅ Sofort mit Arbeit beginnen
6. ✅ Zeiterfassung starten

**Tipp**: Kennzeichnen Sie Eilaufträge im Titel (z.B. "EILAUFTRAG: ...").

---

### Szenario 2: Material fehlt

**Situation**: Sie wollen an Auftrag arbeiten, aber Material ist aus.

**Workflow**:
1. ❌ Stoppen Sie die Zeiterfassung (falls gestartet)
2. ✅ Fügen Sie Unterbrechung hinzu: "Warten auf Material"
3. ✅ Bestellen Sie Material
4. ✅ Arbeiten Sie an anderem Auftrag weiter
5. ✅ Nach Lieferung: Bestand anpassen
6. ✅ Arbeit fortsetzen

---

### Szenario 3: Kunde möchte Änderung

**Situation**: Kunde ruft an und möchte Änderung (z.B. andere Ringgröße).

**Workflow**:
1. ✅ Öffnen Sie den Auftrag
2. ✅ Klicken Sie auf "Bearbeiten"
3. ✅ Ändern Sie Beschreibung (z.B. "Größe 60 statt 58")
4. ✅ Optional: Fügen Sie Notiz hinzu im Tab "Zeiteinträge"
5. ✅ Klicken Sie auf "Speichern"

**Tipp**: Dokumentieren Sie Änderungen in den Notizen!

---

## Wöchentliche Aufgaben

### Montags

✅ **Wochenplanung**:
- Welche Aufträge müssen diese Woche fertig werden?
- Reicht das Material?
- Gibt es Eilaufträge?

---

### Freitags

✅ **Wochenabschluss**:
- Alle laufenden Aufträge prüfen
- Zeiteinträge der Woche prüfen
- Material für nächste Woche bestellen

**Für Admins**:
- Berichte erstellen (falls verfügbar)
- Zeiteinträge aller Mitarbeiter prüfen

---

## Tipps für effizientes Arbeiten

### 1. Aufträge sortieren

✅ **Sortieren Sie nach Abgabedatum** (aufsteigend)
✅ Arbeiten Sie an **dringenden Aufträgen** zuerst

---

### 2. Zeiterfassung nicht vergessen

✅ **Timer starten**, wenn Sie mit Arbeit beginnen
✅ **Timer stoppen**, wenn Sie fertig sind
✅ **Unterbrechungen dokumentieren** (wichtig für Auswertung)

---

### 3. Materialien im Blick behalten

✅ **Prüfen Sie täglich** den Material-Bestand
✅ **Bestellen Sie rechtzeitig** Nachschub
✅ **Mindestbestand anpassen** (falls nötig)

---

### 4. Fotos dokumentieren

✅ **Fotografieren Sie wichtige Arbeitsschritte**
✅ Kunden schätzen **visuelle Dokumentation**
✅ Hilft bei **späteren Fragen**

---

### 5. Regelmäßig speichern

✅ Klicken Sie regelmäßig auf **"Speichern"**
✅ Browser kann abstürzen - **Datenverlust vermeiden**!

---

## Checkliste: Tägliche Routine

### Morgens

- [ ] Anmelden
- [ ] Dashboard prüfen (neue Aufträge, Material-Warnungen)
- [ ] Prioritäten setzen (nach Abgabedatum)
- [ ] Material prüfen (reicht es für heute?)

### Während der Arbeit

- [ ] Auftrag öffnen
- [ ] Status auf "In Progress" setzen
- [ ] Zeiterfassung starten
- [ ] Materialien hinzufügen (falls nötig)
- [ ] Fotos hochladen (Arbeitsschritte dokumentieren)

### Abends

- [ ] Zeiterfassung stoppen (alle Timer!)
- [ ] Auftrag-Status aktualisieren (falls fertig: "Completed")
- [ ] Morgen-Prioritäten notieren
- [ ] Abmelden

---

## Zusammenfassung

✅ **Morgens**: Dashboard prüfen, Prioritäten setzen
✅ **Während der Arbeit**: Status ändern, Zeit tracken, dokumentieren
✅ **Abends**: Timer stoppen, Status aktualisieren, abmelden
✅ **Tipps**: Nach Abgabedatum sortieren, Zeiterfassung nicht vergessen, Fotos dokumentieren

---

## Siehe auch

- [USER_GETTING_STARTED.md](USER_GETTING_STARTED.md) - Erste Schritte
- [FEATURE_ORDER_MANAGEMENT.md](FEATURE_ORDER_MANAGEMENT.md) - Aufträge verwalten
- [FEATURE_MATERIAL_MANAGEMENT.md](FEATURE_MATERIAL_MANAGEMENT.md) - Materialien verwalten
- [FEATURE_TIME_TRACKING.md](FEATURE_TIME_TRACKING.md) - Zeit tracken
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Probleme lösen
- [FAQ.md](FAQ.md) - Häufig gestellte Fragen

---

**Effizientes Arbeiten mit Goldsmith ERP!** ⚡🔨✨

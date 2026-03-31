# Ideen-Sammlung: Anne - Programm Goldschmiede

> Originale Feature-Anforderungen und Ideen einer Goldschmiedin.
> Dieses Dokument enthaelt die ungefilterten Anforderungen aus der Praxis.

---

## Modul-Uebersicht

| Nr. | Modul | Kernidee |
|-----|-------|----------|
| 1 | [Auftragsmodul (Die Basis)](#1-auftragsmodul-die-basis) | Digitale Tuete mit Pflichtfeldern |
| 2 | [Kalkulations- und Arbeitsmodul](#2-kalkulations--und-arbeitsmodul) | Soll vs. Ist, Angebot-zu-Rechnung |
| 3 | [Lager- und Bestandsverwaltung](#3-lager--und-bestandsverwaltung) | Edelsteine, Metalle, Werkzeuge mit Bildern |
| 4 | [Altgold-Verrechnung](#4-altgold-verrechnung) | Feingold-Berechnung, Foto, digitale Signatur |
| 5 | [Terminverwaltung & Erinnerung](#5-terminverwaltung--proaktive-erinnerung) | Kalender mit Ampel, automatische Erinnerungen |
| 6 | [360-Grad-Kundenprofil](#6-das-360-grad-kundenprofil) | Mass-Bibliothek, visuelle Historie |
| 7 | [Mitarbeiter-Dashboard & Messaging](#7-mitarbeiter-dashboard--internes-messaging) | Rollenbasierte Ansichten, Digitale Post-its |

---

## 1. Auftragsmodul (Die Basis)

### Das zentrale Auftrags-Dashboard (Die "Digitale Tuete")

Dies ist das Herzstueck, das den gesamten Lebenszyklus eines Unikats abbildet:

**Kundenstammdaten:**
- Hinterlegung von Adressen und Historie

**Input-Maske (Die "Pflichtfelder-Garantie"):**
- Digitales Pop-up fuer Pflichtangaben (Legierung, Oberflaeche, Ringmass, etc.)
- Wenn Felder leer bleiben, verhindert das System den Abschluss des Auftrags-Inputs
- **Logik:** Erst wenn alle Pflichtfelder befuellt sind, wird der Auftrag im System aktiv ("Auftrag bestaetigt")

**Status-Pflicht:**
- Kein Auftrag ohne Vollstaendigkeitspruefung

---

## 2. Kalkulations- und Arbeitsmodul

> Hier schliesst du die Luecke zwischen Angebot und Realitaet.

**Vorkalkulation:**
- Das Programm zieht sich aktuelle Edelmetall- und Edelsteinpreise (aus deinem Verzeichnis)
- Berechnet basierend auf geschaetzten Arbeitszeiten ein verbindliches Angebot
- Katalog-System fuer Arbeitsschritte (Fassen, Loeten) und Materialien

**Digitaler Arbeitszettel:**
- Waehrend der Produktion traegst du die Ist-Werte ein:
  - Tatsaechliches Metallgewicht nach Verschnitt
  - Tatsaechliche Arbeitszeit

**Nahtlose Uebergabe (Soll vs. Ist):**
- System vergleicht Soll (Angebot) mit Ist (Arbeitszettel)
- Generiert daraus per Klick die Rechnung
- Keine manuelle Uebertragung mehr - minimiert Fehlerquellen fuer die Buchhaltung
- Automatisierte Uebergabe an das Rechnungsprogramm

---

## 3. Lager- und Bestandsverwaltung

> Damit sparst du dir das taegliche Suchen und Nachschlagen.

**Materialverzeichnis:**
- Edelmetalle und Steine mit Stammdaten und aktuellem Bestand

**Verbrauchsmaterial-Katalog:**
- Datenbank fuer Werkzeuge (Schmirgelleinen, Saegeblaetter etc.) inklusive:
  - **Produktbild** (zur Identifikation fuer Dritte/Buerokraefte)
  - **Verknuepfung** zu den jeweiligen Haendler-Webshops oder Bestellnummern

**Bestands-Warnung:**
- Wenn ein kritischer Punkt unterschritten wird, gibt das Programm einen Hinweis zur Nachbestellung

**Woechentliche Sammel-Einkaufsliste:**
- Nach Lieferanten gruppiert fuer effizientes Bestellen

---

## 4. Altgold-Verrechnung

> Damit dies kein "vergessener Posten" mehr bleibt, muss es Teil des initialen Pop-up-Prozesses bei der Auftragserstellung sein.

### Der "Altgold-Check" im Pop-up

Wenn du einen neuen Auftrag anlegst, erscheint die Abfrage: **"Altgold vorhanden? Ja/Nein"**.
Wenn "Ja" gewaehlt wird, oeffnet sich eine spezifische Eingabemaske.

### Strukturierte Erfassung

**Foto-Upload:**
- Direkt in der Maske Fotos der angelieferten Stuecke machen oder hochladen
- Fuer Dokumentation und Absicherung

**Legierungs-Rechner:**
- Legierung waehlen (z.B. 585er, 750er)
- Gesamtgewicht eingeben
- Programm rechnet automatisch den Feingehalt aus

**Listen-Funktion:**
- Mehrere Positionen hinzufuegen (z.B. 10g 585er Gelbgold + 5g 333er Weissgold)
- Programm summiert den gesamten Feingoldgehalt
- Berechnet tagesaktuellen oder fixen Wert fuer die Verrechnung

### Digitale Unterschrift (Rechtssicherheit)

- System generiert aus den eingegebenen Daten sofort ein **Ankaufsbeleg-Dokument**
- Kunde kann direkt auf einem Tablet unterschreiben (**Digitale Signatur**)
- Bestaetigung der Abgabe UND Zustimmung zur verrechneten Summe direkt im Auftrag hinterlegt

### Buchhaltungskonforme Schnittstelle

- Daten digital erfasst und "festgeschrieben"
- Betrag fliesst bei finaler Rechnungsstellung automatisch als **"Gutschrift Altgold"** in die Rechnung ein

---

## 5. Terminverwaltung & Proaktive Erinnerung

### Der "Deadline-Flow" bei Auftragseingang

Bei der Auftragserfassung im Pop-up-Fenster werden Pflichtfelder fuer Termine hinterlegt:

- **Abgabetermin (Ziel-Datum):** Wann muss der Schmuck fertig sein?
- **Anprobe-Datum:** (Optional, aber empfohlen) Wenn das Schmuckstueck komplex ist
  - Wenn noch kein Datum feststeht: Status "Warten auf Anprobe"

### Digitale Kalender-Integration & Status-Monitoring

Zentrale Dashboard-Ansicht ("Mein Kalender") mit **optischer Ampel**:

| Farbe | Bedeutung |
|-------|-----------|
| Gruen | Alles im Zeitplan |
| Gelb | Anprobe steht an / Teil ist in Arbeit |
| Rot | Deadline rueckt kritisch nah (z.B. in 2 Tagen) |

### Automatisierte Erinnerungen (Push-Notifications / E-Mail)

**Tag vor Abholung:**
> "Morgen: Kundenname XY, Artikel: Ring, ist der Stein schon gefasst?"

**Follow-up bei Anprobe:**
> Wenn Status "Anprobe offen" ist und du den Status auf "Rohfassung fertig" aenderst:
> "Anprobe fuer Kunden XY jetzt moeglich - Termin vereinbaren?"

---

## 6. Das 360-Grad-Kundenprofil

> Die digitale Kundenkartei - die "Akte", in der alles zusammenlaeuft, was jemals mit diesem Kunden passiert ist.

### Basis-Daten & CRM

- Adresse, Kontaktmoeglichkeiten
- **Geburtstag** (fuer Marketing/Gutscheine)

### Die "Mass-Bibliothek"

Hier hinterlegst du dauerhaft:
- **Ringgroessen**
- **Kettenlaengen**
- **Spezielle Vorlieben** (z.B. "bevorzugt Platin", "allergisch gegen Nickel")

> Das spart jedes Mal das Messen.

### Historie (Die "Lebenslauf-Funktion")

Jedes Schmuckstueck, das der Kunde bei dir gekauft oder anfertigen lassen hat, wird automatisch in einer Liste gefuehrt.

**Visuelle Historie** - jedes Teil ist verknuepft mit:
- Dem **Original-Foto** des gefertigten Unikats
- Dem **Auftrags-Dokument** (was wurde damals besprochen?)
- Der **Rechnung** (als PDF im Zugriff)

---

## 7. Mitarbeiter-Dashboard & internes Messaging

### A. Rollenbasiertes Dashboard (Die "Was-muss-ich-tun?"-Ansicht)

Jeder Mitarbeiter sieht beim Login nur das, was fuer ihn relevant ist:

| Rolle | Fokus | Inhalte |
|-------|-------|---------|
| **Goldschmied** | Produktion | Arbeitszettel, aktuelle Steine, Deadlines |
| **Buerokraft** | Administration | Auftragseingang, Materialbestellungen, Rechnungsabschluss |

**Priorisierung:**
- Jeder Mitarbeiter hat eine **"To-Do-Liste"**, die sich automatisch aus den Auftrags-Deadlines fuellt
- Ein roter Punkt bei einem Auftrag signalisiert sofort: **"Hier brennt es, heute ist Deadline!"**

### B. Das "Digitale Post-it" (Kontextbezogene Kommunikation)

> Anstatt Zettel zu schreiben oder sich im Laden zu suchen.

Innerhalb jedes Auftrags gibt es eine **Kommentar-Funktion**:

- **Die Logik:** Jedes Kommentar ist direkt mit der Auftrags-ID verknuepft
- **Beispiel:** Der Goldschmied schreibt in den Auftrag:
  > "Kunde hat bei Anprobe Wunsch nach Zargenfassung statt Krabbenfassung geaeussert. Bitte Mehrpreis pruefen."
- **Die Wirkung:** Die Buerokraft bekommt eine Benachrichtigung und kann direkt den Preis im Kalkulationsmodul anpassen, ohne den Goldschmied bei der Arbeit zu stoeren

### C. Uebergabe-Protokoll (Der "Stabuebergabe"-Button)

Wenn ein Schritt beendet ist, wird der Status des Auftrags geaendert:

**Beispiel:** "In Bearbeitung" -> "Bereit fuer Fassen"

Das System benachrichtigt automatisch den entsprechenden Mitarbeiter:
> "Ring fuer Kunde XY liegt bereit zur Fassung."

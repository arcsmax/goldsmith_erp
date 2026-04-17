# eIDAS-Klassifikation der Altgold-Kundensignaturen

**Scope:** `quotes.customer_signature_data` und `scrap_gold.signature_data` (beides Text-Spalten mit base64-PNG-Blobs einer per Touch/Stylus/Maus gezeichneten Signatur).
**Rechtsrahmen:** EU-Verordnung Nr. 910/2014 (eIDAS), ZPO §371a (Beweiswert elektronischer Dokumente), GwG §§ 10, 12 (Identifikationspflicht im Altgold-Handel).
**Auditorin:** Anna Becker (DPO/TUeV) · **Datum:** 2026-04-17 · **Verweis:** `V1.1-POST-WAVE5-COMPLIANCE-AUDIT.md` §5 Punkt 4, `VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN.md` V1.1-009.

**Kernaussage vorab:** Die aktuelle Signatur-Erfassung ist eine **einfache elektronische Signatur** nach Art. 3 Nr. 10 eIDAS. Fuer den Standard-Altgold-Ankauf im Werkstatt-Kontext ist das rechtlich ausreichend. Fuer Transaktionen > 5 000 € oder bei erhoehtem Streit-Risiko empfehle ich fuer V1.2 die Ergaenzung um ein qualifiziertes Signaturverfahren.

---

## 1. eIDAS-Klassifikation der aktuellen Erfassungsmethode

Die App erfasst Signaturen als **Raster-Bild (base64-PNG)** auf einem Touchscreen/Tablet/Grafiktablet. Dies wird gegen die drei Stufen der eIDAS-Verordnung geprueft:

| Stufe | eIDAS Art. 3 | Kriterien | Aktuelle Erfassung |
|---|---|---|---|
| **Einfache elektronische Signatur** (SES) | **Nr. 10** | Daten in elektronischer Form, die anderen elektronischen Daten beigefuegt sind und zur Unterzeichnung dienen. | **JA** — base64-PNG beigefuegt zum Altgold-Datensatz. |
| **Fortgeschrittene elektronische Signatur** (AES) | **Nr. 11** | Muss (a) eindeutig dem Unterzeichner zugeordnet sein, (b) Identifizierung ermoeglichen, (c) mit Mitteln erstellt, die der Unterzeichner unter alleiniger Kontrolle hat, und (d) mit den signierten Daten so verknuepft sein, dass nachtraegliche Aenderungen erkennbar sind. | **NEIN** — keine biometrische Bindung (Druckkurve, Geschwindigkeit), keine Hash-Verkettung mit Dokumenten-Inhalt, keine Tamper-Detection auf dem Raster-PNG. |
| **Qualifizierte elektronische Signatur** (QES) | **Nr. 12** | AES + erstellt von einer qualifizierten Signaturerstellungseinheit (QSCD) + beruht auf qualifiziertem Zertifikat eines Vertrauensdiensteanbieters. | **NEIN** — weder QSCD noch qualifiziertes Zertifikat. |

**Schlussfolgerung:** Die heutige Implementierung ist eine **einfache elektronische Signatur (SES)** nach Art. 3 Nr. 10 eIDAS.

---

## 2. Rechtliche Implikationen fuer den Altgold-Ankauf

### 2.1 Beweiswert nach deutschem Prozessrecht

**§ 371a Abs. 1 ZPO** regelt: „Auf private elektronische Dokumente, die mit einer qualifizierten elektronischen Signatur versehen sind, finden die Vorschriften ueber die Beweiskraft privater Urkunden entsprechende Anwendung." Das heisst im Umkehrschluss: eine einfache elektronische Signatur hat **nicht** automatisch die volle Beweiskraft einer handschriftlichen Unterschrift nach § 440 ZPO, sondern unterliegt der **freien Beweiswuerdigung** nach § 286 ZPO.

**In der Praxis bedeutet das:**
- Das Gericht kann der einfachen Signatur einen Beweiswert zumessen, wenn Begleitumstaende (Foto, Zeitstempel, Mitarbeiter-Zeuge) die Authentizitaet stuetzen.
- Beweislast liegt im Zweifel bei der Werkstatt: bestreitet der Kunde die Signatur, muss die Werkstatt die Echtheit darlegen — mit einer qualifizierten Signatur waere die Beweislast umgekehrt.
- Faelschung ist nicht unmoeglich, aber bei Kombination mit Foto + Zeitstempel + Mitarbeiter-Identitaet schwer plausibel zu machen.

### 2.2 Zivilrechtliche Formvorschrift

Der Altgold-Ankauf ist ein **Kaufvertrag nach § 433 BGB** zwischen Werkstatt und Privatkunde. Es besteht **keine gesetzliche Schriftform-Pflicht nach § 126 BGB**, solange kein ausdruecklich der Schriftform unterworfenes Nebengeschaeft vorliegt (z. B. Ratenzahlung ueber Verbraucherdarlehensrecht). Eine einfache elektronische Signatur ist daher **ausreichend** fuer das Kernvertragsverhaeltnis.

### 2.3 Geldwaeschegesetz-Pflichten (GwG)

Der GwG §§ 10, 12 verlangen die **Identifikation des Vertragspartners** bei Bartransaktionen ab bestimmten Schwellen (Gueterhaendler ab 10 000 € grundsaetzlich, bei hohem Bargeldanteil ab 2 000 €). GwG-konforme Identifikation bedeutet: **Vorlage eines amtlichen Ausweises + Erfassung der Ausweisdaten**, nicht eine Signatur. Die Signatur ist hier kein Ersatz fuer die Ausweiskopie, sondern ein zusaetzlicher Nachweis der Willensuebereinstimmung.

### 2.4 Streitige Transaktionen

Wenn ein Kunde spaeter behauptet, er habe **nicht unterschrieben** oder sei nicht der Verkaeufer gewesen:

- **Ohne Zusatzmassnahmen:** einfache Signatur allein ist schwer zu verteidigen — das PNG laesst sich theoretisch auch nachtraeglich erzeugen.
- **Mit Zusatzmassnahmen (Foto des Kunden beim Ankaufsvorgang, Foto des Ausweises, Zeitstempel, Mitarbeiter-Zeuge, Kassen-Beleg-Nummer):** plausibler Beweis zusammengesetzt. Viele Zivilgerichte akzeptieren das heute routinemaessig in Pfandleihe- und Altgold-Kontexten.

---

## 3. Empfehlung fuer V1.1

**Die einfache elektronische Signatur bleibt fuer V1.1.** Rechtlich zulaessig, praxisgerecht, und der Standard-Altgold-Ankauf in einer Werkstatt mit 5 Mitarbeitern und persoenlichem Kunden-Kontakt generiert kaum Streitfaelle.

**Verbindliche V1.1-Begleitmassnahmen (zur Beweiswert-Staerkung, bereits teils im Code):**

1. **Foto des angekauften Gegenstandes** im selben Datensatz (`scrap_gold_items.photo_path`) — bereits vorhanden.
2. **Foto der Ausweisvorderseite** bei GwG-Schwelle (Upload-Feld ergaenzen, wenn `total_price ≥ GWG_IDENTIFICATION_THRESHOLD` — **neue Anforderung**, noch nicht in V1.1 spec’d). Deadline: **in V1.1.5 Slice 12 aufnehmen**, Kostenschaetzung 1 PT.
3. **Zeitstempel der Signatur** im Datensatz (bereits vorhanden als `created_at`).
4. **Mitarbeiter-Identitaet** der anwesenden Ankaufs-Person (`scrap_gold.created_by` FK, bereits vorhanden).
5. **Kombination Signatur + Foto-mit-Signatur in einem Beleg-PDF** (`receipt_pdf_path`). Prueft Max, ob das schon passiert — falls nicht, V1.1-Hotfix.

**Mitarbeiter-Schulung:** vor jedem Altgold-Ankauf > 1 000 € ist die Identitaet zu verifizieren und der Ausweis zu fotografieren. Dokumentiere ich im `DAILY_WORKFLOWS.md`-Update (out-of-scope hier, H-Item).

---

## 4. Empfehlung fuer V1.2 — qualifizierte Signatur fuer grosse Transaktionen

Fuer Altgold-Ankaeufe ueber einer Schwelle (Empfehlung: **5 000 €** pro Einzeltransaktion, Auswertung aus bestehenden Daten sinnvoll) sollte V1.2 eine **qualifizierte elektronische Signatur** (QES) nach Art. 3 Nr. 12 eIDAS ergaenzen. Optionen fuer kleinbetriebliche Integration:

| Option | Anbieter | Kosten (Richtwert) | Aufwand |
|---|---|---|---|
| **BundID** (oeffentlich) | Bundesregierung | Buerger-Konto kostenlos | Kunde muss Konto haben; nicht alle Kunden akzeptieren es |
| **Sign-me** (Deutsche Post/D-Trust) | Vertrauensdiensteanbieter | ca. 1–3 € pro Signatur | Integration ueber REST-API; Kunde erhaelt SMS-TAN |
| **FP-Sign (Francotyp Postalia)** | Vertrauensdiensteanbieter | ab 0.50 € pro Signatur | Vor-Ort-Tablet oder Browser-Flow |
| **DocuSign EU Advanced** | DocuSign Germany GmbH | Abo-Modell | Integrations-Aufwand hoch, fuer Handwerk ueberdimensioniert |

**Empfehlung:** fuer V1.2 mit `sign-me` (D-Trust) evaluieren, ist deutscher Vertrauensdiensteanbieter, REST-API, per-Signatur-Abrechnung passt zur niedrigen Volumen-Realitaet einer 5-Personen-Werkstatt.

**Designziel V1.2:** automatische QES-Nachforderung, wenn `total_price ≥ 5 000 €`. Unter der Schwelle weiter einfache Signatur.

---

## 5. Aktion im Verzeichnis von Verarbeitungstaetigkeiten

Der Altgold-Eintrag (V1.1-009 in `VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN.md`) referenziert dieses Dokument und klassifiziert die Signatur **explizit** als einfache elektronische Signatur. Dadurch liegt die rechtliche Einordnung im Audit-Trail vor, falls spaeter bestritten.

---

## 6. Offene Rechtsfragen — „Rechtsrat einholen"

Zwei Detailfragen benoetigen fachanwaltliche Pruefung vor V1-Ship, wenn sehr grosse Ankaeufe erwartet werden:

1. **Schwelle GwG-Identifikationspflicht:** die exakte Schwelle fuer Gueterhaendler „mit hohem Bargeldanteil" ist auslegungsbeduerftig — `[Rechtsrat einholen]` bei einem im Handwerks-/Edelmetallbereich spezialisierten Fachanwalt, ob die 2 000 €-Schwelle fuer eine Goldschmiede-Werkstatt greift oder die 10 000 €-Regelschwelle.
2. **Zivilrechtliche Beweislast-Umkehr durch AGB:** ob eine AGB-Klausel „Der Kunde bestaetigt die Echtheit seiner elektronischen Signatur" die Beweislast faktisch zum Kunden verschiebt, ist umstritten und in der Rechtsprechung uneinheitlich. `[Rechtsrat einholen]` ob eine solche Klausel in Standard-AGB einer Werkstatt zulaessig waere.

Beide Fragen sind **nicht ship-blocking** fuer V1.1, weil die einfache Signatur auch ohne AGB-Klausel zulaessig ist; sie sind Optimierungen fuer V1.2.

---

## 7. Fazit

- **V1.1-Status:** Rechtlich zulaessig. Einfache elektronische Signatur + Foto + Zeitstempel + MA-Identitaet + (bei > 1 000 €) Ausweis-Foto ergeben einen verteidigungsfaehigen Beweis-Cluster.
- **V1.1-Hotfix-Kandidat:** Pruefen, ob Signatur + Foto-mit-Signatur als ein Beleg-PDF zusammengefuehrt werden. Falls nicht, in V1.1 aufnehmen.
- **V1.1.5-Add:** Upload-Feld fuer Ausweis-Foto bei GwG-Schwelle.
- **V1.2-Roadmap:** QES-Ergaenzung ueber D-Trust/sign-me fuer Transaktionen > 5 000 €.
- **Dokumentations-Spur:** dieses Dokument + Verzeichnis-Eintrag V1.1-009 + Daten-Inventar (PII-SCRUB-AUDIT.md Zeile 64, 79) = vollstaendige Audit-Kette fuer einen echten deutschen DPO.

---

**Unterschrift Auditorin:**

```
_________________________________________
Anna Becker, DPO/TUeV-zertifiziert
Datum: 2026-04-17
```

**Kenntnisnahme Verantwortlicher:**

```
_________________________________________
Max Kull, Verantwortlicher
Ort, Datum
```

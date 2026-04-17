# Information zur Datenverarbeitung im neuen QR-/Barcode-Workflow

**Nach Art. 13 DSGVO und BDSG §26 Abs. 8 Satz 2**
**Auszuhaendigen oder in der Werkstatt auszuhaengen vor Einfuehrung am 2026-06-16.**
**Jeder Mitarbeiter bestaetigt Erhalt durch Unterschrift (Liste unten).**

---

Liebe Kolleginnen und Kollegen,

ab dem **16. Juni 2026** fuehren wir im ERP den neuen QR- und Barcode-Workflow ein. Jeder Scan an eurer Werkbank, am Empfang oder im Lager wird dabei protokolliert. Ihr sollt genau wissen, **was gespeichert wird, warum — und wofuer wir die Daten ausdruecklich NICHT verwenden.**

---

## Verantwortlicher

**Max Kull**, Goldsmith ERP (Einzelunternehmer)
`[AUSFUELLEN — eingetragene Geschaeftsadresse]`
Datenschutzanfragen: `[AUSFUELLEN — datenschutz@yourdomain.de]`

Max Kull ist fuer diese Werkstattgroesse auch Datenschutzbeauftragter (Selbstbestellung, < 20 Mitarbeiter, BDSG §38(1) zulaessig). Wenn euch das einen Interessenkonflikt-Eindruck macht, koennt ihr jederzeit externe DPO-Beratung beantragen — das wird dokumentiert und bei gegebenem Anlass auch umgesetzt.

---

## Was wird gespeichert?

Jeder QR- oder Barcode-Scan erzeugt einen Eintrag in der Datenbank mit:

- **Eurer User-ID** (nicht Klarname im Log — nur die interne Datenbank-ID)
- **Zeitstempel** auf dem Geraet (`client_tap_at`) und auf dem Server
- **Dem gescannten Code** (z. B. `ORDER:42`, `METAL:15` — keine Kundennamen im Code)
- **Dem Eingabegeraet** (Kamera, USB-Scanner, manuelle Eingabe)
- **Kontext:** welcher laufende Timer, welche Seite, welches Geraet (Browser-Typ)

Zusaetzlich werden eure **Zeiteintraege** erweitert um die Information, ob der Timer per Scan oder per Button gestartet wurde (`scan_origin`-Feld).

---

## Wofuer wir die Daten nutzen (Art. 5(1)(b) DSGVO Zweckbindung)

1. **Workflow-Beschleunigung.** Timer-Start und Auftragsaufruf gehen per Scan schneller als per Tippen.
2. **Fehlerdiagnose.** Wenn ein Code nicht erkannt wird, sehen wir, ob ein Label beschaedigt ist oder eine Schulung fehlt.
3. **Materialnachvollziehbarkeit.** Was wurde aus welchem Bestand entnommen — gesetzlich vorgeschrieben (HGB §257, Feingehaltsgesetz).
4. **Aggregierte Team-Metriken.** Beispiel: „Wie oft kam die Scanner-Kamera diese Woche zum Einsatz vs. USB-Scanner." Ausschliesslich auf Team-Ebene, niemals pro Person.

---

## Wofuer wir die Daten ausdruecklich NICHT nutzen

Das ist die rechtliche Bright-Line — ohne diese Zusicherung waere der Scan-Log ein Leistungskontroll-Instrument und damit nur mit Betriebsvereinbarung oder Einzeleinwilligung zulaessig. **Es gibt also explizit keine:**

- **Leistungskontrolle einzelner Mitarbeiter.** Wir vergleichen nicht, wer schneller scannt oder mehr Scans pro Tag macht.
- **Ranglisten oder Produktivitaets-Scores.** Keine Dashboards mit Mitarbeiternamen und Zahlen dahinter.
- **Auswertungen unterhalb der Team-Aggregations-Ebene.** Keine Einzelauswertungen, ausser ihr fordert sie selbst an (Art. 15 Auskunft).
- **Grundlage fuer Abmahnungen oder Personalmassnahmen.** Scan-Daten sind kein Disziplinar-Werkzeug.
- **Weitergabe an Dritte** zur Profiling-Analyse.

Diese Zweckbindung ist technisch abgesichert: nur die Admin-Rolle sieht aggregierte Dashboards, und nur mit mindestens drei Mitarbeitern pro Aggregat.

---

## Eure Rechte

| Recht | DSGVO | So uebt ihr es aus |
|---|---|---|
| **Auskunft** | Art. 15 | Sprecht Max an oder schreibt an die Datenschutz-Adresse. Ihr bekommt einen JSON/CSV-Export aller eurer Scan-Logs und Zeiteintraege. V1.1.5 bringt dafuer einen Self-Service-Endpoint. |
| **Berichtigung** | Art. 16 | Zeitbuchungen korrigieren: im ERP selbst (Korrektur-Feld `correction_of`). Scan-Logs sind faktische Ereignisse und werden nicht berichtigt — nur durch neue, korrigierende Scans ersetzt. |
| **Loeschung** | Art. 17 | Bei Austritt: eure User-ID wird anonymisiert (`deleted_user_<Hash>`). Eure Zeit- und Materialeintraege bleiben zur HGB-/Feingehaltsgesetz-Konformitaet erhalten, aber sind nicht mehr auf euch zurueckfuehrbar. |
| **Einschraenkung** | Art. 18 | Wenn ihr eine Verarbeitung bestreitet, koennen wir sie bis zur Klaerung technisch zurueckhalten. |
| **Widerspruch gegen Profiling** | Art. 21 | Wir fuehren kein Profiling — siehe oben. Ein Widerspruch wird dennoch dokumentiert und ihr erhaltet eine Bestaetigung. |
| **Beschwerde bei Aufsichtsbehoerde** | Art. 77 | BayLDA (Bayerisches Landesamt fuer Datenschutzaufsicht) bzw. die fuer euren Wohnsitz zustaendige Aufsichtsbehoerde. Ihr muesst uns nicht fragen und keine Angst um euren Job haben — das ist gesetzlich geschuetzt. |

---

## Aufbewahrungsfristen

| Datenkategorie | Frist | Grundlage |
|---|---|---|
| Scan-Logs (eure Scans) | 24 Monate | Betrieblicher Bedarf; danach automatisch archiviert/geloescht |
| Zeiteintraege (mit Auftragsbezug) | 10 Jahre | HGB §257 kaufmaennische Aufbewahrung |
| Punzierungs-/Hallmark-Verifikationen | 10 Jahre | Feingehaltsgesetz / DIN 8238 |
| Altgold-Belege mit Signatur | 10 Jahre | HGB + GwG |

---

## Besonderes Hinweisrecht zum `client_tap_at`-Feld

Der Zeitstempel auf eurem Geraet (Millisekunden-Genauigkeit) ermoeglicht technisch die Analyse eures Arbeitsrhythmus. Wir verwenden ihn dafuer nicht (siehe Zweckbindung), aber wir wollen, dass ihr wisst, dass er erhoben wird. **Wenn ihr dieser Erhebung widersprechen wollt:** technisch ist `client_tap_at` erforderlich fuer die Konfliktaufloesung bei Offline-Scans und fuer die Idempotenz-Pruefung — wir koennen ihn nicht einfach nicht mehr erheben. Euer Widerspruch nach Art. 21 DSGVO wird aber dokumentiert und mit unserer Interessensabwaegung beantwortet. Faire Moeglichkeit fuer euch, die Sache formell auf den Tisch zu bringen.

---

## Bei Fragen

Fragt Max direkt in der Werkstatt oder schreibt an `[AUSFUELLEN — datenschutz@yourdomain.de]`. Alle Datenschutzanfragen werden innerhalb von 30 Tagen beantwortet (Art. 12 Abs. 3 DSGVO, BDSG §35 Abs. 2).

---

Mit freundlichen Gruessen,

**Max Kull**
Verantwortlicher und DPO-Funktionstraeger

---

## Empfangsbestaetigung

„Ich bestaetige, dass ich diese Information vor Einfuehrung des QR-/Barcode-Workflows erhalten und gelesen habe."

| Name (druckschrift) | Datum | Unterschrift |
|---|---|---|
|  |  |  |
|  |  |  |
|  |  |  |
|  |  |  |
|  |  |  |

---

**Version 1.0** · **Stand:** 2026-04-17 · **Rechtsgrundlage:** Art. 13 DSGVO, BDSG §26 Abs. 8 Satz 2 · **Ablage:** Ausgehaengt im Werkstattbereich + signierte Kopie im Personalordner pro Mitarbeiter.

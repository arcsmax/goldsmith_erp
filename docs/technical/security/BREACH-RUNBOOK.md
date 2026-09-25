# Datenpanne: Ablauf in 72 Stunden (Art. 33 / 34 DSGVO)

**Verantwortliche:** [Name der Goldschmiede], Inhaberin Anne [Nachname] — **entscheidet und meldet**
**Technik:** Max Kull (Betreiber, Auftragsverarbeiter) — **untersucht, sichert, behebt, informiert Anne unverzüglich**
**Stand:** 2026-09-25 · **Finding:** GDPR-17

> Fristen und Schwellen sind **vom Datenschutzberater zu bestätigen**. Zuständige Aufsichtsbehörde: die Landesdatenschutzbehörde am Sitz der Werkstatt: [Name, Online-Meldeformular-URL, Telefon]. **(eintragen)**

## 0. Was ist eine Datenpanne?

Jede Verletzung der Sicherheit, die zu Vernichtung, Verlust, Veränderung oder unbefugter Offenlegung von bzw. unbefugtem Zugang zu personenbezogenen Daten führt (Art. 4 Nr. 12). Beispiele für diese Werkstatt:

- Laptop, Tablet oder Backup-Festplatte gestohlen oder verloren
- E-Mail mit Fotos oder Rechnung an die falsche Kundin geschickt
- Fremder Zugriff auf den Server oder ein ADMIN-Konto (z. B. Passwort weitergegeben)
- Backup-Datei oder `.env.production` (Schlüssel!) an einen falschen Ort kopiert/hochgeladen
- Ransomware / verschlüsselte Festplatte, Daten nicht mehr verfügbar
- Mail-Anbieter oder Backup-Speicher meldet einen Vorfall

## 1. Die Uhr läuft ab Kenntnis

Die 72 Stunden beginnen, sobald die Werkstatt **mit hinreichender Sicherheit weiß**, dass eine Panne passiert ist — nicht erst, wenn alles aufgeklärt ist. Der Betreiber muss Anne **sofort**, spätestens nach [24] Stunden informieren (AVV).

| Zeit | Wer | Was |
|---|---|---|
| **0 h** | wer es bemerkt | Anne und Max anrufen (nicht nur E-Mail). Nichts löschen, nichts „aufräumen“. Uhrzeit notieren. |
| **0–4 h** | Max | Eindämmen: betroffenes Konto sperren (ADMIN: Nutzer deaktivieren), Passwort ändern; bei Verdacht auf gestohlene Tokens `SECRET_KEY` rotieren (macht alle Anmeldungen ungültig), Gerät vom Netz, bei Schlüsselverlust `ENCRYPTION_KEY`-Rotation vorbereiten (`scripts/rotate-secrets.sh`). Beweise sichern (Logs, Zeitpunkte). |
| **4–24 h** | Max | Umfang klären (Abschnitt 2), Ergebnis schriftlich an Anne. |
| **24–48 h** | Anne (mit Datenschutzberater) | Risiko bewerten (Abschnitt 3), Entscheidung: melden ja/nein, Betroffene benachrichtigen ja/nein. Entscheidung und Begründung ins Pannen-Register. |
| **bis 72 h** | Anne | Meldung an die Aufsichtsbehörde (Vorlage Abschnitt 4). Unvollständige Angaben sind erlaubt und werden nachgereicht (Art. 33 Abs. 4). Wird die Frist überschritten, Gründe angeben. |
| **ohne unangemessene Verzögerung** | Anne | Betroffene benachrichtigen, wenn ein **hohes** Risiko besteht (Art. 34, Vorlage Abschnitt 5). |
| **danach** | Max + Anne | Ursache beheben, TOMs anpassen (`TOMS.md`), Eintrag im Register abschließen. |

## 2. Umfang klären (Max)

- **Welche Daten?** Kundendaten (Kategorien: Kontakt, Allergien = Gesundheitsdaten, Rechnungen, Altgold/Ausweis, Wertgutachten, Fotos), Mitarbeiterdaten?
- **Waren sie verschlüsselt?** Datenbankfelder mit PII sind verschlüsselt (`EncryptedString`); Backups sind verschlüsselt (age/gpg). Wurde **auch der Schlüssel** offengelegt (`.env.production`, Backup-Schlüsseldatei)? Wenn nein, ist das Risiko oft gering.
- **Wie viele Personen?** Für eine Kundin: `GET /customers/{id}/export` zeigt, was über sie gespeichert ist. Zugriffe: `customer_audit_logs` (wer, wann, welche Kundin, welcher Endpunkt), z. B.
  ```sql
  SELECT customer_id, user_id, action, entity, timestamp, ip_address
  FROM customer_audit_logs
  WHERE timestamp BETWEEN '<von>' AND '<bis>'
  ORDER BY timestamp;
  ```
  Anzahl betroffener Kundinnen: `SELECT COUNT(DISTINCT customer_id) … ` mit demselben Filter.
- **Seit wann, bis wann?** Server- und Proxy-Logs, `podman-compose logs`.
- **Ist es noch aktiv?** Wenn ja: zuerst eindämmen.

## 3. Risiko bewerten (Anne)

| Risiko | Beispiel | Aufsichtsbehörde | Betroffene |
|---|---|---|---|
| **voraussichtlich kein Risiko** | verschlüsseltes Backup verloren, Schlüssel sicher; Mail an falsche Adresse, Empfänger bestätigt Löschung, nur Terminhinweis ohne Details | nicht melden, **aber im Register dokumentieren** (Art. 33 Abs. 5) | nein |
| **Risiko** | Mail mit Rechnung/Fotos an falsche Person; kurzfristiger unbefugter Zugriff auf einzelne Kundendaten | **melden (72 h)** | in der Regel nein |
| **hohes Risiko** | Allergien (Gesundheitsdaten), Ausweisdaten aus Altgold-Ankäufen, Wertgutachten mit Wert und Anschrift (Einbruchsrisiko!) offengelegt; Schlüssel und Datenbank zusammen abgeflossen | **melden (72 h)** | **benachrichtigen** |

Im Zweifel melden. **(Schwellen vom Datenschutzberater zu bestätigen)**

## 4. Vorlage: Meldung an die Aufsichtsbehörde (Art. 33 Abs. 3)

Die meisten Landesbehörden haben ein Online-Formular; diese Angaben bereithalten:

```
Verantwortliche: [Name der Goldschmiede], Anne [Nachname], [Anschrift], [Telefon], [E-Mail]
Kontakt für Rückfragen: Anne [Nachname], [Telefon]

1. Art der Verletzung: [z. B. Diebstahl eines Tablets / Fehlversand einer E-Mail / unbefugter Zugriff]
   Zeitpunkt der Verletzung: [Datum, Uhrzeit oder Zeitraum]
   Zeitpunkt der Kenntnisnahme: [Datum, Uhrzeit]
2. Kategorien betroffener Personen: [Kundinnen und Kunden / Mitarbeitende], ungefähre Anzahl: [n]
   Kategorien personenbezogener Daten: [Kontaktdaten, Auftragsdaten, Rechnungen, Gesundheitsdaten (Allergien), Ausweisdaten, Fotos …]
   ungefähre Anzahl Datensätze: [n]
3. Wahrscheinliche Folgen: [z. B. Kenntnis Dritter von Kontakt- und Auftragsdaten; Risiko von Einbruch/Betrug bei Wertangaben]
4. Ergriffene / vorgeschlagene Maßnahmen:
   - [Konto gesperrt, Passwörter und Sitzungen widerrufen am …]
   - [Daten waren verschlüsselt (Verfahren), Schlüssel nicht betroffen]
   - [Empfänger der Fehl-Mail um Löschung gebeten, Bestätigung am …]
   - [Benachrichtigung der Betroffenen am … / nicht erforderlich, weil …]
Hinweis: Angaben sind vorläufig und werden nach Abschluss der Untersuchung ergänzt (Art. 33 Abs. 4 DSGVO).
[Bei Meldung nach mehr als 72 h: Begründung der Verzögerung]
```

## 5. Vorlage: Benachrichtigung der Betroffenen (Art. 34)

Klar und einfach, per Brief oder E-Mail an die bekannte Adresse (nicht an eine möglicherweise kompromittierte):

```
Betreff: Wichtige Information zum Schutz Ihrer Daten

Sehr geehrte/r [Anrede Name],

am [Datum] ist es bei uns zu einem Vorfall gekommen, bei dem [kurze, verständliche Beschreibung,
z. B. „ein Tablet mit Zugang zu unserem Auftragssystem gestohlen wurde“].
Davon betroffen sind möglicherweise folgende Daten von Ihnen: [Kategorien].

Mögliche Folgen: [z. B. dass Unbefugte Ihre Anschrift und Angaben zu Ihrem Schmuck kennen].
Wir haben sofort Folgendes getan: [Maßnahmen].
Wir empfehlen Ihnen: [z. B. auf ungewöhnliche Anrufe oder Post zu achten, die sich auf Ihren Auftrag beziehen].

Für Fragen erreichen Sie uns unter [Telefon / E-Mail].
Sie haben außerdem das Recht, sich bei der Datenschutz-Aufsichtsbehörde zu beschweren: [Behörde].

Wir bedauern den Vorfall sehr.
[Anne Nachname], [Name der Goldschmiede]
```

## 6. Pannen-Register (Art. 33 Abs. 5)

Jede Panne wird eingetragen, auch wenn nicht gemeldet wird. Eine Tabelle genügt (Papier im Ordner „Datenschutz“ oder Tabellenkalkulation, nicht im selben System, das betroffen sein könnte):

| Nr. | Bemerkt am | Beschreibung | Daten / Personen | Risiko | Gemeldet (Datum, Az.) | Betroffene informiert | Maßnahmen | Abgeschlossen |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |

## 7. Vorbereitet halten

- [ ] Telefonnummern Anne, Max, Datenschutzberater: [eintragen]
- [ ] Zugangsdaten zum Meldeportal der Aufsichtsbehörde / Formular-Link: [eintragen]
- [ ] Ausgedruckte Schlüsselhinterlegung im Tresor (für Wiederherstellung und Schlüsselrotation)
- [ ] Letzte erfolgreiche Restore-Probe: [Datum]

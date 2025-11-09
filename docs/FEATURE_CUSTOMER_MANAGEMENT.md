# Goldsmith ERP - Kundenverwaltung

**Kundendaten pflegen und nutzen**
Version 1.0 | Stand: November 2025

---

## Überblick

Die **Kundenverwaltung** hilft Ihnen, Kundendaten zu pflegen und die Kundenhistorie nachzuvollziehen.

### Hauptfunktionen

- 👥 **Kundenliste** - Alle Kunden auf einen Blick
- ➕ **Kunde anlegen** - Neue Kunden erfassen
- ✏️ **Kunde bearbeiten** - Kontaktdaten aktualisieren
- 📋 **Kundenhistorie** - Alle Aufträge eines Kunden
- 🔍 **Kunden suchen** - Schnell den richtigen Kunden finden

---

## Kundenliste ansehen

1. Klicken Sie im Hauptmenü auf **"Kunden"**
2. Sie sehen die **Kundenliste**

### Angezeigte Informationen

| Spalte | Beschreibung |
|--------|--------------|
| **ID** | Kunden-ID |
| **Name** | Vor- und Nachname |
| **E-Mail** | E-Mail-Adresse |
| **Telefon** | Telefonnummer |
| **Aufträge** | Anzahl Aufträge |

---

## Neuen Kunden anlegen

### Wer darf Kunden anlegen?

- ✅ **Admins**: Ja
- ✅ **Goldsmiths**: Ja
- ❌ **Viewers**: Nein

### Schritt-für-Schritt

1. Klicken Sie auf **"Neuer Kunde"** oder **"+ Kunde"**
2. Geben Sie die Kundendaten ein:
   - **Vorname** (Pflicht)
   - **Nachname** (Pflicht)
   - **E-Mail** (optional, aber empfohlen)
   - **Telefon** (optional)
   - **Adresse** (optional)
3. Klicken Sie auf **"Kunde erstellen"**

**Beispiel**:
```
Vorname: Maria
Nachname: Müller
E-Mail: maria.mueller@example.com
Telefon: +49 123 456789
Adresse: Musterstraße 12, 12345 Musterstadt
```

---

## Kunde bearbeiten

1. Öffnen Sie die **Kundenliste**
2. Klicken Sie auf einen Kunden
3. Klicken Sie auf **"Bearbeiten"**
4. Ändern Sie die gewünschten Felder
5. Klicken Sie auf **"Speichern"**

---

## Kunde einem Auftrag zuordnen

Beim Erstellen eines Auftrags:
1. Wählen Sie im Feld **"Kunde"** den passenden Kunden
2. Oder erstellen Sie einen neuen Kunden (Button "+ Neuer Kunde")

Der Auftrag wird automatisch mit dem Kunden verknüpft.

---

## Kundenhistorie ansehen

1. Öffnen Sie die **Kundendetailseite**
2. Sie sehen alle **Aufträge** dieses Kunden:
   - Auftragstitel
   - Status
   - Abgabedatum
   - Erstellungsdatum

**Vorteile**:
- Schneller Überblick über Kundenhistorie
- Erkennung von Stammkunden
- Nachvollziehbarkeit

---

## Kunden suchen

Nutzen Sie das **Suchfeld** oben rechts:

**Suche nach**:
- Vor- oder Nachname
- E-Mail-Adresse
- Telefonnummer

```
Beispiel: "Müller" findet alle Müllers
```

---

## Berechtigungen

| Aktion | Admin | Goldsmith | Viewer |
|--------|-------|-----------|--------|
| Kunden ansehen | ✅ | ✅ | ✅ |
| Kunde erstellen | ✅ | ✅ | ❌ |
| Kunde bearbeiten | ✅ | ✅ | ❌ |
| Kunde löschen | ✅ | ❌ | ❌ |

---

## Best Practices

### Kundennamen

✅ **Gut**:
- Vollständiger Vor- und Nachname
- "Maria Müller"

❌ **Schlecht**:
- Nur Nachname: "Müller"
- Nur Vorname: "Maria"

**Regel**: Immer Vor- UND Nachname angeben.

---

### Kontaktdaten pflegen

✅ **Gut**:
- E-Mail und Telefon erfassen
- Bei Änderungen sofort aktualisieren

❌ **Schlecht**:
- Keine Kontaktdaten
- Veraltete Daten

**Regel**: Kontaktdaten sind wichtig für Rückfragen!

---

### Duplikate vermeiden

✅ **Gut**:
- Vor Neuanlage suchen, ob Kunde schon existiert
- Nur einen Eintrag pro Kunde

❌ **Schlecht**:
- "Maria Müller" und "M. Müller" als separate Kunden

**Regel**: Ein Kunde = ein Eintrag!

---

## Zusammenfassung

✅ **Kundenverwaltung** für Kontaktdaten und Historie
✅ **Goldsmiths** können Kunden anlegen und bearbeiten
✅ **Kundenhistorie** zeigt alle Aufträge
✅ **Suchfunktion** für schnelles Finden

---

**Pflegen Sie Ihre Kundendaten!** 👥✨

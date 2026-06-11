# printertest — Diagnose- und Test-Utility für den Canon SELPHY CP1500

Eigenständiges Python-3-Werkzeug, um den Canon SELPHY CP1500 (USB) unter
Raspberry Pi OS Trixie mit CUPS + Gutenprint 5.3.5 zu testen und die
**Druckoptionen zu finden, die zuverlässig funktionieren** — insbesondere wenn
Aufträge bei „Waiting for printer to become available" hängen bleiben.

Das Werkzeug ist **vollständig unabhängig von der Fotobox-App**: eigener Code,
eigene Logs, eigene Reports. Es ändert nichts an der CUPS-Konfiguration
(Ausnahme: das ausdrücklich aufgerufene `unstick`).

**Grundprinzip:** Es wird nichts über den CP1500 fest verdrahtet. Alle
Seitengrößen, Randlos- und Skalierungsoptionen werden zur Laufzeit aus der
PPD der CUPS-Warteschlange und per IPP vom Server gelesen — also genau das,
was der installierte Gutenprint-5.3.5-Treiber wirklich anbietet. Auch
`media=Postcard` wird **nicht** als korrekt angenommen, sondern gegen die PPD
geprüft.

---

## Installation (auf dem Raspberry Pi)

Kein pip nötig — alles per apt:

```bash
sudo apt install python3-cups python3-pil
```

| Paket | Zweck |
|---|---|
| `python3-cups` | pycups, Pflicht |
| `python3-pil` | beschriftete Testseiten (optional; ohne Pillow wird eine unbeschriftete PPM-Testseite erzeugt) |

Voraussetzung: CUPS läuft, die Warteschlange existiert (siehe
`../PRINTER_SETUP.md`). Für `unstick` muss der Benutzer in der Gruppe
`lpadmin` sein.

`requirements.txt` dokumentiert die Abhängigkeiten nur für Nicht-Pi-Umgebungen.

---

## Schnellstart — empfohlener Ablauf

```bash
cd printertest

# 1. Systemüberblick: CUPS-/Gutenprint-Version, Drucker, Geräte-URI, Queue-Konfiguration
python3 selphy_test.py info

# 2. Ist der Drucker bereit? (prüft auch das Backend: gutenprint53+usb:// erforderlich!)
python3 selphy_test.py check

# 3. Welche Optionen unterstützt der Treiber wirklich? (PageSize, StpBorderless, …)
python3 selphy_test.py options
python3 selphy_test.py options -k PageSize

# 4. Eine Testseite drucken (mit automatisch ermittelten Randlos-Foto-Optionen)
python3 selphy_test.py test-page

# 5. Automatischer Kombinationstest: findet die funktionierenden Einstellungen
python3 selphy_test.py matrix --dry-run     # erst den Plan ansehen
python3 selphy_test.py matrix               # dann drucken (interaktiv bestätigt)
```

Das Ergebnis von Schritt 5 steht in `reports/matrix_*.md` — die Tabelle zeigt
pro Kombination Job-ID, Endzustand, Dauer und Druckermeldung, plus eine Liste
der **funktionierenden Kombinationen**.

---

## Alle Kommandos

| Kommando | Zweck |
|---|---|
| `info` | CUPS-Version, Gutenprint-Version, Backends, alle Drucker mit Status/URI, komplette Queue-Konfiguration, PPD-Identität |
| `printers` | Warteschlangen kompakt auflisten |
| `check` | Bereitschaft prüfen (Exit-Code 0 = bereit, 2 = Problem); erkennt falsches `usb://`-Backend, gestoppte Queue, hängende Meldungen |
| `options` | Alle PPD-Optionen mit Auswahlwerten und Defaults; zusätzlich IPP-Sicht (`media-supported` etc.); Filter mit `-k` |
| `test-page` | Diagnose-Testseite drucken (Randmarkierungen, Farbbalken, Graustufenkeil, Beschriftung der verwendeten Optionen) |
| `print DATEI` | Beliebiges JPEG/PNG drucken |
| `matrix` | Automatischer Test mehrerer Options-Kombinationen mit Report |
| `jobs` | Aktive (`--completed` / `--all`: auch abgeschlossene) Aufträge anzeigen |
| `cancel ID… / --all` | Aufträge abbrechen (`--purge`: inkl. Historie) |
| `unstick` | Hängende Aufträge abbrechen, Queue per `cupsenable`/`cupsaccept` reaktivieren, erneut prüfen |

Gemeinsame Optionen: `-p NAME` (Queue, sonst Auto-Erkennung „SELPHY/CP1500"),
`-v` (Debug-Ausgabe auf der Konsole; ins Logfile wird immer alles geschrieben).

### Eigene Optionen drucken

```bash
python3 selphy_test.py test-page -o PageSize=Postcard -o StpBorderless=True \
    -o StpiShrinkOutput=Expand -o fit-to-page=true

python3 selphy_test.py test-page --bare          # ganz ohne Optionen (PPD-Defaults)
python3 selphy_test.py print ~/foto.jpg -o PageSize=Postcard -o fit-to-page=true
```

Jeder `-o`-Wert wird vor dem Absenden gegen die PPD validiert (unbekannte
Werte ⇒ Fehler mit Liste der gültigen Auswahlwerte; PPD-Constraint-Konflikte
⇒ Warnung). Nicht-PPD-Optionen wie `fit-to-page` oder `print-scaling` werden
als CUPS-Filteroptionen durchgereicht.

### Der Matrix-Test im Detail

```bash
python3 selphy_test.py matrix --dry-run                  # Plan anzeigen
python3 selphy_test.py matrix                            # quick-Modus (kuratiert)
python3 selphy_test.py matrix --mode full --limit 12     # Kartesisches Produkt, begrenzt
python3 selphy_test.py matrix --pagesize Postcard        # nur bestimmte Größen
python3 selphy_test.py matrix --include-other-sizes      # quick + alle weiteren PageSizes
python3 selphy_test.py matrix --image ~/foto.jpg         # eigenes Bild statt Testseiten
python3 selphy_test.py matrix -y --timeout 240           # ohne Rückfragen (bricht beim ersten hängenden Job ab)
```

- **quick** (Default) testet: PPD-Defaults pur → Randlos+Expand+fit-to-page
  (Fotobox-Satz) → Randlos ohne fit-to-page → mit Rand+fit-to-page → ggf.
  `…Fullbleed`-Seitengrößen, falls die PPD welche definiert.
- **full** bildet das kartesische Produkt aus `PageSize` ×
  `StpBorderless` × `StpiShrinkOutput` × `fit-to-page` — Achtung Papierverbrauch.
- Vor jedem Druck wird interaktiv bestätigt (Enter/s/q), Kombinationen mit
  PPD-Constraint-Konflikten werden übersprungen, und ohne Pillow bzw. mit
  `--image` entfällt die Beschriftung pro Kombination.
- Jede Testseite trägt eine **große Nummer (#1, #2, …)**, damit sich die
  physischen Ausdrucke den Report-Einträgen zuordnen lassen.
- Ein Job gilt als **erfolgreich**, wenn CUPS ihn als `completed` meldet; als
  **STUCK**, wenn er nach `--timeout` Sekunden (Default 180) noch nicht fertig
  ist. Hängende Jobs werden abgebrochen, und das Werkzeug fordert zum
  Aus-/Einschalten des Druckers auf, bevor es weitergeht — sonst wären alle
  Folgemessungen wertlos.
- Der Report wird **nach jeder Kombination** gespeichert (JSON), ein Abbruch
  kostet also keine Daten.

---

## Logs und Reports

| Ort | Inhalt |
|---|---|
| `logs/` | Pro Aufruf ein Logfile `JJJJMMTT_HHMMSS_<kommando>.log` mit vollständigem Debug-Protokoll (Optionen, Job-Status-Verlauf, Druckermeldungen) |
| `logs/testpages/` | Die erzeugten Testseiten-Bilder |
| `reports/` | `matrix_*.json` (Rohdaten inkl. komplettem Status-Verlauf je Job) und `matrix_*.md` (lesbare Tabelle + Liste funktionierender Kombinationen) |

Exit-Codes: `0` ok/bereit · `1` Druck fehlgeschlagen · `2` nicht bereit /
Eingabefehler · `130` abgebrochen.

---

## Ergebnisse interpretieren

**Testseite lesen:** Der äußerste **rote Rahmen** liegt exakt auf der
Bildkante. Ist er auf dem Papier sichtbar ⇒ Druck ist nicht randlos bzw.
das Bild wird verkleinert. Fehlt er ⇒ randloser Druck mit Überfüllung
(normal bei `StpBorderless=True`). Der blaue/grüne Innenrahmen zeigt, wie
viel beschnitten wurde.

**Job bleibt „pending" mit „Waiting for printer to become available":**

1. `python3 selphy_test.py check` — beginnt die Geräte-URI mit `usb://` statt
   `gutenprint53+usb://`, ist das die Ursache (Reparatur: `../PRINTER_FIX.md`).
2. Passt die `PageSize` nicht zum eingelegten Papier/Farbband, verweigert der
   Drucker den Auftrag — genau das deckt der Matrix-Test auf.
3. Drucker zeigt dauerhaft „Daten werden empfangen" ⇒ aus- und einschalten
   (das kann keine Software ersetzen), danach `python3 selphy_test.py unstick`.

**Queue steht auf „Angehalten" nach Papier-/Farbband-Fehler:** Der SELPHY
wiederholt den Druck nach dem Nachfüllen selbstständig, meldet das aber nicht
an CUPS — die Queue bleibt pausiert und muss reaktiviert werden:
`python3 selphy_test.py unstick` (bzw. `sudo cupsenable <queue>`).

**Mehrere Aufträge gleichzeitig:** Das `gutenprint53+usb`-Backend hält das
Gerät pro Auftrag exklusiv offen; Folgeaufträge warten als „pending". Das ist
normal. Der Matrix-Test druckt deshalb strikt nacheinander und wartet, bis
die Queue leer ist.

---

## Aufbau

```
printertest/
├── selphy_test.py          # Startskript (CLI)
├── selphytest/
│   ├── cli.py              # Kommandos & Argumente
│   ├── cupsinfo.py         # Laufzeit-Erkennung: Versionen, Drucker, Queue, Jobs
│   ├── ppdopts.py          # PPD-Optionen lesen & validieren
│   ├── printing.py         # Job absenden + Status-Verlauf überwachen
│   ├── testpage.py         # Diagnose-Testseiten erzeugen
│   ├── matrix.py           # Kombinationstest
│   ├── report.py           # JSON-/Markdown-Reports
│   └── logutil.py          # Logging in logs/
├── logs/                   # (zur Laufzeit angelegt)
├── reports/                # (zur Laufzeit angelegt)
├── requirements.txt
└── README.md
```

## Quellen

- [Gutenprint-Forum: Canon SELPHY CP1500 (Unterstützung ab 5.3.5)](https://sourceforge.net/p/gimp-print/discussion/4359/thread/cf53575ce3/)
- [Gutenprint Support-Request #614: Queue bleibt nach Papier-/Farbbandfehler pausiert](https://sourceforge.net/p/gimp-print/support-requests/614/)
- [pibooth #268: Randlos-Druck auf SELPHY (StpBorderless, StpiShrinkOutput)](https://github.com/pibooth/pibooth/issues/268)
- [OpenPrinting cups-filters #492: Randlos-Druck CP1500](https://github.com/OpenPrinting/cups-filters/issues/492)
- [OpenPrinting cups #994: CP1500 wird per USB nicht erkannt (ipp-usb)](https://github.com/OpenPrinting/cups/discussions/994)
- `../PRINTER_SETUP.md` und `../PRINTER_FIX.md` (Einrichtung und Backend-Reparatur)

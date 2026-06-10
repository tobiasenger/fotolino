# Drucker-Einrichtung: Canon SELPHY CP1500

Dieses Dokument beschreibt Schritt für Schritt, wie der Canon SELPHY CP1500
auf dem Raspberry Pi eingerichtet wird, damit die Fotobox drucken kann.

**Wichtig vorab:** Das Installieren der Pakete allein reicht **nicht**.
Der Drucker muss zusätzlich einmalig als **CUPS-Warteschlange** angelegt
werden. Genau das fehlte bei der Fehlermeldung
`Drucker 'SELPHY' nicht in CUPS gefunden. Verfügbare Drucker: ['(keine)']` –
CUPS lief zwar, kannte aber noch keinen einzigen Drucker. Der spätere
Druckfehler `CUPS IPP 1280: No such file or directory` ist nur die
Folge davon (Druckauftrag an eine nicht existierende Warteschlange).

---

## 1. Wie die Fotobox den Drucker findet

- In `config/settings.json` steht unter `printer_name` der Name der
  CUPS-Warteschlange (Standard: `SELPHY`). Änderbar auch im Admin-Bereich
  unter „CUPS-Druckername".
- Die App sucht zuerst nach exakt diesem Namen. Findet sie ihn nicht,
  akzeptiert sie auch ähnliche Namen (z. B. `Canon_SELPHY_CP1500`) oder –
  wenn nur ein einziger Drucker eingerichtet ist – diesen einen.
- Am einfachsten: Die Warteschlange beim Einrichten direkt `SELPHY` nennen.

---

## 2. Benötigte Pakete (Annahme: noch nichts installiert)

```bash
sudo apt update
sudo apt install -y cups cups-client cups-bsd printer-driver-gutenprint python3-cups usbutils
```

| Paket | Wozu |
|---|---|
| `cups` | Der Druckdienst selbst (verwaltet Warteschlangen und Aufträge) |
| `cups-client` | Kommandozeilen-Werkzeuge wie `lpadmin`, `lpstat`, `lpinfo` |
| `cups-bsd` | Klassische Befehle wie `lpr` (praktisch zum Testen) |
| `printer-driver-gutenprint` | Open-Source-Treiber für die Canon-SELPHY-Serie |
| `python3-cups` | Python-Anbindung (`pycups`) – wird vom Code in `src/printer.py` benutzt |
| `usbutils` | `lsusb` zum Prüfen, ob der Drucker am USB erkannt wird |

> Statt `printer-driver-gutenprint` funktioniert auch das Sammelpaket
> `printer-driver-all` (enthält Gutenprint).

Dann CUPS starten und den Benutzer zur Druckerverwaltung berechtigen:

```bash
sudo systemctl enable --now cups
sudo usermod -aG lpadmin $USER     # danach einmal ab- und wieder anmelden
```

---

## 3. Drucker als CUPS-Warteschlange anlegen

Canon liefert **keinen Linux-Treiber** für den CP1500. Es gibt zwei Wege:

### Weg A: USB mit Gutenprint (empfohlen, wenn verfügbar)

Der CP1500 wird von Gutenprint erst seit **Version 5.3.5** unterstützt
(bzw. Snapshots ab Oktober 2022). Prüfen, ob die installierte Version ihn kennt:

```bash
lpinfo -m | grep -i cp1500
```

- **Treffer vorhanden** (z. B. auf Raspberry Pi OS „Trixie"/Debian 13):
  weiter mit den Schritten unten.
- **Kein Treffer** (z. B. Raspberry Pi OS „Bookworm" mit Gutenprint
  5.3.4): Entweder das Betriebssystem aktualisieren, Gutenprint aus den
  Quellen bauen – oder einfach **Weg B (WLAN)** nutzen.

Einrichtung:

```bash
# 1. Drucker einschalten, per USB anschließen, Erkennung prüfen:
lsusb | grep -i canon

# 2. Geräte-URI anzeigen lassen (Zeile mit "selphy" bzw. "gutenprint…usb"):
lpinfo -v
# Beispielausgabe: direct gutenprint53+usb://canon-selphy-cp1500/...

# 3. Exakten Treibernamen ermitteln:
lpinfo -m | grep -i cp1500
# Beispielausgabe: gutenprint.5.3://canon-cp1500/expert ...

# 4. Warteschlange "SELPHY" anlegen (URI und Treiber aus Schritt 2+3 einsetzen):
sudo lpadmin -p SELPHY -E \
  -v "gutenprint53+usb://canon-selphy-cp1500/..." \
  -m "gutenprint.5.3://canon-cp1500/expert"

# 5. Papiergröße als Standard setzen und Drucker als Standarddrucker markieren:
sudo lpadmin -p SELPHY -o media-default=Postcard
sudo lpoptions -d SELPHY
```

> **Achtung:** Falls das Paket `ipp-usb` installiert ist, beansprucht es
> das USB-Gerät für sich und blockiert den Gutenprint-USB-Backend.
> Für Weg A daher entfernen: `sudo apt remove ipp-usb`

### Weg B: WLAN, treiberlos über AirPrint/IPP

Der CP1500 unterstützt AirPrint. Das funktioniert ohne speziellen Treiber
und damit auch auf älteren Systemen (Bookworm):

1. Am Drucker im Menü das WLAN einrichten (gleiches Netz wie der Pi).
   Vorher möglichst die aktuelle **Drucker-Firmware** installieren –
   Canon hat IPP-Fehler per Update behoben.
2. Drucker finden und Warteschlange anlegen:

```bash
# Drucker im Netz suchen (zeigt eine ipp://…-Adresse):
lpinfo -v | grep -i ipp

# Warteschlange treiberlos anlegen ("everywhere" = AirPrint/IPP):
sudo lpadmin -p SELPHY -E -v "ipp://<adresse-aus-obiger-ausgabe>" -m everywhere
sudo lpoptions -d SELPHY
```

### Alternative: CUPS-Webinterface

Statt der Kommandozeile geht auch der Browser:

```bash
sudo cupsctl --remote-admin    # Fernzugriff erlauben (nur falls vom Mac aus)
```

Dann `http://fotobox.local:631` öffnen → *Verwaltung* → *Drucker hinzufügen*
(Login = Pi-Benutzername/-Passwort). Beim Einrichten als Namen **SELPHY**
eintragen – oder anschließend den vergebenen Namen im Admin-Bereich der
Fotobox unter „CUPS-Druckername" hinterlegen.

---

## 4. Funktion prüfen

```bash
# Ist die Warteschlange da und bereit? (Soll: "… ist im Leerlauf")
lpstat -p SELPHY

# Testdruck (Papier + Farbkassette einlegen!):
lp -d SELPHY /usr/share/cups/data/testprint
```

Danach die Fotobox starten – die Warnung
„Drucker 'SELPHY' nicht in CUPS gefunden" darf nicht mehr erscheinen.
Die App erkennt eine neu eingerichtete Warteschlange auch **ohne Neustart**,
da sie vor jedem Druck neu sucht.

---

## 5. Fehlersuche

| Symptom | Ursache / Lösung |
|---|---|
| `Verfügbare Drucker: ['(keine)']` | Es ist keine CUPS-Warteschlange angelegt → Abschnitt 3 |
| `CUPS IPP 1280 / No such file or directory` | Folgefehler von oben: Warteschlange existiert nicht |
| `lsusb` zeigt keinen Canon | Kabel/Strom prüfen; Drucker muss eingeschaltet sein |
| `lpinfo -m` kennt kein CP1500 | Gutenprint zu alt (< 5.3.5) → Weg B (WLAN) nutzen oder OS aktualisieren |
| Auftrag hängt, Drucker druckt nicht über USB | `ipp-usb` deinstallieren (blockiert Gutenprint) oder Firmware aktualisieren |
| `lpadmin: … nicht erlaubt` | Benutzer ist nicht in der Gruppe `lpadmin` → Abschnitt 2 |
| Python-Log: „pycups not available" | `sudo apt install python3-cups` |
| Druck wird abgeschnitten/mit Rand | Papiergröße auf `Postcard` (100×148 mm) stellen, s. Abschnitt 3 |

Logs ansehen:

```bash
journalctl -u cups --since "10 minutes ago"
tail -f /var/log/cups/error_log
```

---

## Quellen

- [CUPS-Diskussion: CP1500 wird per USB nicht erkannt](https://github.com/OpenPrinting/cups/discussions/994)
- [ipp-usb Issue #73: CP1500 einrichten schlägt fehl](https://github.com/OpenPrinting/ipp-usb/issues/73)
- [Gutenprint-Forum: Canon Selphy CP1500](https://sourceforge.net/p/gimp-print/discussion/4359/thread/cf53575ce3/)
- [Gutenprint 5.3.5 Release](https://sourceforge.net/projects/gimp-print/files/gutenprint-5.3/5.3.5/)
- [Debian Bookworm: printer-driver-gutenprint (5.3.4-Snapshot)](https://packages.debian.org/bookworm/printer-driver-gutenprint)

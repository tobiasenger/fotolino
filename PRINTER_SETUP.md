# Drucker-Einrichtung: Canon SELPHY CP1500 (USB)

Schritt-für-Schritt-Anleitung, um den Canon SELPHY CP1500 **per USB** auf
einem frischen Raspberry Pi OS **Trixie** (Debian 13) einzurichten, damit
die Fotobox drucken kann.

**Wichtig vorab:**

1. Canon liefert keinen Linux-Treiber für den CP1500. Der Open-Source-Treiber
   **Gutenprint** unterstützt den CP1500 erst ab **Version 5.3.5**. Trixie
   liefert im Debian-Paket nur 5.3.4 – Gutenprint 5.3.5 muss daher einmalig
   **aus den Quellen** gebaut werden (Abschnitt 3).
2. Pakete installieren allein reicht nicht: Der Drucker muss zusätzlich
   einmalig als **CUPS-Warteschlange** angelegt werden (Abschnitt 4). Fehlt
   sie, meldet die App `Drucker 'SELPHY' nicht in CUPS gefunden. Verfügbare
   Drucker: ['(keine)']`.

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

## 2. Basispakete installieren

```bash
sudo apt update
sudo apt install -y cups cups-client cups-bsd python3-cups usbutils
```

| Paket | Wozu |
|---|---|
| `cups` | Der Druckdienst selbst (verwaltet Warteschlangen und Aufträge) |
| `cups-client` | Kommandozeilen-Werkzeuge wie `lpadmin`, `lpstat`, `lpinfo` |
| `cups-bsd` | Klassische Befehle wie `lpr` (praktisch zum Testen) |
| `python3-cups` | Python-Anbindung (`pycups`) – wird von `src/printer.py` benutzt |
| `usbutils` | `lsusb` zum Prüfen, ob der Drucker am USB erkannt wird |

Dann CUPS starten und den Benutzer zur Druckerverwaltung berechtigen:

```bash
sudo systemctl enable --now cups
sudo usermod -aG lpadmin $USER     # danach einmal ab- und wieder anmelden
```

> **Hinweis `ipp-usb`:** Falls das Paket `ipp-usb` installiert ist,
> beansprucht es USB-Drucker für sich und blockiert andere Backends.
> Sicherheitshalber entfernen: `sudo apt remove ipp-usb`

---

## 3. Gutenprint 5.3.5 aus den Quellen installieren

### 3.1 Build-Abhängigkeiten

```bash
sudo apt install -y build-essential pkg-config libcups2-dev libcupsimage2-dev libusb-1.0-0-dev
```

**Wichtig:** Ohne `libcups2-dev` und `libcupsimage2-dev` schlägt der
Build später fehl bzw. baut ohne CUPS-Unterstützung – erkennbar an dieser
Zeile in der `./configure`-Ausgabe:

```text
checking for cups-config... no
```

Erst wenn dort ein Pfad steht (`checking for cups-config... /usr/bin/cups-config`),
wird der CUPS-Treiber mitgebaut.

### 3.2 Quellcode laden, bauen, installieren

```bash
cd ~
wget https://downloads.sourceforge.net/project/gimp-print/gutenprint-5.3/5.3.5/gutenprint-5.3.5.tar.xz
tar xf gutenprint-5.3.5.tar.xz
cd gutenprint-5.3.5

./configure --without-doc
# In der Ausgabe prüfen: "checking for cups-config... /usr/bin/cups-config"

make -j4          # dauert auf dem Pi 4 eine Weile
sudo make install
sudo ldconfig
sudo systemctl restart cups
```

Die CUPS-Treiberdateien werden dabei in die echten CUPS-Verzeichnisse
installiert (`./configure` ermittelt sie über `cups-config`) und
überschreiben dort die 5.3.4-Dateien des Debian-Pakets.

### 3.3 Installierte Version prüfen

```bash
gutenprint-config --version
# Soll: 5.3.5
```

> **Nicht verwirren lassen:** `dpkg -l | grep gutenprint` zeigt weiterhin
> die alte Debian-Paketversion (5.3.4) an. Das ist **erwartet** – die
> manuell aus den Quellen installierte Version wird von `dpkg` nicht
> verwaltet. Maßgeblich ist die Ausgabe von `gutenprint-config --version`.

Anschließend prüfen, dass CUPS den CP1500-Treiber jetzt kennt:

```bash
lpinfo -m | grep -i cp1500
# Soll u. a. zeigen: gutenprint.5.3://canon-cp1500/expert  Canon SELPHY CP1500 - CUPS+Gutenprint v5.3.5
```

> Falls vor dem Update bereits Gutenprint-Warteschlangen existierten,
> deren PPDs aktualisieren: `sudo cups-genppdupdate && sudo systemctl restart cups`

---

## 4. CUPS-Warteschlange anlegen (USB)

### 4.1 Drucker anschließen und Geräte-URI ermitteln

Drucker einschalten, per USB anschließen, dann:

```bash
# 1. Wird der Drucker am USB erkannt?
lsusb | grep -i canon
# Beispiel: Bus 001 Device 005: ID 04a9:32f1 Canon, Inc. SELPHY CP1500

# 2. Geräte-URI anzeigen lassen:
lpinfo -v
# Es erscheinen typischerweise ZWEI Zeilen für den Drucker, Beispiel:
# direct usb://Canon/SELPHY%20CP1500?serial=CZ23011023417958
# direct gutenprint53+usb://canon-selphy-cp1500/CZ23011023417958
```

> **Die richtige URI wählen:** Es muss die Zeile verwendet werden, die mit
> **`gutenprint53+usb://`** beginnt – das ist das SELPHY-eigene Backend aus
> Gutenprint 5.3.5. Die `usb://Canon/...`-URI (Standard-USB-Backend) führt
> dazu, dass Aufträge bei „Waiting for printer to become available" hängen
> und der Drucker nach dem Druck auf „Daten werden empfangen" stehen bleibt
> (Reparatur einer so angelegten Queue: siehe `PRINTER_FIX.md`).

> **Achtung:** Das Wort `direct` am Zeilenanfang ist **nicht Teil der URI** –
> es bezeichnet nur die Backend-Klasse. Die URI beginnt bei `gutenprint53+usb://`.
> Falsch: `-v "direct gutenprint53+usb://..."` · Richtig: `-v "gutenprint53+usb://..."`

### 4.2 Warteschlange anlegen

URI aus Schritt 4.1 einsetzen (die Seriennummer ist bei jedem Gerät anders):

```bash
sudo lpadmin -p SELPHY -E \
  -v "gutenprint53+usb://canon-selphy-cp1500/CZ23011023417958" \
  -m "gutenprint.5.3://canon-cp1500/expert"

# Randlosdruck als Queue-Standard setzen – die App übergibt KEINE
# Druckoptionen, daher muss das hier (einmalig) konfiguriert werden:
sudo lpadmin -p SELPHY -o StpBorderless=True

# Papiergröße als Standard setzen und als Standarddrucker markieren:
sudo lpadmin -p SELPHY -o media-default=Postcard
sudo lpoptions -d SELPHY
```

- `-p SELPHY` – Name der Warteschlange (muss zu `printer_name` in der App passen)
- `-E` – Warteschlange aktivieren und Aufträge annehmen
- `-v` – die `gutenprint53+usb://`-URI aus `lpinfo -v` (ohne `direct`!)
- `-m` – der Gutenprint-5.3.5-Treiber aus `lpinfo -m | grep -i cp1500`
  (Variante `expert` verwenden – sie stellt die Randlos-Option
  `StpBorderless` bereit, die hier als Queue-Standard gesetzt wird)
- `-o StpBorderless=True` – randloser Druck als **Standardwert der
  Warteschlange**. Die Fotobox sendet Aufträge bewusst ohne eigene
  Druckoptionen (Begründung: Abschnitt „Druckoptionen der Fotobox"),
  deshalb gehört diese Einstellung in die Queue, nicht in die App.

### 4.3 Queue-Standards prüfen

```bash
lpoptions -p SELPHY -l | grep -iE "pagesize|borderless"
# Beispiel: PageSize/Page Size: *Postcard w253h337 w155h244 ...
#           StpBorderless/Borderless: False *True
```

Der Stern markiert den jeweils aktiven Standardwert: `Postcard`
(100×148 mm, KP-108IN-Papier) und `StpBorderless=True` müssen markiert
sein. Diese Queue-Standards sind die einzige Stelle, an der Papierformat
und Randlosdruck konfiguriert werden – die Fotobox selbst übergibt beim
Drucken keine Optionen (siehe Abschnitt „Druckoptionen der Fotobox").

---

## 5. Funktion prüfen

```bash
# Ist die Warteschlange da und bereit? (Soll: "… ist im Leerlauf")
lpstat -p SELPHY

# Testdruck (Papier + Farbkassette einlegen!) – bewusst OHNE -o-Optionen,
# genau wie die Fotobox druckt; die Queue-Standards aus 4.2 gelten:
lp -d SELPHY /usr/share/cups/data/testprint
```

> Falls der Testdruck mit „Waiting for printer to become available" hängt:
> zuerst mit `lpstat -t` prüfen, ob die Geräte-URI wirklich mit
> `gutenprint53+usb://` beginnt (sonst → `PRINTER_FIX.md`); danach
> USB-Kabel des Druckers ab- und wieder anstecken (siehe Fehlersuche).

Danach die Fotobox starten – die Warnung
„Drucker 'SELPHY' nicht in CUPS gefunden" darf nicht mehr erscheinen.
Die App erkennt eine neu eingerichtete Warteschlange auch **ohne Neustart**,
da sie vor jedem Druck neu sucht.

### Druckoptionen der Fotobox

**Die App übergibt bewusst keinerlei Druckoptionen an CUPS** – der Aufruf
in `src/printer.py` lautet:

```python
job_id = self._conn.printFile(target, str(path), "Fotobox", {})
```

**Warum keine app-seitigen Optionen?** Nach ausgiebiger Fehlersuche stellte
sich heraus, dass vom Programm mitgesendete Druckoptionen (`media`,
`fit-to-page`, `print-scaling`, PPD-Optionen wie `StpBorderless` …) die
Ursache für unzuverlässiges Druckverhalten waren: CUPS nahm die Aufträge
an, sie blieben aber teils hängen oder druckten nicht korrekt – obwohl
Drucker, USB-Verbindung, CUPS, pycups und der Gutenprint-Treiber
nachweislich einwandfrei funktionierten. Ohne Job-Optionen druckt der
CP1500 stabil.

**Wo wird dann der Randlosdruck konfiguriert?** Ohne Job-Optionen gelten
die **Standardwerte der CUPS-Warteschlange** (PPD-Defaults plus per
`lpadmin -o` gesetzte Queue-Defaults). Randloser Druck wird deshalb
einmalig in der Queue hinterlegt – getestet und mit dem gewünschten
randlosen Ergebnis:

```bash
sudo lpadmin -p SELPHY -o StpBorderless=True
```

**Bekannt-gute Referenzkonfiguration** (verifiziert nach ausgiebiger
Fehlersuche – aktueller Stand):

| Komponente | Stand |
|---|---|
| Drucker | Canon SELPHY CP1500 |
| Betriebssystem | Raspberry Pi OS Trixie (Debian 13) |
| Druckdienst | CUPS |
| Treiber | Gutenprint 5.3.5 (aus den Quellen, Abschnitt 3) |
| Verbindung | USB, Backend `gutenprint53+usb://` (Abschnitt 4) |
| Queue-Standards | `StpBorderless=True`, `media-default=Postcard` |
| App-Druckaufruf | `printFile(…, {})` – **ohne** Job-Optionen |

> **Wichtig – Stabilität geht vor:** Keine neuen Druck-, Medien- oder
> Skalierungsoptionen einführen (weder im Code noch als zusätzliche
> Job-Optionen), sofern es dafür keinen starken, dokumentierten Grund gibt
> und die Änderung gründlich auf dem CP1500 getestet wurde. Die obige
> Konfiguration ist die stabile Referenz und soll erhalten bleiben.

Die App protokolliert vor jedem Druck Warteschlange, Geräte-URI und Datei
und prüft nach dem Absenden kurz den Job-Status – verworfene Aufträge
werden als Fehler gemeldet, hängende Aufträge mit der CUPS-Druckermeldung
ins Log geschrieben.

---

## 6. Fehlersuche

### Auftrag hängt bei „Waiting for printer to become available"

Das ist die häufigste Störung: CUPS hat den Auftrag angenommen, aber das
USB-Backend kann den Drucker nicht öffnen. Der Reihe nach prüfen:

```bash
# 1. Gesamtstatus: Warteschlangen, Aufträge, Statusmeldungen
lpstat -t

# 2. Wird der Drucker am USB überhaupt noch gesehen?
lsusb | grep -i canon

# 3. USB-Kabel ab- und wieder anstecken bzw. Drucker aus- und einschalten.
#    Der SELPHY meldet sich nach Standby/Fehlern manchmal nicht neu am Bus.

# 4. Hängende Aufträge verwerfen und neu drucken:
cancel -a SELPHY

# 5. CUPS-Logs ansehen:
journalctl -u cups --since "10 minutes ago"
sudo tail -n 50 /var/log/cups/error_log
```

> **Unterspannung prüfen:** Eine zu schwache Stromversorgung des Pi kann
> die USB-Kommunikation mit dem Drucker stören (Gerät „verschwindet"
> zeitweise vom Bus). Prüfen mit:
>
> ```bash
> vcgencmd get_throttled
> # 0x0     = alles in Ordnung
> # ≠ 0x0   = Unterspannung/Drosselung (z. B. 0x50005) → offizielles
> #           5,1-V/3-A-Netzteil verwenden, USB-Verbraucher reduzieren
> ```

### Weitere Symptome

| Symptom | Ursache / Lösung |
|---|---|
| `Verfügbare Drucker: ['(keine)']` | Keine CUPS-Warteschlange angelegt → Abschnitt 4 |
| `CUPS IPP 1280 / No such file or directory` | Folgefehler: Warteschlange existiert nicht |
| `lsusb` zeigt keinen Canon | Kabel/Strom prüfen; Drucker einschalten; anderes USB-Kabel/-Port testen |
| `lpinfo -m` kennt kein CP1500 | Gutenprint < 5.3.5 aktiv → Abschnitt 3; danach `gutenprint-config --version` prüfen |
| `checking for cups-config... no` beim `./configure` | `sudo apt install libcups2-dev libcupsimage2-dev`, dann `./configure` erneut |
| `dpkg` zeigt 5.3.4 trotz Quellinstallation | Erwartet – maßgeblich ist `gutenprint-config --version` (Abschnitt 3.3) |
| Auftrag hängt bei „Waiting for printer…" | Queue nutzt das falsche `usb://`-Backend → `PRINTER_FIX.md`; sonst: replug, `lpstat -t`, Logs, Unterspannung |
| Druck erst nach Aus-/Einschalten; Drucker bleibt auf „Daten werden empfangen" | Queue nutzt das Standard-`usb://`-Backend statt `gutenprint53+usb://` → Reparatur siehe `PRINTER_FIX.md` |
| Drucker druckt, fällt dann aus | `vcgencmd get_throttled` prüfen (Unterspannung), `ipp-usb` entfernen |
| `lpadmin: … nicht erlaubt` | Benutzer nicht in Gruppe `lpadmin` → Abschnitt 2 |
| Python-Log: „pycups not available" | `sudo apt install python3-cups` |
| Druck mit weißem Rand | Randlosdruck als Queue-Standard setzen: `sudo lpadmin -p SELPHY -o StpBorderless=True` (braucht das `expert`-PPD, Abschnitt 4.2). Die App setzt **keine** eigenen Druckoptionen |
| Druckaufträge hängen/fehlerhaft, obwohl Hardware/Treiber in Ordnung | Werden app-/job-seitig Druckoptionen mitgesendet (`media`, `fit-to-page`, `print-scaling` …)? Entfernen – ohne Job-Optionen drucken (siehe „Druckoptionen der Fotobox") |

---

## Quellen

- [Gutenprint 5.3.5 Release (SourceForge)](https://sourceforge.net/projects/gimp-print/files/gutenprint-5.3/5.3.5/)
- [Gutenprint-Forum: Canon Selphy CP1500 (Unterstützung ab 5.3.5/Snapshots)](https://sourceforge.net/p/gimp-print/discussion/4359/thread/cf53575ce3/)
- [pibooth Issue #268: Randlos-Druck auf SELPHY via CUPS/Gutenprint (StpBorderless, StpiShrinkOutput)](https://github.com/pibooth/pibooth/issues/268)
- [OpenPrinting cups-filters #492: Randlos-Druck CP1500](https://github.com/OpenPrinting/cups-filters/issues/492)
- [CUPS-Diskussion: CP1500 wird per USB nicht erkannt](https://github.com/OpenPrinting/cups/discussions/994)
- [ipp-usb Issue #73: CP1500 einrichten schlägt fehl](https://github.com/OpenPrinting/ipp-usb/issues/73)

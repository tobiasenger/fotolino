# Fotobox – Komplette Installationsanleitung

Diese Anleitung führt Schritt für Schritt von einem frisch installierten
Raspberry Pi OS bis zur ersten erfolgreich gestarteten Fotobox. Es sind
**keine Vorkenntnisse über das Projekt nötig** – einfach von oben nach unten
durcharbeiten.

**Ausgangslage (wird vorausgesetzt):**

- Ein Raspberry Pi 4 mit frisch installiertem **Raspberry Pi OS Desktop
  (64-bit)** startet bis zum Desktop.
- Der Projektordner **`Fotobox`** liegt bereits im Home-Verzeichnis des
  Benutzers (also unter `/home/<benutzer>/Fotobox`).
- Sonst ist noch **nichts** installiert oder eingerichtet.

> **Hinweis zu Pfaden:** In dieser Anleitung steht der Projektordner unter
> `~/Fotobox`. Heißt der Ordner anders oder liegt er woanders, die Pfade
> entsprechend anpassen. Alle Befehle werden im **Terminal** eingegeben
> (schwarzes Konsolen-Symbol in der Taskleiste oder per SSH).

**Benötigte Zeit:** ca. 2–3 Stunden (der größte Teil entfällt auf das
einmalige Bauen des Druckertreibers in Teil 2, Schritt 6).

---

# Teil 1: Hardware-Aufbau

## 1.1 Übersicht – was wird angeschlossen?

| Komponente | Anschluss am Pi | Zweck |
|---|---|---|
| Kameramodul (z. B. Camera Module 3 / IMX708) | CSI-Kameraport (Flachbandkabel) | Live-Vorschau und Fotoaufnahme |
| Canon SELPHY CP1500 | USB-A-Port | Fotodruck |
| Lautsprecher (aktiv) | 3,5-mm-Klinkenbuchse | Szenen-Musik und Sound-Effekte |
| USB-Stick | USB-A-Port | Speicherung der Fotos und Collagen |
| Monitor / Display | HDMI (micro-HDMI am Pi 4) | Anzeige (1920×1080 empfohlen) |
| 2 Taster + 2 LEDs auf Steckbrett | GPIO-Pins (siehe 1.3) | Start-/Admin-Taste, Blitz-/Bereit-LED |
| Netzteil **5,1 V / 3 A** (offizielles Pi-Netzteil) | USB-C | Stromversorgung |

> **Wichtig – Netzteil:** Ein zu schwaches Netzteil führt zu Unterspannung.
> Die spürbarste Folge bei der Fotobox: Die USB-Verbindung zum Drucker wird
> instabil und Druckaufträge bleiben hängen. Unbedingt das offizielle
> 5,1-V/3-A-Netzteil verwenden.

**Alle folgenden Verkabelungsschritte bei ausgeschaltetem,
stromlosem Pi durchführen!**

## 1.2 Kamera anschließen

1. Pi ausschalten und vom Strom trennen.
2. Die Verriegelung des **CSI-Ports** (zwischen HDMI- und Klinkenbuchse)
   vorsichtig nach oben ziehen.
3. Flachbandkabel einstecken: **blaue Seite zeigt zur USB-Buchse des Pi**
   (Kontakte zeigen zum HDMI-Port).
4. Verriegelung wieder herunterdrücken, leicht am Kabel ziehen – es darf
   nicht herausrutschen.
5. Anderes Kabelende genauso am Kameramodul befestigen (blaue Seite zeigt
   von der Linse weg).

## 1.3 Taster und LEDs (GPIO)

Die Fotobox verwendet zwei Taster und zwei LEDs:

| Funktion | GPIO (BCM) | Physischer Pin | Typ |
|---|---|---|---|
| Start-Taste (startet eine Foto-Session) | GPIO 17 | Pin 11 | Eingang |
| Admin-Taste (öffnet/schließt den Admin-Bereich) | GPIO 27 | Pin 13 | Eingang |
| Blitz-LED (leuchtet während der Aufnahme) | GPIO 22 | Pin 15 | Ausgang |
| Bereit-LED (leuchtet, wenn die Box startbereit ist) | GPIO 23 | Pin 16 | Ausgang |
| Gemeinsame Masse (GND) | – | Pin 9 | – |

**Schaltung in Kurzform:**

- **Taster:** `GPIO-Pin ──[10 kΩ]──[Taster]──[10 kΩ]── GND`.
  Die Software aktiviert den internen Pull-up – der Pin liegt auf HIGH und
  wird beim Drücken auf LOW gezogen.
- **LEDs:** `GPIO-Pin ──[220 Ω]── LED-Anode (langes Bein) → LED-Kathode
  (kurzes Bein) ── GND`.

> **Detaillierte Schritt-für-Schritt-Anleitung mit Steckbrett-Plan,
> Teileliste und Pinout-Grafik: siehe `WIRING.md`.**

Die Pin-Nummern sind nicht fest verdrahtet – sie lassen sich später im
Admin-Bereich der App oder in `config/settings.json` ändern. Wer abweichend
verkabelt, muss die Nummern dort anpassen.

**Ohne Taster funktioniert die Box trotzdem:** Die Tastatur ersetzt die
GPIO-Taster (LEERTASTE = Start, F1 = Admin). Für den ersten Test ist die
GPIO-Verkabelung also optional.

## 1.4 Drucker anschließen

1. Canon SELPHY CP1500 mit dem mitgelieferten Netzteil verbinden.
2. Papierkassette (Postkartenformat, KP-108IN) und Farbkassette einsetzen.
3. USB-Kabel vom Drucker an einen **USB-A-Port des Pi** anschließen.
4. Drucker einschalten.

## 1.5 Lautsprecher, USB-Stick, Monitor

- **Lautsprecher:** Aktive Lautsprecher (mit eigener Stromversorgung) an die
  **3,5-mm-Klinkenbuchse** des Pi anschließen.
- **USB-Stick:** In einen freien USB-Port stecken. Empfohlen: FAT32- oder
  exFAT-formatiert, mindestens 8 GB. Die Einrichtung folgt in Teil 2,
  Schritt 7.
- **Monitor:** Per (micro-)HDMI-Kabel verbinden. Die App ist für
  **1920×1080** ausgelegt.

Danach: Netzteil anschließen und den Pi starten.

---

# Teil 2: Software-Einrichtung

Alle Befehle im Terminal des Pi ausführen. Am bequemsten geht das per SSH
vom eigenen Rechner aus; es funktioniert aber genauso direkt am Pi.

## Schritt 1: System aktualisieren

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Nach dem Neustart wieder anmelden bzw. das Terminal neu öffnen.

## Schritt 2: Alle benötigten Pakete installieren

Ein einziger Befehl installiert alles, was die Fotobox braucht:

```bash
sudo apt install -y \
  python3-pyqt6 python3-pyqt6.qtmultimedia \
  python3-picamera2 python3-gpiozero \
  python3-pil python3-numpy python3-mutagen \
  vlc python3-vlc \
  cups cups-client cups-bsd python3-cups \
  usbutils alsa-utils pipewire-alsa udisks2
```

**Was wird da installiert?**

| Paket(e) | Wozu |
|---|---|
| `python3-pyqt6`, `…qtmultimedia` | Die Benutzeroberfläche (Qt 6) |
| `python3-picamera2` | Ansteuerung des Kameramoduls |
| `python3-gpiozero` | Taster und LEDs an den GPIO-Pins |
| `python3-pil`, `python3-numpy` | Bildverarbeitung und Collage-Erstellung |
| `python3-mutagen` | Länge von Audio-/Videodateien auslesen (Szeneneditor) |
| `vlc`, `python3-vlc` | **Pflicht für jeden Ton und jedes Video** – ohne diese Pakete bleibt die Box stumm |
| `cups`, `cups-client`, `cups-bsd`, `python3-cups` | Druckdienst und Python-Anbindung |
| `usbutils` | `lsusb` zum Prüfen der Drucker-Erkennung |
| `alsa-utils`, `pipewire-alsa` | Audio-Werkzeuge und Soundserver-Brücke |
| `udisks2` | USB-Stick-Verwaltung |

Anschließend prüfen, ob das problematischste Paket wirklich da ist:

```bash
python3 -c "import vlc; print('python-vlc OK:', vlc.__version__)"
```

✅ **Kontrollpunkt:** Es erscheint `python-vlc OK: …` (keine Fehlermeldung).

## Schritt 3: Benutzerrechte setzen

Der Benutzer braucht Zugriff auf GPIO und auf die Druckerverwaltung:

```bash
sudo usermod -aG gpio,lpadmin $USER
```

**Danach einmal ab- und wieder anmelden** (oder `sudo reboot`), sonst
greifen die neuen Gruppenrechte nicht.

## Schritt 4: Kamera prüfen

Bei aktuellem Raspberry Pi OS wird das Kameramodul automatisch erkannt –
es muss nichts aktiviert werden. Einfach testen:

```bash
rpicam-hello
```

✅ **Kontrollpunkt:** Für einige Sekunden erscheint ein Live-Vorschaufenster.

Erscheint stattdessen ein Fehler („no cameras available"):

1. Pi ausschalten, Sitz des Flachbandkabels an **beiden** Enden prüfen
   (Abschnitt 1.2 – blaue Seite richtig herum?).
2. Erneut starten und `rpicam-hello` wiederholen.

## Schritt 5: Audio einrichten

1. Audioausgabe fest auf die Klinkenbuchse stellen:
   ```bash
   sudo raspi-config
   ```
   → **System Options** → **Audio** → **3.5mm jack** (bzw. „Headphones")
   auswählen → mit *Finish* beenden.

2. Lautsprecher testen (Abbruch mit `Strg+C`):
   ```bash
   speaker-test -t wav -c 2
   ```

✅ **Kontrollpunkt:** Aus beiden Lautsprechern ist abwechselnd
„Front Left / Front Right" zu hören.

Kein Ton? Lautstärke prüfen mit `alsamixer` (Regler mit Pfeiltasten hoch,
Stummschaltung „MM" mit Taste `M` aufheben). Hilft das nicht: Die
ausführliche Audio-Fehlersuche steht in **`FIX_AUDIO.md`**.

> Die App stellt beim Start zusätzlich selbst die Klinkenbuchse als
> Standard-Ausgang ein (Einstellung `force_headphone_audio`, im
> Admin-Bereich abschaltbar, falls der Ton über HDMI laufen soll).

## Schritt 6: Drucker einrichten (Canon SELPHY CP1500)

Das ist der aufwendigste Schritt, denn Canon liefert keinen Linux-Treiber:
Der Open-Source-Treiber **Gutenprint** unterstützt den CP1500 erst ab
Version **5.3.5**, die einmalig aus den Quellen gebaut werden muss.
(Ausführliche Fassung mit Fehlersuche: **`PRINTER_SETUP.md`**.)

### 6.1 CUPS starten und Störer entfernen

```bash
sudo systemctl enable --now cups
sudo apt remove -y ipp-usb 2>/dev/null; true
```

> Das Paket `ipp-usb` (falls vorhanden) beansprucht USB-Drucker exklusiv
> und blockiert den SELPHY-Treiber – deshalb wird es entfernt.

### 6.2 Gutenprint 5.3.5 bauen und installieren

Build-Werkzeuge installieren:

```bash
sudo apt install -y build-essential pkg-config libcups2-dev libcupsimage2-dev libusb-1.0-0-dev
```

Quellcode laden und bauen (dauert auf dem Pi 4 ca. 20–40 Minuten):

```bash
cd ~
wget https://downloads.sourceforge.net/project/gimp-print/gutenprint-5.3/5.3.5/gutenprint-5.3.5.tar.xz
tar xf gutenprint-5.3.5.tar.xz
cd gutenprint-5.3.5

./configure --without-doc
```

**Wichtig – bevor es weitergeht:** In der `./configure`-Ausgabe muss diese
Zeile stehen:

```text
checking for cups-config... /usr/bin/cups-config
```

Steht dort `... no`, fehlen `libcups2-dev`/`libcupsimage2-dev` (Befehl oben
wiederholen, dann `./configure` erneut). Erst dann:

```bash
make -j4
sudo make install
sudo ldconfig
sudo systemctl restart cups
```

Version prüfen:

```bash
gutenprint-config --version
```

✅ **Kontrollpunkt:** Ausgabe ist `5.3.5`.
(`dpkg -l | grep gutenprint` zeigt weiterhin eine ältere Version – das ist
normal, maßgeblich ist nur `gutenprint-config --version`.)

### 6.3 CUPS-Warteschlange anlegen

Drucker **einschalten** und per USB anschließen, dann:

```bash
lsusb | grep -i canon
```

✅ **Kontrollpunkt:** Eine Zeile wie
`ID 04a9:32f1 Canon, Inc. SELPHY CP1500` erscheint.
(Nichts zu sehen? Kabel/Strom prüfen, Drucker aufwecken.)

Geräte-URI ermitteln:

```bash
lpinfo -v | grep -i selphy
```

Es erscheinen typischerweise **zwei** Zeilen, z. B.:

```text
direct usb://Canon/SELPHY%20CP1500?serial=CZ23011023417958
direct gutenprint53+usb://canon-selphy-cp1500/CZ23011023417958
```

> **Unbedingt die Zeile mit `gutenprint53+usb://` verwenden!** Mit der
> `usb://Canon/...`-URI bleiben Druckaufträge bei „Waiting for printer to
> become available" hängen. Das Wort `direct` am Anfang gehört **nicht**
> zur URI.

Warteschlange anlegen – die URI aus der eigenen `lpinfo -v`-Ausgabe
einsetzen (die Seriennummer ist bei jedem Gerät anders):

```bash
sudo lpadmin -p SELPHY -E \
  -v "gutenprint53+usb://canon-selphy-cp1500/DEINE-SERIENNUMMER" \
  -m "gutenprint.5.3://canon-cp1500/expert"

sudo lpadmin -p SELPHY -o media-default=Postcard
sudo lpoptions -d SELPHY
```

- Der Name `SELPHY` muss zur App-Einstellung `printer_name` passen
  (Standard ist `SELPHY` – wer nichts ändert, muss nichts anpassen).
- Die Treiber-Variante `expert` ist Pflicht: Nur sie bietet die
  Randlos-Optionen, die die App beim Drucken setzt.

### 6.4 Testdruck

Papier- und Farbkassette müssen eingelegt sein:

```bash
lpstat -p SELPHY
lp -d SELPHY -o PageSize=Postcard -o fit-to-page /usr/share/cups/data/testprint
```

✅ **Kontrollpunkt:** `lpstat` meldet „… ist im Leerlauf" und der Drucker
gibt nach ca. 1 Minute eine Testseite aus.

Hängt der Auftrag bei „Waiting for printer to become available": USB-Kabel
des Druckers ab- und wieder anstecken, hängende Aufträge mit
`cancel -a SELPHY` löschen, erneut versuchen. Bleibt es dabei →
**`PRINTER_FIX.md`** (häufigste Ursache: falsches USB-Backend in der Queue).

## Schritt 7: USB-Stick einrichten

Die Fotobox speichert Fotos und Collagen auf einem USB-Stick, der unter
`/media/usb` eingehängt sein muss (Pfad im Admin-Bereich änderbar).

1. Mount-Verzeichnis anlegen:
   ```bash
   sudo mkdir -p /media/usb
   ```

2. UUID des eingesteckten Sticks ermitteln:
   ```bash
   sudo blkid
   ```
   In der Ausgabe die Zeile des Sticks suchen (meist `/dev/sda1`) und die
   Werte `UUID="…"` und `TYPE="…"` notieren (TYPE ist z. B. `vfat` oder
   `exfat`).

3. Automatisches Einhängen beim Booten einrichten – Datei `/etc/fstab`
   bearbeiten:
   ```bash
   sudo nano /etc/fstab
   ```
   Am Ende **eine** neue Zeile anfügen (UUID und Typ durch die eigenen
   Werte ersetzen):
   ```text
   UUID=XXXX-XXXX  /media/usb  vfat  defaults,auto,users,rw,nofail,umask=000  0  0
   ```
   Speichern mit `Strg+O`, `Enter`, schließen mit `Strg+X`.

   > `nofail` ist wichtig: Damit startet der Pi auch dann normal, wenn
   > einmal kein Stick steckt.

4. Einhängen und prüfen:
   ```bash
   sudo systemctl daemon-reload
   sudo mount -a
   df -h /media/usb
   ```

✅ **Kontrollpunkt:** `df -h` zeigt den Stick mit seiner Größe unter
`/media/usb` an.

Die Ordner `Fotos/` und `Collagen/` legt die App selbst an – entweder
automatisch beim ersten Foto oder über den Button **„USB-Stick
vorbereiten"** im Admin-Bereich (Tab „Einstellungen", Abschnitt „Speicher").

## Schritt 8: Erster Start der Fotobox

Jetzt ist alles installiert. Erster Start im Entwicklungsmodus (Fenster
statt Vollbild, damit man alles im Blick hat):

```bash
cd ~/Fotobox
python3 src/main.py --dev
```

**Das sollte passieren:**

- Ein Fenster mit dem Startbildschirm öffnet sich.
- Im Terminal erscheinen Logzeilen, u. a.:
  - `Logging aktiv (Level=INFO) – Datei: …/fotobox.log`
  - `settings.json nicht vorhanden – wird mit Standardwerten angelegt.`
    (nur beim allerersten Start – die App erzeugt ihre Konfiguration selbst)
  - `Kamera bereit: Vorschau 1920x1080, …`
  - `GPIO initialisiert: Pins {…}`
  - `Fotobox gestartet (Dev-Modus=True)`

**Diese Warnungen dürfen NICHT erscheinen** (sonst den genannten Schritt
wiederholen):

| Warnung im Log | Dann fehlt … |
|---|---|
| `python-vlc/libVLC nicht verfügbar …` | Schritt 2 (`vlc`, `python3-vlc`) |
| `picamera2 nicht installiert …` / `Kamera-Initialisierung fehlgeschlagen …` | Schritt 2 bzw. Schritt 4 (Kamera) |
| `gpiozero nicht verfügbar …` | Schritt 2 (`python3-gpiozero`) |
| `pycups nicht verfügbar …` | Schritt 2 (`python3-cups`) |
| `Drucker 'SELPHY' nicht in CUPS gefunden …` | Schritt 6.3 (Warteschlange) |

**Bedienung beim Testen:**

| Taste | Funktion |
|---|---|
| LEERTASTE | Start-Taste (wie der GPIO-Taster) |
| F1 | Admin-Bereich öffnen/schließen |
| ESC | App beenden |

Die Meldung „Keine Pfade konfiguriert – Admin-Taste drücken" beim Druck auf
die Start-Taste ist beim ersten Start **normal** – die Inhalte werden erst
im nächsten Schritt angelegt. Eine ausführliche Erklärung aller Fehler- und
Warnmeldungen steht in **`ERROR_HANDLING.md`**.

## Schritt 9: Erstkonfiguration im Admin-Bereich

Mit **F1** (oder dem Admin-Taster) den Admin-Bereich öffnen und einmal
durchgehen:

1. **Szenen anlegen** (Bereich „Szenen"): Mindestens je eine Szene vom Typ
   *Begrüßung*, *Collage* und *Druck* erstellen – jeweils ein Bild und
   optional eine Audiodatei zuweisen. (Mediendateien vorher z. B. nach
   `~/Fotobox/assets/` kopieren.)
2. **Pfad anlegen** (Bereich „Pfade"): Einen Pfad erstellen, die drei
   Szenen zuweisen und die Anzahl der Fotos (1–4) wählen.
3. **Einstellungen prüfen** (Bereich „Einstellungen"):
   - **Druckername:** muss `SELPHY` sein (bzw. der in Schritt 6.3 gewählte
     Queue-Name).
   - **USB-Mount-Pfad:** muss `/media/usb` sein (bzw. der eigene Pfad).
   - **GPIO-Pins:** müssen zur Verkabelung aus Teil 1.3 passen.
   - **Demo-Modus:** für echten Druck **ausschalten** (im Demo-Modus wird
     absichtlich nicht gedruckt).
   - Optional: Collage-Cover (PNG, exakt 1800×1200 px), Startbildschirm-
     Hintergrund, Ladebalken-Farbe, System-Sounds.

**Kompletter Probedurchlauf:** Admin-Bereich schließen, LEERTASTE drücken –
es sollte laufen: Begrüßung → Countdown + Fotos → Collage → Druck → zurück
zum Start. Danach liegen die Bilder auf dem Stick unter
`/media/usb/Fotos/` und `/media/usb/Collagen/`, und der SELPHY druckt die
Collage aus.

## Schritt 10 (optional, empfohlen): Autostart beim Einschalten

Damit die Fotobox nach dem Einstecken des Stroms von selbst startet:

1. Automatische Desktop-Anmeldung aktivieren:
   ```bash
   sudo raspi-config
   ```
   → **System Options** → **Boot / Auto Login** → **Desktop Autologin**.

2. Autostart-Eintrag anlegen (Benutzername ggf. anpassen):
   ```bash
   mkdir -p ~/.config/autostart
   nano ~/.config/autostart/fotobox.desktop
   ```
   Inhalt (im `Exec`-Pfad `<benutzer>` durch den eigenen Benutzernamen
   ersetzen – anzeigen lassen mit `whoami`):
   ```ini
   [Desktop Entry]
   Type=Application
   Name=Fotobox
   Exec=/usr/bin/python3 /home/<benutzer>/Fotobox/src/main.py
   ```
   Speichern (`Strg+O`, `Enter`, `Strg+X`) und neu starten:
   ```bash
   sudo reboot
   ```

✅ **Kontrollpunkt:** Nach dem Booten erscheint die Fotobox automatisch im
Vollbild. (Beenden am angeschlossenen Keyboard weiterhin mit ESC.)

> Eine robustere Alternative über einen systemd-Service ist in `SETUP.md`,
> Abschnitt 5.9 beschrieben.

---

# Abschluss-Checkliste vor dem ersten Einsatz

| ✓ | Prüfung | Wie |
|---|---|---|
| ☐ | Kamera liefert Live-Bild | `rpicam-hello` oder Admin → Kameratest |
| ☐ | Ton kommt aus den Lautsprechern | `speaker-test -t wav -c 2` und Probedurchlauf |
| ☐ | Drucker druckt | Testdruck aus Schritt 6.4 **und** ein kompletter Probedurchlauf |
| ☐ | USB-Stick eingehängt | `df -h /media/usb` |
| ☐ | Taster und LEDs reagieren | Start-/Admin-Taster drücken; Bereit-LED leuchtet am Startbildschirm |
| ☐ | Mindestens 1 Pfad mit 3 Szenen angelegt | Admin-Bereich → Pfade |
| ☐ | Demo-Modus AUS | Admin-Bereich → Einstellungen |
| ☐ | Keine Warnungen beim App-Start | Terminal bzw. `~/Fotobox/fotobox.log` |
| ☐ | Genug Papier/Farbband im SELPHY | KP-108IN: 108 Drucke pro Set |
| ☐ | Autostart funktioniert | Pi vom Strom trennen, wieder einstecken |

**Bei Problemen:**

- `~/Fotobox/fotobox.log` lesen – jede Störung steht dort mit Ursache und
  Lösungshinweis (Nachschlagewerk: `ERROR_HANDLING.md`).
- Mehr Details: App mit `python3 src/main.py --debug` starten.
- Drucker: `PRINTER_SETUP.md` (Einrichtung) und `PRINTER_FIX.md` (hängende
  Aufträge).
- Audio: `FIX_AUDIO.md`.
- Verkabelung: `WIRING.md`.

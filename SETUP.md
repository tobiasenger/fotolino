# Fotobox – Setup & Vorgehensweise

## Übersicht

Dieses Dokument beschreibt die Vorbereitung der Entwicklungsumgebung, die Einrichtung des Raspberry Pi und den allgemeinen Entwicklungsworkflow für das Fotobox-Projekt.

---

## 1. Projektstruktur (geplant)

```
fotobox/
├── SETUP.md                    # Dieses Dokument
├── README.md
├── .gitignore
├── requirements.txt
├── config/
│   ├── settings.json           # Globale Einstellungen (GPIO-Pins, Pfade, Farben, ...)
│   ├── scenes.json             # Gespeicherte Szenen (Greeting, Collage, Print)
│   └── paths.json              # Konfigurierte Pfade mit Wahrscheinlichkeiten
├── src/
│   ├── main.py                 # Einstiegspunkt, App-State-Machine
│   ├── state.py                # Zentrale Zustandsverwaltung (ready, running, admin, ...)
│   ├── ui/
│   │   ├── screen_start.py     # Startscreen (Hintergrundbild/-video + Warte-Text)
│   │   ├── screen_intro.py     # Intro-Szene (Bild/Video + Audio)
│   │   ├── screen_capture.py   # Fotoaufnahme (Live-Preview, Countdown, Blitz)
│   │   ├── screen_collage.py   # Collagenerstellung (Ladebalken, Vorschau)
│   │   ├── screen_print.py     # Druckscreen (Ladebalken, Collage-Vorschau, Audio)
│   │   ├── admin/
│   │   │   ├── admin_main.py   # Admin-Hauptmenü (Navigation zwischen Sub-Views)
│   │   │   ├── admin_paths.py  # Pfad-Übersicht und -Editor
│   │   │   ├── admin_scenes.py # Szenen-Erstellung und -Verwaltung
│   │   │   └── admin_settings.py # Allgemeine Einstellungen
│   │   └── widgets.py          # Wiederverwendbare UI-Elemente (Buttons, Dropdowns, ...)
│   ├── camera.py               # Kamerasteuerung (picamera2)
│   ├── gpio_handler.py         # GPIO-Buttons und LEDs (Flash-LED + Ready-LED)
│   ├── audio.py                # Audiowiedergabe (MP3)
│   ├── collage.py              # Collagenerstellung (Pillow)
│   ├── printer.py              # Drucksteuerung (CUPS/pycups)
│   └── storage.py              # USB-Stick-Verwaltung
├── assets/
│   ├── CollageCovers/          # PNG-Vorlagen (cover_1.png – cover_4.png)
│   ├── backgrounds/            # Hintergrundbilder/-videos für den Startscreen
│   ├── sounds/                 # MP3-Dateien für Szenen
│   ├── images/                 # Bilder für Szenen (Intro-Screens)
│   └── videos/                 # Videodateien für Szenen
└── deploy/
    └── deploy.sh               # Deployment-Skript (rsync + Neustart auf dem Pi)
```

---

## 2. Datenmodell (Konfigurationsdateien)

### 2.1 `config/scenes.json` – Szenen-Definitionen

Jede Szene gehört zu einem der drei Typen `greeting`, `collage` oder `print`. Eine Szene enthält entweder ein Bild + Ton oder ein Video. Szenentyp und Mediendatei bestimmen die Laufzeit.

```json
{
  "scenes": [
    {
      "id": "scene_001",
      "type": "greeting",
      "name": "Fröhliche Begrüßung",
      "media_type": "photo",
      "image": "assets/images/img_smiley_happy.jpg",
      "audio": "assets/sounds/sound_welcome.mp3",
      "duration": 8
    },
    {
      "id": "scene_002",
      "type": "greeting",
      "name": "Video-Begrüßung",
      "media_type": "video",
      "video": "assets/videos/intro_video.mp4",
      "duration": 12
    },
    {
      "id": "scene_003",
      "type": "collage",
      "name": "Standard Collage-Screen",
      "media_type": "photo",
      "image": "assets/backgrounds/bg_collage.jpg",
      "audio": "assets/sounds/sound_creating.mp3",
      "duration": 10
    },
    {
      "id": "scene_004",
      "type": "print",
      "name": "Standard Druck-Screen",
      "media_type": "photo",
      "image": "assets/backgrounds/bg_print.jpg",
      "audio": "assets/sounds/sound_toll_gemacht.mp3",
      "duration": 40
    }
  ]
}
```

**Regeln für Szenenlängen:**

| Szenentyp  | Festdauer   | Erlaubte Medienlänge  |
|------------|-------------|-----------------------|
| `greeting` | variabel    | 5 – 25 Sekunden       |
| `collage`  | 10 Sekunden | max. 10 Sekunden      |
| `print`    | 40 Sekunden | max. 40 Sekunden      |

Die Laufzeit einer Szene folgt automatisch der Länge des Videos oder der MP3-Datei. Bei Bild+Ton gilt die MP3-Dauer; bei reinem Bild (ohne Ton) muss die Dauer manuell angegeben werden.

### 2.2 `config/paths.json` – Pfad-Definitionen

```json
{
  "paths": [
    {
      "id": "path_001",
      "name": "Standard-Pfad",
      "probability": 73,
      "is_default": true,
      "scenes": {
        "greeting": "scene_001",
        "capture_count": 4,
        "collage": "scene_003",
        "print": "scene_004"
      }
    },
    {
      "id": "path_002",
      "name": "Nur Begrüßung (kein Foto)",
      "probability": 2,
      "is_default": false,
      "scenes": {
        "greeting": "scene_002",
        "capture_count": 0
      }
    }
  ]
}
```

**Wahrscheinlichkeitslogik:**
- Pfad 1 (Default) erhält automatisch die Restwahrscheinlichkeit: `100% – Summe aller anderen Pfade`.
- Alle weiteren Pfade haben manuell eingetragene Prozentwerte, die vom Default abgezogen werden.
- `capture_count: 0` bedeutet: Pfad endet nach der Begrüßungsszene. `collage` und `print` sind dann nicht erforderlich.
- Bei `capture_count` 1–4 müssen `collage` und `print` zwingend gesetzt sein.

### 2.3 `config/settings.json` – Globale Einstellungen

```json
{
  "gpio": {
    "pin_start_button": 17,
    "pin_admin_button": 27,
    "pin_led_flash": 22,
    "pin_led_ready": 23
  },
  "collage_covers": {
    "1_photo": "assets/CollageCovers/cover_1.png",
    "2_photos": "assets/CollageCovers/cover_2.png",
    "3_photos": "assets/CollageCovers/cover_3.png",
    "4_photos": "assets/CollageCovers/cover_4.png"
  },
  "idle_background": {
    "type": "image",
    "file": "assets/backgrounds/bg_start.jpg"
  },
  "loading_bar_color": "#FF6600",
  "flash_enabled": true,
  "printer_name": "SELPHY",
  "usb_mount": "/media/usb"
}
```

---

## 3. Anwendungslogik

### 3.1 Zustands-Machine (App-States)

```
READY  ──(Start-Button)──▶  INTRO
                               │
                     (capture_count == 0)
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
                 READY             CAPTURE (1–4 Fotos)
                                         │
                                         ▼
                                      COLLAGE
                                         │
                                         ▼
                                       PRINT
                                         │
                                         ▼
                                       READY

READY / RUNNING / PRINT ──(Admin-Button)──▶  ADMIN
ADMIN ──(Admin-Button)──▶  (vorheriger Zustand)
```

### 3.2 Ready-LED (Betriebsbereitschaftsanzeige)

Die **Ready-LED** (GPIO `pin_led_ready`) signalisiert den Bereitschaftszustand der Fotobox:

- **AN:** Applikation befindet sich im `READY`-Zustand (Startscreen wartet auf Tastendruck).
- **AUS:** Sobald der Start-Button gedrückt wird, erlischt die LED sofort.
- **Wieder AN:** Erst wenn die Applikation nach dem Abschluss eines vollständigen Pfades (also nach dem Print-Screen oder direkt nach der Begrüßung bei `capture_count: 0`) wieder in den `READY`-Zustand wechselt.
- Im Admin-Modus: LED bleibt aus (Gerät ist nicht für Gäste bereit).

### 3.3 Flash-LED

Die **Flash-LED** (GPIO `pin_led_flash`) ist nur während der Fotoaufnahme aktiv:

- **AN:** Zu Beginn des `CAPTURE`-Screens (während die Kamera läuft und Fotos aufgenommen werden).
- **AUS:** Sobald alle Fotos aufgenommen wurden und der Screen beendet wird.
- Kann in den allgemeinen Einstellungen global deaktiviert werden (`flash_enabled: false`).

### 3.4 Admin-Modus

Der **Admin-Button** (GPIO `pin_admin_button`) schaltet zwischen Normal- und Admin-Ansicht um:

- Ein Druck auf den Admin-Button während des `READY`-Zustands oder des laufenden Betriebs öffnet die Admin-Ansicht.
- Ein erneuter Druck auf den Admin-Button schließt die Admin-Ansicht und kehrt in den vorherigen Zustand zurück.
- Läuft gerade ein Pfad (Foto, Collage, Druck), wird der Admin-Button ignoriert – oder er unterbricht den Pfad nur nach expliziter Bestätigung (Designentscheidung, wird in der Implementierung festgelegt).

---

## 4. Admin-Menü (Konzept)

Das Admin-Menü ist in drei Sub-Views gegliedert, die über eine Navigationsleiste am oberen Bildschirmrand erreichbar sind.

### 4.1 Pfad-Übersicht (`admin_paths.py`)

**Listenansicht:**
- Alle konfigurierten Pfade werden als Karten angezeigt, sortiert nach Erstellungsreihenfolge.
- Jede Karte zeigt: Name, zugewiesene Szene (Begrüßung), Aufnahmetyp (0–4 Fotos), Wahrscheinlichkeit in %.
- Der Default-Pfad ist visuell hervorgehoben (z. B. farbiger Rahmen oder „Standard"-Badge).
- Die Restwahrscheinlichkeit des Default-Pfads wird automatisch berechnet und angezeigt.
- Ein „**+**"-Button öffnet den Pfad-Editor für einen neuen Pfad.
- Jede Pfad-Karte hat einen „**Bearbeiten**"-Button.

**Pfad-Editor:**
- **Name:** Freitextfeld.
- **Wahrscheinlichkeit:** Zahleneingabe in % (nur für Nicht-Default-Pfade; Default-Wahrscheinlichkeit ist read-only und zeigt Restwert).
- **Begrüßungsszene:** Dropdown-Menü mit allen Szenen vom Typ `greeting`.
- **Aufnahmetyp:** Dropdown-Menü: `0 – Kein Foto`, `1 Foto`, `2 Fotos`, `3 Fotos`, `4 Fotos`.
- **Collage-Szene:** Dropdown-Menü mit allen Szenen vom Typ `collage`. Nur sichtbar/pflichtfeld, wenn Aufnahmetyp ≥ 1.
- **Druck-Szene:** Dropdown-Menü mit allen Szenen vom Typ `print`. Nur sichtbar/pflichtfeld, wenn Aufnahmetyp ≥ 1.
- **Speichern / Abbrechen / Löschen**-Buttons.

### 4.2 Szenen-Verwaltung (`admin_scenes.py`)

**Listenansicht:**
- Alle Szenen aufgeteilt in drei Tabs: „Begrüßung", „Collage", „Druck".
- Jede Szene zeigt: Name, Medientyp (Foto/Video), Laufzeit, vorschau-Icon.
- „**+**"-Button zum Erstellen einer neuen Szene.
- „**Bearbeiten**"- und „**Löschen**"-Buttons je Szene.

**Szenen-Editor (neu anlegen / bearbeiten):**

1. **Szenentyp wählen:** Dropdown: `Begrüßung`, `Collage`, `Druck`.
2. **Medientyp wählen:** Dropdown: `Foto + Ton`, `Video`.
3. **Wenn Foto + Ton:**
   - Dateiauswahl für Bild (`.jpg`, `.png`).
   - Dateiauswahl für Audio (`.mp3`). Die Dauer der MP3 bestimmt die Szenenläge. Die MP3 darf die für den Szenentyp festgelegte Maximallänge nicht überschreiten – eine Fehlermeldung erscheint andernfalls.
4. **Wenn Video:**
   - Dateiauswahl für Videodatei (`.mp4`). Das Video wird im Vollbild abgespielt. Die Videodauer bestimmt die Szenenlänge. Die Videodauer darf die für den Szenentyp festgelegte Maximallänge nicht überschreiten.
5. **Name:** Freitextfeld.
6. **Vorschau der berechneten Dauer** wird angezeigt.
7. **Speichern**-Button.

**Löschen einer Szene:**
- Wenn die zu löschende Szene in mindestens einem Pfad verwendet wird, erscheint ein Bestätigungs-Popup: „Diese Szene wird von [n] Pfad(en) verwendet. Das Löschen führt dazu, dass diese Pfade ebenfalls gelöscht werden. Fortfahren?"
- Bestätigung löscht Szene und alle abhängigen Pfade.

### 4.3 Allgemeine Einstellungen (`admin_settings.py`)

- **Collage-Overlays:** Je ein Datei-Upload-Feld für `cover_1.png` bis `cover_4.png` (PNG mit Transparenz). Beim Upload wird zwingend geprüft, ob die Bildgröße exakt **1800×1200 px** beträgt – andernfalls erscheint eine Fehlermeldung und die Datei wird abgelehnt. Ungültige Dateien dürfen nicht gespeichert werden.
- **Startscreen-Hintergrund:** Auswahl zwischen Bild (`.jpg`, `.png`) oder Video-Loop (`.mp4`). Dateiauswahl per Upload-Button.
- **Ladebalken-Farbe:** Farbwähler (Hex-Wert) für die Ladebalkenfüllung auf dem Collage- und Druck-Screen.
- **Blitz-LED:** Toggle-Schalter (Ein/Aus) – deaktiviert die Flash-LED global, auch wenn GPIO angeschlossen ist.
- **GPIO-Pins:** Eingabefelder für alle vier GPIO-Pin-Nummern (Start-Button, Admin-Button, Flash-LED, Ready-LED), damit das Layout ohne Code-Änderung angepasst werden kann.
- **Druckername (CUPS):** Textfeld für den CUPS-Druckernamen.
- **USB-Mount-Pfad:** Textfeld für den Mount-Punkt des USB-Sticks.

---

## 5. Raspberry Pi vorbereiten

### 5.1 Betriebssystem installieren

1. **Raspberry Pi Imager** herunterladen: https://www.raspberrypi.com/software/
2. OS wählen: **Raspberry Pi OS Desktop (64-bit)** – ermöglicht HDMI-Ausgabe und GUI direkt nach dem Booten.
3. In den erweiterten Einstellungen des Imagers vorab konfigurieren:
   - Hostname setzen: `fotobox`
   - SSH aktivieren
   - WLAN **nicht** konfigurieren (Verbindung über LAN-Kabel)
   - Benutzername und Passwort festlegen (z. B. `pi` / sicheres Passwort)
   - Zeitzone: `Europe/Berlin`
   - Tastaturlayout: `de`
4. Image auf die SD-Karte schreiben und in den Pi einsetzen.

### 5.2 Erstes Booten und SSH-Zugang

1. Pi mit LAN-Kabel, Monitor, Tastatur und Maus verbinden, dann einschalten.
2. IP-Adresse herausfinden (am Router oder direkt auf dem Pi):
   ```bash
   hostname -I
   ```
3. Vom Mac aus verbinden:
   ```bash
   ssh admin@fotobox.local
   # alternativ (direkt per IP):
   ssh admin@192.168.178.69
   ```
4. System aktualisieren:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo reboot
   ```

### 5.3 Kamera einrichten (IMX708)

Der IMX708 ist libcamera-kompatibel und wird unter Raspberry Pi OS 64-bit automatisch erkannt.

1. Kameramodul in den CSI-Port einsetzen (Kabel: blaue Seite zeigt zur USB-Buchse des Pi).
2. Kamera aktivieren (falls nicht bereits automatisch erkannt):
   ```bash
   sudo raspi-config
   # → Interface Options → Camera → Enable
   ```
3. Funktion prüfen:
   ```bash
   rpicam-hello
   ```
4. Python-Bibliothek installieren:
   ```bash
   sudo apt install -y python3-picamera2
   ```

### 5.4 GPIO einrichten

**Geplante GPIO-Belegung (alle Pins in der Konfiguration änderbar):**

| Funktion         | Typ    | GPIO-Beispielpin | Beschreibung                                      |
|------------------|--------|------------------|---------------------------------------------------|
| Start-Button     | Input  | GPIO 17          | Startet einen Pfad vom Startscreen aus            |
| Admin-Button     | Input  | GPIO 27          | Wechselt zwischen Normal- und Admin-Ansicht       |
| Flash-LED        | Output | GPIO 22          | Aktiv nur während der Fotoaufnahme                |
| Ready-LED        | Output | GPIO 23          | AN im READY-Zustand; AUS während laufendem Pfad   |

Buttons werden mit internem Pull-up-Widerstand betrieben (aktiv LOW).

**Installation:**
```bash
sudo apt install -y python3-gpiozero python3-rpi.gpio
```

**GPIO-Zugriff ohne `sudo`:**
```bash
sudo usermod -aG gpio admin
```

### 5.5 Audio einrichten

1. Audioausgabe auf den 3,5-mm-Klinkenanschluss erzwingen:
   ```bash
   sudo raspi-config
   # → System Options → Audio → 3.5mm jack
   ```
2. Lautsprecher testen:
   ```bash
   speaker-test -t wav -c 2
   ```
3. Python-Bibliotheken:
   ```bash
   sudo apt install -y python3-pygame mpg123
   ```

### 5.6 Drucker einrichten (Canon SELPHY CP1500)

**CUPS installieren:**
```bash
sudo apt install -y cups cups-client printer-driver-gutenprint
sudo usermod -aG lpadmin admin
sudo systemctl enable cups && sudo systemctl start cups
sudo cupsctl --remote-admin
```

CUPS-Webinterface aufrufen (vom Mac im Browser): `http://fotobox.local:631`

**Drucker hinzufügen:**
```bash
# USB:
lpadmin -p SELPHY -E -v usb://Canon/CP1500 -m gutenprint.5.3://canon-cp1500/expert
# WLAN:
lpadmin -p SELPHY -E -v ipp://DRUCKER-IP/ipp/print -m gutenprint.5.3://canon-cp1500/expert
```

**Testdruck:**
```bash
lp -d SELPHY /usr/share/cups/data/testprint
```

**Python-Integration:**
```bash
pip3 install --break-system-packages pycups
```

### 5.7 USB-Stick einrichten

```bash
sudo apt install -y udisks2
sudo mkdir -p /media/usb
```

Festen Mount-Eintrag in `/etc/fstab` (UUID mit `blkid` ermitteln):
```
UUID=<USB-UUID>  /media/usb  vfat  defaults,auto,users,rw,nofail  0  0
```

Ordner auf dem USB-Stick anlegen:
```bash
mkdir -p /media/usb/Fotos /media/usb/Collagen
```

### 5.8 Programm als ausführbare Datei verpacken (nach Abschluss der Entwicklung)

Das fertige Programm soll als einzelne ausführbare Datei auf dem Pi bereitstehen. Dafür gibt es zwei empfohlene Ansätze:

**Option A: PyInstaller (einzelnes Binary, empfohlen)**

PyInstaller kompiliert das Python-Projekt in eine selbstständige ausführbare Datei, die ohne installiertes Python ausgeführt werden kann. Der Build muss **auf dem Raspberry Pi** selbst durchgeführt werden, da PyInstaller plattformspezifische Binaries erzeugt (ARM64).

```bash
# Auf dem Pi:
pip3 install --break-system-packages pyinstaller

cd ~/fotobox
pyinstaller --onefile --name fotobox src/main.py
```

Das fertige Binary liegt anschließend unter `dist/fotobox`. Es kann beliebig kopiert oder direkt gestartet werden:

```bash
./dist/fotobox
```

> Hinweis: Bei Nutzung von `picamera2`, `pygame` und anderen systemeigenen Bibliotheken müssen diese ggf. explizit als Hidden Imports oder Data Files in der `.spec`-Datei ergänzt werden. Eine `fotobox.spec`-Datei sollte nach dem ersten Build im Repository gepflegt werden.

**Option B: Shell-Wrapper-Skript (einfacher, für Entwicklung)**

```bash
#!/bin/bash
cd /home/admin/fotobox
exec python3 src/main.py "$@"
```

Als ausführbare Datei speichern:
```bash
chmod +x /home/admin/fotobox/fotobox.sh
```

### 5.9 Autostart beim Booten konfigurieren

**Schritt 1 – Automatisches Login aktivieren:**
```bash
sudo raspi-config
# → System Options → Boot / Auto Login → Desktop Autologin
```

**Schritt 2A – Desktop-Autostart (LXDE/PIXEL):**

Datei `~/.config/autostart/fotobox.desktop` anlegen:
```ini
[Desktop Entry]
Type=Application
Name=Fotobox
Exec=/home/admin/fotobox/dist/fotobox
```

Für die Shell-Wrapper-Variante:
```ini
[Desktop Entry]
Type=Application
Name=Fotobox
Exec=/home/admin/fotobox/fotobox.sh
```

**Schritt 2B – systemd-Service (robuster, auch ohne Desktop)**

Datei `/etc/systemd/system/fotobox.service` anlegen:
```ini
[Unit]
Description=Fotobox
After=graphical.target

[Service]
User=admin
WorkingDirectory=/home/admin/fotobox
ExecStart=/home/admin/fotobox/dist/fotobox
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/admin/.Xauthority

[Install]
WantedBy=graphical.target
```

Service aktivieren:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fotobox.service
sudo systemctl start fotobox.service
```

Logs anzeigen:
```bash
journalctl -u fotobox.service -f
```

### 5.9 Benötigte Python-Pakete (Gesamtübersicht)

```bash
sudo apt install -y \
  python3-picamera2 \
  python3-pygame \
  python3-gpiozero \
  python3-rpi.gpio \
  python3-pil \
  python3-pip \
  mpg123

pip3 install --break-system-packages \
  pycups \
  pillow \
  numpy \
  mutagen
```

> `mutagen` wird benötigt, um die Länge von MP3-Dateien und Videos auszulesen (für die Validierung der Szenendauer im Admin-Menü).

---

## 6. GitHub Repository einrichten

### 6.1 Auf dem Mac

1. **Git installieren** (falls nicht vorhanden):
   ```bash
   brew install git
   ```
2. **GitHub-Account** unter https://github.com erstellen (falls noch nicht vorhanden).
3. **Neues Repository anlegen:**
   - Auf GitHub: „New repository" → Name `fotobox` → Private → ohne README anlegen.
4. **Lokales Projekt initialisieren:**
   ```bash
   cd ~/Documents/Claude\ Code/fotobox
   git init
   git branch -M main
   ```
5. **`.gitignore` anlegen:**
   ```
   __pycache__/
   *.pyc
   .env
   config/settings.local.json
   assets/sounds/
   assets/images/
   assets/videos/
   assets/CollageCovers/
   assets/backgrounds/
   /media/
   *.log
   ```
6. **Remote hinzufügen und pushen:**
   ```bash
   git remote add origin https://github.com/<dein-benutzername>/fotobox.git
   git add .
   git commit -m "Initial commit: project structure and setup docs"
   git push -u origin main
   ```

### 6.2 Auf dem Raspberry Pi

```bash
sudo apt install -y git
cd ~
cd ~
git clone https://github.com/<dein-benutzername>/fotobox.git
```

---

## 7. Entwicklungsworkflow (Mac → Raspberry Pi)

### 7.1 Entwicklungsumgebung auf dem Mac

Das Projekt wird auf dem Mac entwickelt und auf den Raspberry Pi deployed. Zwei Arbeitsweisen sind vorgesehen:

**Option A: Terminal + Claude Code CLI**
- Entwicklung direkt im Terminal mit Claude Code als KI-Assistent.
- Claude Code liest und bearbeitet Dateien lokal auf dem Mac, Deployment erfolgt über `rsync` oder Git.
- Starten:
  ```bash
  cd ~/Documents/Claude\ Code/fotobox
  claude
  ```

**Option B: Antigravity IDE**
- Entwicklung in der Antigravity IDE mit integriertem Claude-Assistenten.
- Projektordner `~/Documents/Claude Code/fotobox` in der IDE öffnen.
- Claude ist direkt in den Editor integriert und kann Dateien lesen, bearbeiten und erklären.
- Deployment über das integrierte Terminal oder das `deploy.sh`-Skript.

Beide Varianten arbeiten auf demselben lokalen Projektordner und sind vollständig kompatibel – ein Wechsel zwischen ihnen ist jederzeit möglich.

### 7.2 Code auf den Pi übertragen

**Variante 1: `rsync`-Skript (schnell, kein Git-Commit nötig)**

Skript `deploy/deploy.sh`:
```bash
#!/bin/bash
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  ~/Documents/Claude\ Code/fotobox/ \
  admin@fotobox.local:~/fotobox/
ssh admin@fotobox.local "pkill -f main.py; sleep 1; cd ~/fotobox && python3 src/main.py"
```

Ausführbar machen:
```bash
chmod +x deploy/deploy.sh
```

Ausführen:
```bash
./deploy/deploy.sh
```

**Variante 2: Git-basiertes Deployment**

```bash
# Auf dem Mac:
git push origin main

# Auf dem Pi (per SSH):
cd ~/fotobox && git pull origin main && python3 src/main.py
```

### 7.3 SSH-Schlüssel einrichten (Passwort-freier Zugang)

```bash
ssh-keygen -t ed25519 -C "fotobox-dev"
ssh-copy-id admin@fotobox.local.local
```

### 7.4 Remote-Terminal auf dem Pi (aus Mac-Terminal)

```bash
ssh admin@fotobox.local
```

Logs direkt streamen:
```bash
ssh admin@fotobox.local "cd ~/fotobox && python3 src/main.py"
```

---

## 8. Nächste Schritte (Entwicklungsreihenfolge)

1. Projektstruktur anlegen: leere Quelldateien, `requirements.txt`, `.gitignore`, GitHub-Repo initialisieren und pushen.
2. Konfigurationsschema finalisieren (`settings.json`, `scenes.json`, `paths.json`).
3. GPIO-Handler implementieren: Start-Button, Admin-Button, Flash-LED, Ready-LED.
4. Zustandsmaschine (`state.py`) implementieren: alle App-States und Übergänge.
5. Startscreen implementieren: Hintergrundbild/-video, Ready-LED-Steuerung.
6. Kamera-Modul: Live-Preview im Capture-Screen, Countdown-Overlay, Fotoaufnahme, Blitz-LED.
7. Audio-Modul: MP3-Wiedergabe, Dauer auslesen.
8. Intro-Screen: Bild+Ton oder Video vollflächig abspielen.
9. Collage-Screen: Pillow-basierte Erstellung, PNG-Overlay, Ladebalken.
10. Druck-Screen: Collage anzeigen, CUPS-Druck, Ladebalken, Audio.
11. USB-Stick-Integration: Fotos und Collagen speichern.
12. Admin-Menü implementieren:
    a. Grundstruktur + Navigation (3 Tabs)
    b. Szenen-Verwaltung (erstellen, bearbeiten, löschen mit Abhängigkeitsprüfung)
    c. Pfad-Verwaltung (erstellen, Wahrscheinlichkeiten, Default-Pfad)
    d. Allgemeine Einstellungen (Uploads, Farben, GPIO-Pins, Schalter)
13. Pfad-Auswahllogik implementieren (gewichteter Zufallsalgorithmus).
14. Autostart beim Booten konfigurieren.
15. Tests, Fehlerbehandlung und Feinschliff.

---

## 9. Collage-Canvas-Spezifikation

**Ausgabeformat: 1800×1200 px (3:2 Querformat)**

Fotos werden in ihre jeweilige Bounding Box hineingerechnet: skaliert unter Beibehaltung des Seitenverhältnisses, zentriert, überstehende Ränder werden abgeschnitten (Crop-to-fill). Nach dem Platzieren aller Fotos wird das PNG-Overlay (1800×1200 px, RGBA) darübergelegt. Das Ergebnis wird als JPEG gespeichert.

---

### Layout 1 – 1 Foto

Das Foto ist zentriert, mit einem gleichmäßigen Rand von 100 px auf allen Seiten.

```
┌──────────────────────────────────────┐  1800×1200
│                                      │
│   ┌──────────────────────────────┐   │  y=100
│   │                              │   │
│   │          Foto 1              │   │
│   │        1600×1000             │   │
│   │                              │   │
│   └──────────────────────────────┘   │  y=1100
│                                      │
└──────────────────────────────────────┘
    x=100                         x=1700
```

| Foto | x   | y   | Breite | Höhe |
|------|-----|-----|--------|------|
| 1    | 100 | 100 | 1600   | 1000 |

---

### Layout 2 – 2 Fotos (um 90° rotiert)

Die Fotos werden vor dem Platzieren um 90° gedreht (Hochformat). Beide Fotos sind gleich groß, mit einem äußeren Rand von 80 px und einem mittleren Abstand von 60 px.

```
┌──────────────────────────────────────┐  1800×1200
│  ┌──────────────┐  ┌──────────────┐  │  y=80
│  │              │  │              │  │
│  │    Foto 1    │  │    Foto 2    │  │
│  │  (rotiert)   │  │  (rotiert)   │  │
│  │   790×1040   │  │   790×1040   │  │
│  │              │  │              │  │
│  └──────────────┘  └──────────────┘  │  y=1120
│  x=80          x=870               │
│             x=930              x=1720│
└──────────────────────────────────────┘
```

| Foto | Rotation | x   | y  | Breite | Höhe |
|------|----------|-----|----|--------|------|
| 1    | 90°      | 80  | 80 | 790    | 1040 |
| 2    | 90°      | 930 | 80 | 790    | 1040 |

Abstand Mitte: 60 px (930 − 80 − 790 = 60). Rand links/rechts: 80 px.

---

### Layout 3 – 3 Fotos (unterschiedliche Größen)

Foto 1 ist das größte und nimmt die linke Seite vollständig ein. Foto 2 und 3 sind gleich groß und sind auf der rechten Seite übereinander angeordnet. Äußerer Rand: 60 px, innerer Abstand: 40 px.

```
┌──────────────────────────────────────┐  1800×1200
│  ┌──────────────────┐  ┌──────────┐  │  y=60
│  │                  │  │  Foto 2  │  │
│  │                  │  │ 540×520  │  │
│  │     Foto 1       │  └──────────┘  │  y=620
│  │    1100×1080     │  ┌──────────┐  │
│  │                  │  │  Foto 3  │  │
│  │                  │  │ 540×520  │  │
│  └──────────────────┘  └──────────┘  │  y=1140
│  x=60           x=1160 x=1200  x=1740│
└──────────────────────────────────────┘
```

| Foto | x    | y   | Breite | Höhe |
|------|------|-----|--------|------|
| 1    | 60   | 60  | 1100   | 1080 |
| 2    | 1200 | 60  | 540    | 520  |
| 3    | 1200 | 620 | 540    | 520  |

Prüfung: 60 + 1100 + 40 + 540 + 60 = 1800 ✓ | 60 + 520 + 40 + 520 + 60 = 1200 ✓

---

### Layout 4 – 4 Fotos (2×2 Raster mit horizontalem Versatz)

Alle Fotos haben die gleiche Größe. Die obere Reihe ist 40 px nach links versetzt, die untere Reihe 40 px nach rechts versetzt. Der Abstand zwischen den Fotos bleibt in beiden Reihen gleich (40 px). Basisgitter: äußerer Rand 60 px, innerer Abstand 40 px.

```
┌──────────────────────────────────────┐  1800×1200
│┌─────────────────┐  ┌──────────────┐ │  y=60
││     Foto 1      │  │    Foto 2    │ │
││     820×520     │  │    820×520   │ │
│└─────────────────┘  └──────────────┘ │  y=580
│  ┌──────────────┐  ┌─────────────────┐│  y=620
│  │    Foto 3    │  │     Foto 4      ││
│  │    820×520   │  │     820×520     ││
│  └──────────────┘  └─────────────────┘│  y=1140
│x=20   x=840  x=880   x=920   x=1740 x=1780
└──────────────────────────────────────┘
```

| Foto | Reihe  | x   | y   | Breite | Höhe | Versatz     |
|------|--------|-----|-----|--------|------|-------------|
| 1    | oben   | 20  | 60  | 820    | 520  | −40 px (links) |
| 2    | oben   | 880 | 60  | 820    | 520  | −40 px (links) |
| 3    | unten  | 100 | 620 | 820    | 520  | +40 px (rechts) |
| 4    | unten  | 960 | 620 | 820    | 520  | +40 px (rechts) |

Abstand jeweils: 880 − 20 − 820 = 40 px ✓ (oben) | 960 − 100 − 820 = 40 px ✓ (unten)

---

### Overlay-Spezifikation

Die PNG-Overlays werden vom Nutzer selbst erstellt und über das Admin-Menü hochgeladen.

- **Format:** PNG mit Alphakanal (RGBA)
- **Größe:** exakt **1800×1200 px** (wird beim Upload validiert)
- **Dateibenennung intern:** `cover_1.png`, `cover_2.png`, `cover_3.png`, `cover_4.png`
- **Funktion:** Das Overlay wird als oberste Ebene über das fertige Foto-Canvas gelegt (Alpha-Compositing). Cutouts (transparente Bereiche) geben die Foto-Positionen frei. Rahmen, Dekorationen und Text können im PNG gestaltet werden.

---

## 10. Technische Entscheidungen (festgelegt / zu klären)

| Thema                  | Entscheidung / Status                                                                 |
|------------------------|---------------------------------------------------------------------------------------|
| UI-Framework           | **pygame** – volle Kontrolle über Vollbild, Kamera-Preview, Animationen               |
| Konfigurationsformat   | **JSON** – `settings.json`, `scenes.json`, `paths.json` getrennt                      |
| Collage-Rendering      | **Pillow (PIL)** – PNG-Overlays mit Transparenz über Fotos legen                      |
| GPIO-Bibliothek        | **gpiozero** – einfacher, abstrahierter Zugriff                                       |
| Audio-Wiedergabe       | **pygame.mixer** – MP3-Support, gut in pygame-App integrierbar                        |
| Videowiedergabe        | zu klären – `pygame` + `ffmpeg` oder externer Player (`omxplayer` / `mpv`)            |
| Druckeranbindung       | **CUPS + pycups** – USB oder WLAN (WLAN bevorzugt)                                    |
| MP3/Video-Dauer auslesen | **mutagen** (Audio), **cv2 / ffprobe** (Video)                                      |
| Admin-UI-Widgets       | pygame-eigene Implementierung oder leichtgewichtige Bibliothek (z. B. `pygame_gui`)   |
| Entwicklungsumgebung   | **Terminal + Claude Code CLI** und **Antigravity IDE**                                |
| Executable-Packaging   | **PyInstaller** (`--onefile`) – Build auf dem Pi, ARM64-Binary in `dist/fotobox`      |
| Autostart              | systemd-Service (`fotobox.service`) – robuster als Desktop-Autostart                  |

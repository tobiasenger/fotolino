# Fehler- und Warnungsbehandlung der Fotobox

Dieses Dokument beschreibt, wie die Fotobox mit Fehlern umgeht, welche
Meldungen im Log bzw. auf dem Bildschirm erscheinen können, was sie bedeuten
und wie sie behoben werden.

---

## 1. Wie das Logging funktioniert

**Wohin wird geloggt?**

| Ziel | Beschreibung |
|---|---|
| Konsole (stdout) | Alle Meldungen ab Level INFO (mit `--debug`: ab DEBUG) |
| `fotobox.log` im Projektordner | Gleiche Meldungen als Datei; rotiert automatisch bei 1 MB, 3 Backups (`fotobox.log.1` … `.3`) |
| Bildschirm-Meldung (oben links) | Wichtige Fehler/Warnungen für den Betreiber; jede Bildschirm-Meldung landet zusätzlich mit Präfix `[Meldung]` im Log |

**Format:** `2026-06-11 14:30:00,123 [LEVEL] modulname: Meldungstext`

**Start mit ausführlichem Logging:**

```bash
python src/main.py --debug      # zeigt zusätzlich DEBUG-Meldungen
```

**Log-Level und ihre Bedeutung:**

| Level | Bedeutung | Beispiel |
|---|---|---|
| DEBUG | Nur für die Fehlersuche, im Normalbetrieb unsichtbar | „Kamera-Vorschau gestartet" |
| INFO | Normaler Betriebsablauf | „Screen-Wechsel: capture" |
| WARNING | Etwas fehlt oder schlug fehl, **die App läuft mit einem Fallback weiter** | „picamera2 nicht installiert – Mock-Kamera aktiv" |
| ERROR | Eine Funktion ist ausgefallen (z. B. Druck), die App läuft aber weiter | „Druckfehler (CUPS IPP …)" |

**Grundprinzip der Fehlerbehandlung:** Die Fotobox stürzt im Gästebetrieb
nie wegen eines Geräteproblems ab. Jedes Subsystem (Kamera, GPIO, Audio,
Drucker, USB-Speicher) hat einen Fallback:

| Subsystem | Fallback bei Ausfall |
|---|---|
| Kamera | Mock-Kamera mit Testbild |
| GPIO-Taster | Tastatur: LEERTASTE = Start, F1 = Admin |
| Audio (libVLC) | aplay (nur WAV) → QSoundEffect → Stille |
| Video-Szene | Bild + Audio der Szene |
| USB-Stick | Fotos werden temporär in `/tmp` zwischengespeichert |
| Drucker | Fehlermeldung auf dem Bildschirm, Sitzung läuft normal zu Ende |
| Defekte Config-Datei | Sicherung als `*.json.broken`, Standardwerte werden verwendet |

---

## 2. Start / Systemvoraussetzungen

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `ERROR: PyQt6 ist nicht installiert.` (auf stderr, App beendet sich) | fatal | Qt-Bibliothek fehlt – ohne sie kann die App nicht starten | Pi: `sudo apt install -y python3-pyqt6 python3-pyqt6.qtmultimedia` · Mac: `pip3 install -r requirements.txt` |
| `Logging aktiv (Level=…) – Datei: …` | INFO | Normale Startmeldung; zeigt, wo die Logdatei liegt | – |
| `Fotobox gestartet (Dev-Modus=…)` | INFO | App-Start abgeschlossen | – |

---

## 3. Konfiguration (`config/*.json`)

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `settings.json nicht vorhanden – wird mit Standardwerten angelegt.` | INFO | Erster Start oder Datei wurde gelöscht; normal bei Neuinstallation | – |
| `… konnte nicht geladen werden (…) – Standardwerte werden verwendet.` | WARNING | JSON-Datei ist defekt (Syntaxfehler) oder nicht lesbar | Die defekte Datei wird automatisch als `*.json.broken` gesichert. Datei reparieren (JSON-Syntax prüfen) und zurückbenennen, sonst alle Einstellungen im Admin-Bereich neu setzen |
| `… hat eine unerwartete Struktur (kein JSON-Objekt) – Standardwerte werden verwendet.` | WARNING | Datei enthält gültiges JSON, aber nicht das erwartete Format (z. B. eine Liste statt eines Objekts) | Wie oben: `.broken`-Sicherung prüfen und korrigieren |
| `Defekte Datei gesichert als: ….broken` | WARNING | Begleitmeldung zur automatischen Sicherung | – |

**Hinweis:** Alle Schreibvorgänge sind atomar (Temp-Datei + Umbenennen) –
ein Stromausfall kann die Konfiguration nicht halb geschrieben hinterlassen.

---

## 4. Kamera (`src/camera.py`)

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `picamera2 nicht installiert – Mock-Kamera (Testbild) aktiv` | INFO | Normal auf dem Entwicklungs-Mac. Auf dem Pi: Paket fehlt | Pi: `sudo apt install -y python3-picamera2` |
| `Kamera-Initialisierung fehlgeschlagen (…) – Mock-Kamera (Testbild) aktiv.` | WARNING | picamera2 ist installiert, aber die Kamera reagiert nicht (Kabel, belegt durch anderen Prozess, deaktiviert) | Flachbandkabel an Kamera und Pi prüfen; `rpicam-hello` im Terminal testen; prüfen, ob ein anderer Prozess die Kamera belegt |
| `Still-Konfiguration fehlgeschlagen (…) – Fotos werden in Vorschau-Auflösung aufgenommen.` | WARNING | Volle Sensorauflösung nicht verfügbar; Fotos haben dann nur Bildschirmauflösung | Meist harmlos. Bei dauerhaftem Auftreten Kameramodul/Treiberversion prüfen |
| `Vorschaubild konnte nicht gelesen werden (…) – Testbild wird angezeigt.` | WARNING | Einzelner Frame ging verloren | Bei Häufung: Kamerakabel und Stromversorgung prüfen |
| `Foto-Aufnahme in voller Auflösung fehlgeschlagen (…) – Vorschaubild wird verwendet.` | WARNING | Der Moduswechsel zur Foto-Auflösung schlug fehl; das Foto wird in geringerer Qualität gespeichert | Bei Häufung Kamera neu starten (App-Neustart) |
| Bildschirm: `Kamera nicht verfügbar – Testbild wird verwendet.` | warning | Aufnahme-Screen wurde ohne funktionierende Kamera betreten | Siehe „Kamera-Initialisierung fehlgeschlagen" |

---

## 5. GPIO / Taster / LEDs (`src/gpio_handler.py`)

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `gpiozero nicht verfügbar – Tastatur-Fallback aktiv (LEERTASTE / F1)` | INFO | Normal auf dem Mac. Auf dem Pi: Paket fehlt | Pi: `sudo apt install -y python3-gpiozero` |
| `GPIO-Initialisierung fehlgeschlagen (…) – Tastatur-Fallback aktiv …` | WARNING | Pins konnten nicht reserviert werden (falsche Pin-Nummer, Pin belegt, fehlende Rechte) | Pin-Belegung in `config/settings.json` (Abschnitt `gpio`) mit der realen Verkabelung (WIRING.md) abgleichen |
| `GPIO-Callback für '…' fehlgeschlagen` (mit Stacktrace) | ERROR | Ein Tastendruck hat intern eine Ausnahme ausgelöst | Stacktrace im Log lesen – das ist ein Programmfehler, kein Verkabelungsproblem |

---

## 6. Audio (`src/audio.py`)

Backend-Reihenfolge für Sound-Effekte: **libVLC → aplay (nur WAV, Linux) →
QSoundEffect → Stille**. Szenen-Musik läuft ausschließlich über libVLC.

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `python-vlc/libVLC nicht verfügbar (…) – Szenen-Audio und MP3-Töne sind deaktiviert!` | WARNING | VLC fehlt → keine Szenen-Musik, keine MP3-Sounds | Pi: `sudo apt install -y vlc python3-vlc` (Details: FIX_AUDIO.md). Zusätzlich erscheint beim Start eine Bildschirm-Meldung |
| `libVLC-Instanz konnte nicht erstellt werden (…)` | ERROR | VLC ist installiert, startet aber nicht (defekte Plugins, fehlende Libs) | `vlc --version` im Terminal testen; VLC neu installieren |
| `pactl nicht verfügbar (…) – Audio-Routing zur Kopfhörerbuchse übersprungen.` | WARNING | PipeWire/PulseAudio-Werkzeug fehlt; Ton geht ggf. an HDMI statt Klinke | Nur relevant, wenn der Ton am falschen Ausgang landet. Abhilfe: `force_headphone_audio` in settings.json bzw. Ausgang manuell per `raspi-config` setzen |
| `Keine Kopfhörer-Audiosenke gefunden – Audio läuft über die Standard-Ausgabe.` | INFO | Kein Klinken-Ausgang im System gefunden (z. B. am Mac normal) | Auf dem Pi: prüfen, ob die Audioausgabe in `raspi-config` aktiviert ist |
| `Audio-Datei nicht gefunden: … – Musik entfällt.` | WARNING | Eine Szene verweist auf eine gelöschte/verschobene Datei | Pfad im Admin-Szeneneditor neu auswählen |
| `Sound-Datei nicht gefunden: … – Effekt entfällt.` | WARNING | System-Sound (Auslöser/Countdown) verweist auf fehlende Datei | Pfad im Admin-Bereich (System-Sounds) neu auswählen |
| `VLC verweigert die Wiedergabe von: …` | WARNING | Datei vorhanden, aber Format/Codec nicht abspielbar | Datei in WAV oder MP3 konvertieren und neu zuweisen |
| `aplay fehlgeschlagen (rc=…): …` | WARNING | WAV-Fallback schlug fehl. Enthält die Ausgabe „busy", hält der Sound-Server die Karte belegt – aplay wird dann automatisch deaktiviert | Keine Aktion nötig, VLC/Qt übernehmen. Falls gar kein Ton: FIX_AUDIO.md |
| `aplay nicht verfügbar (…) – anderes Audio-Backend wird verwendet.` | WARNING | `aplay` nicht installiert (alsa-utils) | Optional: `sudo apt install -y alsa-utils` |
| `Kein Audio-Backend konnte den Sound-Effekt abspielen: …` | WARNING | Alle drei Backends schlugen fehl → dieser Effekt bleibt stumm | VLC installieren (siehe oben); Dateiformat prüfen (WAV empfohlen) |
| `Audio-/Video-Dauer von … nicht lesbar` | WARNING | Der Admin-Szeneneditor konnte die Mediendauer nicht ermitteln; die Dauer muss ggf. manuell gesetzt werden | Datei auf Korrektheit prüfen; `mutagen` installieren (`pip3 install mutagen`) |
| Bildschirm: `Audio-Backend (python-vlc) fehlt – Szenen-Audio bleibt stumm.` | warning | Start-Hinweis, identisch zu „python-vlc/libVLC nicht verfügbar" | Siehe FIX_AUDIO.md |

---

## 7. Video-Szenen (`src/ui/video_widget.py`)

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `Video … kann nicht abgespielt werden – VLC-Backend nicht verfügbar` | WARNING | Wie Audio: libVLC fehlt. Die Begrüßungsszene zeigt stattdessen Bild + Audio | `sudo apt install -y vlc python3-vlc` |
| `libVLC-Video-Instanz konnte nicht erstellt werden (…)` | ERROR | VLC startet nicht | VLC-Installation prüfen |
| `Video-Wiedergabe von … konnte nicht vorbereitet werden: …` | WARNING | Datei defekt oder Format nicht unterstützt | Video als MP4 (H.264) neu exportieren |
| `Video-Wiedergabe fehlgeschlagen: … – Szene fällt auf Bild+Audio zurück.` | WARNING | Wiedergabe brach beim Start ab; der automatische Fallback zeigt das Szenenbild | Bei Häufung: Videoformat prüfen (H.264 empfohlen, Pi-tauglich) |

---

## 8. USB-Speicher (`src/storage.py`)

Diese Fehler werden als `IOError` mit fertigem Hilfetext ausgelöst und vom
aufrufenden Screen als rote Bildschirm-Meldung angezeigt (und damit auch
geloggt).

| Meldung | Bedeutung | Behebung |
|---|---|---|
| `USB-Stick nicht gefunden unter '/media/usb'. …` | Mountpunkt existiert nicht | USB-Stick einstecken; Mount prüfen: `lsblk`, `df -h`; ggf. Pfad `usb_mount` in den Einstellungen anpassen |
| `Ordner '…' konnte nicht erstellt werden: …` | Stick ist schreibgeschützt, voll oder das Dateisystem ist defekt | Schreibschutz-Schalter prüfen; Stick neu formatieren (FAT32/exFAT); Dateisystem-Check |
| `Foto konnte nicht gespeichert werden (…): … Freier Speicher: … MB` | Schreiben schlug fehl – die Meldung nennt den freien Speicher gleich mit | Bei < 100 MB: Stick leeren oder größeren verwenden; sonst Schreibrechte prüfen |
| `Collage konnte nicht gespeichert werden (…)` | Wie oben, beim Collage-Speichern | Wie oben |
| Bildschirm: `USB-Stick nicht gefunden` (beim Sitzungsstart) | Frühwarnung: Eine Foto-Sitzung startet ohne Stick | Stick einstecken – Fotos der laufenden Sitzung landen sonst nur in `/tmp` |
| Log: `Foto ersatzweise zwischengespeichert: /tmp/… – wird beim Entfernen des Temp-Verzeichnisses gelöscht!` | WARNING: Notfall-Fallback hat gegriffen; die Sitzung läuft weiter, das Foto liegt aber **nicht** auf dem Stick | Fotos zeitnah aus `/tmp` retten (gehen bei Neustart verloren), Stick-Problem beheben |

---

## 9. Collage (`src/collage.py`, `src/ui/screen_collage.py`)

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `Foto … konnte nicht in die Collage eingefügt werden: … – Feld bleibt leer.` | WARNING | Ein Einzelfoto ist defekt/nicht lesbar; die Collage wird trotzdem gebaut | Einzelfall ignorierbar; bei Häufung USB-Stick prüfen |
| `Cover … hat …x… Pixel (erwartet 1800x1200) – wird automatisch skaliert.` | WARNING | Cover-PNG hat die falsche Größe; Skalierung kann unscharf wirken | Cover in exakt 1800×1200 px exportieren |
| `Cover-Datei nicht gefunden: … – Collage ohne Cover.` | WARNING | In den Einstellungen ist ein Cover hinterlegt, die Datei fehlt aber | Pfad im Admin-Bereich (Collage-Cover) korrigieren |
| `Cover-Overlay … konnte nicht angewendet werden: …` | WARNING | Cover-Datei defekt oder kein PNG mit Alphakanal | Cover als PNG (RGBA) neu exportieren |
| `Collage-Erstellung fehlgeschlagen` (mit Stacktrace) | ERROR | Unerwarteter Fehler im Hintergrund-Thread; zusätzlich erscheint eine rote Bildschirm-Meldung | Stacktrace im Log lesen. Die Sitzung läuft weiter, der Druck-Screen meldet dann „Keine Collage-Datei vorhanden" |
| `Foto … kann nicht für die Diashow geladen werden – wird übersprungen.` | WARNING | Nur die Anzeige ist betroffen, nicht die Collage selbst | Wie „Foto konnte nicht eingefügt werden" |

---

## 10. Drucker (`src/printer.py`) – Canon SELPHY CP1500 über CUPS

Ausführliche Einrichtung: **PRINTER_SETUP.md** · Reparatur einer hängenden
Queue: **PRINTER_FIX.md**

> **Bekannt-gute Konfiguration:** Die App sendet Druckaufträge **ohne
> Job-Optionen** (`printFile(…, {})`) – app-seitige Optionen (`media`,
> `fit-to-page`, `print-scaling` …) verursachten beim CP1500 hängende bzw.
> fehlerhafte Drucke. Randlosdruck ist als Queue-Standard hinterlegt
> (`sudo lpadmin -p SELPHY -o StpBorderless=True`). Details:
> PRINTER_SETUP.md, Abschnitt „Druckoptionen der Fotobox".

### Verbindung & Einrichtung

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `pycups nicht verfügbar – Drucken nur als Demo-Ausgabe möglich.` | INFO | Python-CUPS-Anbindung fehlt (am Mac normal) | Pi: `sudo apt install -y python3-cups` |
| `CUPS-Verbindung fehlgeschlagen: …` | WARNING | Der CUPS-Dienst läuft nicht oder ist nicht erreichbar | `systemctl status cups`, ggf. `sudo systemctl restart cups` |
| `CUPS-Abfrage fehlgeschlagen: …` | WARNING | Verbindung bestand, brach aber ab; wird beim nächsten Druck neu aufgebaut | Bei Häufung CUPS neu starten |
| `Drucker '…' nicht in CUPS gefunden. Verfügbare Drucker: …` | WARNING | Es gibt keine passende CUPS-Warteschlange | Queue einmalig anlegen (PRINTER_SETUP.md, Abschnitt 4) oder `printer_name` in den Einstellungen an einen der angezeigten Namen anpassen |
| `Drucker '…' nicht exakt gefunden – verwende stattdessen die CUPS-Warteschlange '…'.` | INFO | Unscharfe Namensauflösung hat eine ähnliche Queue gewählt (z. B. `Canon_SELPHY_CP1500`) | Keine Aktion nötig; optional `printer_name` exakt setzen |
| `Warteschlange '…' nutzt das Standard-USB-Backend (usb://…).` | WARNING | **Bekannte Fehlkonfiguration:** Mit `usb://` bleiben SELPHY-Jobs bei „Waiting for printer to become available" hängen. Die App versucht vor dem nächsten Druck einmalig eine automatische Reparatur | Falls die Auto-Reparatur scheitert: PRINTER_FIX.md (Queue auf `gutenprint53+usb://` umstellen) |

### Automatische Queue-Reparatur (Selbstheilung)

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `Warteschlange '…' automatisch repariert: Geräte-URI von '…' auf '…' umgestellt.` | WARNING | Erfolg – die Queue zeigt jetzt aufs richtige Backend | – |
| `Gerätesuche für die automatische Queue-Reparatur fehlgeschlagen (…)` | WARNING | CUPS konnte nicht nach Geräten suchen | Manuell reparieren: PRINTER_FIX.md |
| `Kein gutenprint53+usb-Gerät für die automatische Reparatur gefunden …` | WARNING | Drucker ist aus oder nicht angesteckt | Drucker einschalten, USB-Kabel prüfen, erneut drucken |
| `Queue '…' konnte nicht automatisch umgestellt werden (…)` | WARNING | Fehlende Rechte (Benutzer nicht in Gruppe `lpadmin`) | Angezeigtes `lpadmin`-Kommando manuell mit `sudo` ausführen |
| `Gestoppte Warteschlange '…' wieder aktiviert.` | WARNING | CUPS hatte die Queue angehalten (Folge eines früheren Fehlers); die App hat sie reaktiviert | – |
| `Hängenden Druckauftrag … verworfen (Status=…, Alter=… s).` | WARNING | Ein alter Auftrag (> 180 s) blockierte die Queue und wurde gelöscht | – |

### Druckvorgang

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| `Demo-Modus aktiv: Druckvorgang übersprungen …` (+ Banner auf der Konsole) | INFO | `demo_mode` ist eingeschaltet – es wird absichtlich nicht gedruckt | Demo-Modus im Admin-Bereich ausschalten |
| `Druckfehler: Datei nicht gefunden: …` | ERROR | Die Collage-Datei ist verschwunden (meist: USB-Stick wurde gezogen) | USB-Stick prüfen |
| `Drucker '…' nicht erreichbar: CUPS-Verbindung nicht verfügbar.` | ERROR | Kein CUPS beim Druckversuch | `sudo systemctl restart cups` |
| `Druck abgebrochen: Keine CUPS-Warteschlange für '…' eingerichtet.` | ERROR | Wie „nicht in CUPS gefunden", aber beim konkreten Druckversuch | PRINTER_SETUP.md |
| `Sende Druckauftrag: Warteschlange=…, Geräte-URI=…, …` | INFO | Normale Diagnosezeile vor jedem Druck – nützlich, um URI/Status im Fehlerfall abzulesen | – |
| `Druckfehler (CUPS IPP …): …` | ERROR | CUPS hat den Auftrag abgelehnt | Drucker eingeschaltet? USB-Kabel? Papier/Farbband? `lpstat -p <queue>` |
| `Druckfehler (unbekannt): …` (mit Stacktrace) | ERROR | Unerwarteter Fehler beim Übergeben an CUPS | `journalctl -u cups --since '5 minutes ago'` |
| `CUPS hat den Druckauftrag … ohne Job-ID abgelehnt` | ERROR | Sehr selten; CUPS nahm den Job nicht an | CUPS-Log prüfen, Dienst neu starten |
| `Druckauftrag angenommen: Job-ID=…` → `Druckauftrag … wird verarbeitet` | INFO | Normaler Erfolgsweg | – |
| `Druckauftrag … von CUPS verworfen: Status=aborted/canceled/stopped …` | ERROR | CUPS nahm den Job an, verwarf ihn aber (Treiber-/Backend-Problem). Die Druckermeldung in der Logzeile nennt den Grund | PRINTER_SETUP.md (Fehlersuche); häufigste Ursache: falsches Backend → PRINTER_FIX.md |
| `Druckauftrag … nach 5 s noch nicht gestartet (Status=pending, Druckermeldung='…')` | WARNING | Job hängt in der Queue. Lautet die Druckermeldung „Waiting for printer to become available", kann das USB-Backend den Drucker nicht öffnen | USB-Kabel ab-/anstecken bzw. Drucker aus-/einschalten (PRINTER_FIX.md). Druckt gerade ein vorheriger Job (~45–60 s pro SELPHY-Druck), ist die Meldung harmlos |
| `Job-Status von Auftrag … nicht abfragbar (…)` | WARNING | Statusabfrage schlug fehl, der Job wurde aber angenommen und gilt als unterwegs | Nur bei Häufung relevant: CUPS prüfen |
| Bildschirm: `Druck fehlgeschlagen – Details in fotobox.log.` | error | Sammel-Meldung des Druck-Screens; die genaue Ursache steht als ERROR-Zeile im Log (siehe oben) | Log lesen, passende Zeile in dieser Tabelle nachschlagen |
| Bildschirm: `Druckfehler: Keine Collage-Datei vorhanden.` | error | Es kam gar keine Collage am Druck-Screen an (Collage-Erstellung oder Speichern schlug vorher fehl) | Vorherige ERROR-Zeilen im Log prüfen (Abschnitte 8 und 9) |

---

## 11. Bedienung / Sitzungsablauf (`src/app.py`)

| Meldung | Level | Bedeutung | Behebung |
|---|---|---|---|
| Bildschirm: `Keine Pfade konfiguriert – Admin-Taste drücken` | warning | Start gedrückt, aber es ist kein Ablauf-Pfad angelegt | Im Admin-Bereich (F1) mindestens einen Pfad anlegen |
| Bildschirm: `Pfad '…' hat keine Begrüßungsszene/Collage-Szene/Druck-Szene.` | error | Der ausgewählte Standard-Pfad verweist nicht auf alle nötigen Szenen | Pfad im Admin-Bereich vervollständigen |
| Bildschirm: `Pfad '…' hat keine Segmente.` / `Segment … hat keine Bilddatei/GIF-Datei/gültige Fotoanzahl` | error | Ein individueller Pfad ist unvollständig konfiguriert (z. B. von Hand editierte `paths.json`) | Pfad im Admin-Bereich öffnen, Segment vervollständigen und neu speichern |
| Bildschirm: `Druckfehler: Keine Collage vorhanden – das Druck-Segment benötigt ein vorheriges Aufnahme-Segment …` | error | Ein Druck-Segment lief, ohne dass in diesem Durchlauf eine Collage entstand und ohne gespeicherte Collage auf dem USB-Stick | Im Pfad ein Aufnahme-Segment vor dem Druck-Segment einplanen |
| `GIF-Datei fehlt: … – Segment zeigt einen schwarzen Bildschirm.` | WARNING | Ein GIF-Segment verweist auf eine fehlende/defekte Datei | Pfad im Admin-Bereich korrigieren |
| `Unbekannter Screen angefordert: '…' – Wechsel ignoriert` | WARNING | Interner Programmfehler (sollte nie auftreten) | Bitte als Bug melden/notieren |
| `Screen-Wechsel: …` | INFO | Normaler Ablauf – zeigt im Log nach, wo eine Sitzung stand | – |
| `Bild-Datei fehlt: … – Standardhintergrund wird verwendet.` | WARNING | Szenen-/Hintergrundbild verweist auf eine fehlende Datei | Pfad im Admin-Bereich korrigieren |
| `Audio-Datei fehlt: … – läuft ohne Ton.` | WARNING | Wie oben, für die Tonspur einer Szene oder eines Segments | Pfad im Admin-Bereich (Szenen-Editor bzw. Pfad-Segment) korrigieren |
| `Admin-Design '…' nicht lesbar – eingebautes Standard-Design wird verwendet.` | WARNING | Die QSS-Datei aus `assets/themes/` fehlt oder ist nicht lesbar; der Admin-Bereich bleibt voll bedienbar | Datei wiederherstellen oder Einstellung `admin_theme` korrigieren (ADMIN_DESIGN.md) |
| `Fehler beim Verlassen des Screens '…' während des Beendens` | ERROR | Aufräumfehler beim App-Ende – kosmetisch, da die App ohnehin beendet wird | Nur bei reproduzierbarem Auftreten relevant (Stacktrace im Log) |

---

## 12. Schnell-Checkliste bei Problemen vor Ort

1. **Log ansehen:** letzte Zeilen von `fotobox.log` (oder Konsole) lesen –
   jede rote Bildschirm-Meldung steht dort mit `[Meldung]` und davor meist
   die eigentliche Ursache als ERROR/WARNING.
2. **Kein Ton?** → Abschnitt 6, meist fehlt `vlc`/`python3-vlc` (FIX_AUDIO.md).
3. **Kein Druck?** → Abschnitt 10; in 9 von 10 Fällen: Queue fehlt
   (PRINTER_SETUP.md) oder falsches USB-Backend (PRINTER_FIX.md).
4. **Schwarzes Testbild statt Kamera?** → Abschnitt 4, `rpicam-hello` testen.
5. **Fotos weg?** → Abschnitt 8, `/tmp` prüfen, bevor der Pi neu startet.
6. **Mehr Details nötig?** → App mit `python src/main.py --debug` starten.

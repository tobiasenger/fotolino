# FIX_AUDIO – Kein Ton in der Fotobox-App

Symptom: WAV-Dateien spielen auf dem Pi im Terminal normal ab (`aplay datei.wav`),
aber **innerhalb der App** kommt kein Ton aus dem Klinkenanschluss.

Dass das Terminal funktioniert, schließt Lautsprecher/Kabel/Dateien aus. Es bleiben
zwei Kategorien: (A) die App versucht gar nicht erst abzuspielen (Konfiguration /
fehlendes Backend) und (B) die App spielt ab, aber die Ausgabe landet im Nichts
(Session/Routing). Beides ist unten abgedeckt.

---

## 1. Was im Code bereits behoben wurde (dieses Refactoring)

Diese Fehler konnten Ton komplett verhindern und sind jetzt gefixt:

1. **Fehlendes VLC-Backend war unsichtbar.** Szenen-Audio (Begrüßung/Collage/Druck)
   läuft komplett über `python-vlc`. Fehlte das Modul, wurde Musik stillschweigend
   deaktiviert (nur eine INFO-Zeile im Log). Jetzt: deutliche WARNING im Log
   **und eine Warnmeldung auf dem Bildschirm beim Start** („Audio-Backend
   (python-vlc) fehlt…“). Außerdem wurde `import vlc` nur gegen `ImportError`
   abgesichert – wenn das Python-Paket installiert ist, aber die native libVLC
   fehlt, wirft es `OSError` und die App stürzte beim Start ab. Auch gefixt.
2. **Auslöser-Ton zeigte auf eine nicht existierende MP3.** Die Standard-Config
   hatte `"shutter_click": "assets/sounds/click.mp3"` – die Datei existiert nicht,
   und selbst wenn: Nicht-WAV-Systemtöne wurden bisher **verweigert** statt
   abgespielt. Jetzt: WAV läuft über `aplay`, alles andere (MP3/OGG) über VLC.
3. **`aplay`-Fehler wurden verschluckt** (`stderr=DEVNULL`). Schlug `aplay` fehl
   (z. B. „Device or resource busy“), gab es keinerlei Hinweis. Jetzt wird der
   Rückgabewert geprüft und stderr im Log ausgegeben.
4. **`deploy.sh` löschte Pi-seitige Dateien.** `rsync --delete` spiegelte das
   komplette Projekt inklusive `config/` – jeder Deploy überschrieb die auf dem
   Pi gemachte Konfiguration und löschte z. B. nur auf dem Pi abgelegte
   WAV-Dateien. `config/` ist jetzt vom Sync ausgenommen.
   **Achtung:** `assets/` wird weiterhin gespiegelt – Sounddateien immer im
   Projekt auf dem Mac ablegen, nie nur auf dem Pi.
5. **`deploy.sh --restart` startete die App ohne Session-Umgebung.** Ohne
   `XDG_RUNTIME_DIR` erreicht die App PipeWire/PulseAudio nicht → alles stumm,
   obwohl ein Terminal auf dem Desktop funktioniert. Das Skript exportiert jetzt
   `DISPLAY` und `XDG_RUNTIME_DIR`.
6. **Countdown-Beep** war in den Einstellungen vorgesehen, wurde aber nie
   abgespielt – jetzt implementiert.
7. Jeder Abspielversuch wird jetzt geloggt (`fotobox.log` im Projektordner,
   rotierend). Damit ist künftig sichtbar, *ob* die App überhaupt versucht
   abzuspielen und mit welchem Ergebnis.

---

## 2. Diagnose auf dem Pi – in dieser Reihenfolge

### Schritt 1: Ist python-vlc installiert? (häufigste Ursache)
```bash
python3 -c "import vlc; print(vlc.__version__)"
```
Fehler? Dann:
```bash
sudo apt install -y vlc python3-vlc
```
Ohne dieses Paket gibt es **kein** Szenen-Audio – die App zeigt das nach dem
Refactoring beim Start als Warnung an.

### Schritt 2: Log lesen, während man einen Durchlauf startet
```bash
tail -f ~/fotobox/fotobox.log
```
Dann Startknopf drücken. Erwartete Zeilen:
- `Music playing: <datei>` → App spielt ab; wenn trotzdem stumm → Schritt 4–6 (Routing).
- `Audio file not found: …` / `Scene audio file missing: …` → Pfad in der Szene
  zeigt auf eine nicht vorhandene Datei (Schritt 3).
- `aplay failed (rc=1): …Device or resource busy` → ALSA-Gerät exklusiv belegt (Schritt 5).
- Gar keine Audio-Zeile → der Szene ist schlicht keine Audiodatei zugeordnet
  (Admin → Szenen prüfen).

### Schritt 3: Zeigen Szenen/Einstellungen auf existierende Dateien?
```bash
cat ~/fotobox/config/scenes.json | grep -E '"audio"|"video"'
cat ~/fotobox/config/settings.json | grep -A3 system_sounds
ls ~/fotobox/assets/sounds/
```
Wichtig: Das bisherige `deploy.sh` hat Pi-seitige Dateien/Configs beim Deploy
gelöscht bzw. überschrieben (siehe oben Punkt 4) – ggf. Szenen neu anlegen.

### Schritt 4: Läuft die App in der richtigen Session?
Die App muss in der Desktop-Session laufen (Autostart oder Terminal auf dem
Desktop). Bei Start über SSH prüfen:
```bash
echo $XDG_RUNTIME_DIR    # muss /run/user/1000 (o. ä.) sein
```
Falls leer:
```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DISPLAY=:0
```
(Das neue `deploy.sh --restart` macht das automatisch.)

### Schritt 5: Mischbare Audio-Ausgabe (Device busy)?
Wenn PipeWire die ALSA-Geräte nicht verwaltet, blockieren sich VLC und `aplay`
gegenseitig (exklusiver Hardware-Zugriff). Test: App laufen lassen (Szene mit
Musik) und parallel im Desktop-Terminal:
```bash
aplay /usr/share/sounds/alsa/Front_Center.wav
```
Kommt „Device or resource busy“ → PipeWire-ALSA-Brücke installieren:
```bash
sudo apt install -y pipewire-alsa
systemctl --user restart pipewire wireplumber
```

### Schritt 6: Geht die Ausgabe auf die richtige Senke (Klinke statt HDMI)?
```bash
wpctl status            # PipeWire-Übersicht: Default-Sink mit * markiert
pactl list sinks short  # Alternative
```
Steht der Default auf HDMI:
```bash
pactl set-default-sink <name-der-headphones-senke>
```
oder dauerhaft: `sudo raspi-config` → System Options → Audio → **3.5mm jack**.
Die App versucht das beim Start selbst (Einstellung „Audio auf Klinke zwingen“,
`force_headphone_audio` in settings.json – abschaltbar, falls HDMI-Ton gewünscht ist).

### Schritt 7: Lautstärke/Mute prüfen
```bash
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0
alsamixer    # F6 → „bcm2835 Headphones“ → Regler hoch, „MM“ (mute) mit M aufheben
```

---

## 3. Wenn alles oben nichts gebracht hat

- VLC direkt auf dem Pi testen (gleiche Engine wie die App):
  ```bash
  cvlc --play-and-exit assets/sounds/sound_1.mp3
  ```
  Spielt `cvlc` und die App nicht → Log vergleichen (Schritt 2).
- App testweise im Vordergrund auf dem Desktop starten, um alle Meldungen zu sehen:
  ```bash
  cd ~/fotobox && python3 src/main.py --dev
  ```
- ALSA-Geräteliste ansehen, falls die Klinke gar nicht auftaucht:
  ```bash
  aplay -l
  ```
  Fehlt „bcm2835 Headphones“: in `/boot/firmware/config.txt` muss
  `dtparam=audio=on` stehen, danach neu starten.

# Drucker-Reparatur: Aufträge hängen, Druck erst nach Aus-/Einschalten

## Symptome

- Während des Fotobox-Durchlaufs wird **nichts gedruckt**; der Auftrag bleibt
  in der Warteschlange (`lpstat -t` zeigt „Waiting for printer to become
  available").
- Schaltet man den Drucker **aus und wieder ein**, druckt er den wartenden
  Auftrag – der Ausdruck selbst ist einwandfrei.
- Nach dem Druck bleibt der Drucker auf dem Bildschirm **„Daten werden
  empfangen"** hängen und nimmt keine weiteren Aufträge an.

## Ursache

Die CUPS-Warteschlange wurde mit dem **Standard-USB-Backend** angelegt
(Geräte-URI beginnt mit `usb://Canon/SELPHY...`). Dieses Backend behandelt
den SELPHY wie einen gewöhnlichen Drucker und schiebt nur Rohdaten durch.
Der SELPHY CP1500 spricht aber ein eigenes Dye-Sub-Protokoll mit
Status-Rückmeldungen: Ohne dieses Protokoll erfährt der Drucker nie, dass
der Auftrag zu Ende ist (→ hängt auf „Daten werden empfangen"), und CUPS
kann das Gerät danach nicht erneut öffnen (→ „Waiting for printer to become
available"). Das Aus-/Einschalten setzt den Drucker nur zurück, behebt aber
nichts.

Gutenprint 5.3.5 bringt für genau diese Drucker ein **eigenes USB-Backend**
mit: `gutenprint53+usb`. Es wurde bei der Quellinstallation
(siehe PRINTER_SETUP.md, Abschnitt 3) bereits mitinstalliert – die
Warteschlange muss nur darauf umgestellt werden.

## Was die App selbst repariert

`src/printer.py` heilt die Warteschlange vor jedem Druck so weit wie
möglich selbst:

1. **Backend-Umstellung (einmalig pro Programmlauf):** Erkennt die App
   einen SELPHY an einer `usb://`-URI, sucht sie per CUPS nach dem
   passenden `gutenprint53+usb://`-Gerät (Abgleich über die Seriennummer)
   und stellt die Warteschlange automatisch um – das Gegenstück zu
   `sudo lpadmin -p SELPHY -v "gutenprint53+usb://…"`.
2. **Gestoppte Warteschlange reaktivieren:** Hat CUPS die Queue nach
   Backend-Fehlern angehalten, wird sie wieder aktiviert
   (`cupsenable`/`cupsaccept`-Äquivalent).
3. **Hängende Aufträge ausräumen:** Nicht abgeschlossene Aufträge, die
   älter als 3 Minuten oder angehalten/gestoppt sind, werden verworfen,
   damit der neue Druck nicht dahinter feststeckt. Frische Aufträge
   bleiben unangetastet (der vorige Druck darf noch laufen).

**Voraussetzung für Punkt 1 und 2:** Der Benutzer, unter dem die Fotobox
läuft, muss CUPS verwalten dürfen, d. h. in der Gruppe `lpadmin` sein
(siehe PRINTER_SETUP.md, Abschnitt 2):

```bash
sudo usermod -aG lpadmin $USER   # danach ab- und wieder anmelden bzw. Pi neu starten
```

Fehlt das Recht oder schlägt die Reparatur fehl, schreibt die App eine
Warnung mit dem exakten manuellen Befehl ins Log – dann gilt die folgende
Anleitung. Ein bereits auf „Daten werden empfangen" hängender Drucker
muss in jedem Fall einmal **aus- und eingeschaltet** werden; das kann
keine Software ersetzen.

## Manuelle Reparatur (einmalig, ca. 2 Minuten)

### 1. Prüfen, dass das Gutenprint-Backend installiert ist

```bash
ls /usr/lib/cups/backend/ | grep gutenprint
# Soll zeigen: gutenprint53+usb
```

Fehlt die Datei: im Quellverzeichnis `gutenprint-5.3.5` erneut
`sudo make install && sudo systemctl restart cups` ausführen.

### 2. Drucker zurücksetzen und neue Geräte-URI ermitteln

Drucker **aus- und wieder einschalten** (damit er den „Daten
empfangen"-Zustand verlässt), USB-Kabel kurz ab- und wieder anstecken, dann:

```bash
lpinfo -v | grep -i selphy
```

Es erscheinen typischerweise **zwei** Zeilen, z. B.:

```text
direct usb://Canon/SELPHY%20CP1500?serial=CZ23011023417958
direct gutenprint53+usb://canon-selphy-cp1500/CZ23011023417958
```

Benötigt wird die Zeile, die mit **`gutenprint53+usb://`** beginnt –
**nicht** die `usb://`-Zeile. Das Wort `direct` am Anfang ist wie immer
**nicht Teil der URI**.

### 3. Warteschlange auf das richtige Backend umstellen

Die vorhandene Warteschlange bleibt bestehen (Treiber/PPD unverändert),
nur die Geräte-URI wird getauscht – URI aus Schritt 2 einsetzen:

```bash
sudo lpadmin -p SELPHY -v "gutenprint53+usb://canon-selphy-cp1500/CZ23011023417958"
```

### 4. Hängende Aufträge löschen und Warteschlange reaktivieren

CUPS pausiert eine Warteschlange manchmal nach wiederholten
Backend-Fehlern – beides in Ordnung bringen:

```bash
cancel -a SELPHY
sudo cupsenable SELPHY
sudo cupsaccept SELPHY
```

### 5. Testen

```bash
lpstat -t          # Warteschlange "im Leerlauf", URI beginnt mit gutenprint53+usb://
lp -d SELPHY -o PageSize=Postcard -o fit-to-page /usr/share/cups/data/testprint
```

Der Druck muss jetzt **ohne Aus-/Einschalten** starten, und der Drucker
muss nach dem Druck wieder auf den Startbildschirm zurückkehren. Danach
einen kompletten Fotobox-Durchlauf testen.

## Falls die `gutenprint53+usb://`-Zeile nicht erscheint

| Prüfung | Befehl / Maßnahme |
|---|---|
| Backend-Datei vorhanden? | `ls /usr/lib/cups/backend/ \| grep gutenprint` → sonst Schritt 1 |
| Drucker am USB sichtbar? | `lsusb \| grep -i canon`; Kabel/Netzteil prüfen, replug |
| `ipp-usb` blockiert das Gerät? | `dpkg -l ipp-usb` → falls installiert: `sudo apt remove ipp-usb` |
| Drucker hängt noch auf „Daten empfangen"? | Drucker aus-/einschalten, dann `lpinfo -v` erneut |
| Unterspannung am Pi? | `vcgencmd get_throttled` → muss `0x0` sein (sonst Netzteil prüfen) |
| CUPS-Logs | `journalctl -u cups --since "10 minutes ago"` |

## Hinweise für den Dauerbetrieb

- Das `gutenprint53+usb`-Backend hält den Drucker offen, bis ein Auftrag
  vollständig übertragen ist. Folgeaufträge warten so lange als „pending" –
  das ist normal und kein Fehler; die Fotobox wertet das nicht als
  Fehlschlag.
- Den Drucker am Netzteil betreiben, nicht am Akku: Im Akkubetrieb geht der
  SELPHY früher in den Standby und meldet sich am USB ab.

## Quellen

- [Linux-Mint-Tutorial zu Gutenprint-Dye-Sub-Druckern: Standard-USB-Backend „will not work properly with these printers"](https://forums.linuxmint.com/viewtopic.php?t=391775)
- [CUPS hängt bei „sending data to printer" mit SELPHY CP910](https://github.com/camswords/raspberry-pi-instagram-printer/issues/1)
- [Gutenprint-Forum: Printer open failure mit gutenprint53+usb](https://sourceforge.net/p/gimp-print/discussion/4359/thread/7fb1c74608/)
- [Gutenprint-Bug #705: SELPHY druckt im Akkubetrieb nicht über USB](https://sourceforge.net/p/gimp-print/bugs/705/)

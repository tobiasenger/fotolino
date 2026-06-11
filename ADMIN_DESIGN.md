# Admin-Design: Austauschbare Optik (wie CSS)

Das komplette Aussehen des Adminbereichs steckt in **einer einzigen
Design-Datei**:

```
assets/themes/admin_dark.qss
```

Das ist ein Qt-Stylesheet (QSS) – Qts eingebaute CSS-Variante. Der Python-Code
setzt nur noch Struktur und „Klassen" (Objektnamen / `kind`-Eigenschaften);
Farben, Rundungen, Abstände und Schriftgrößen kommen ausschließlich aus dieser
Datei.

## Design tauschen

1. Neue `.qss`-Datei nach `assets/themes/` legen (z. B. `admin_light.qss`).
2. In `config/settings.json` den Schlüssel setzen: `"admin_theme": "admin_light.qss"`
   – oder einfach den Inhalt von `admin_dark.qss` ersetzen (Standard, kein
   Settings-Eintrag nötig).
3. App neu starten (das Theme wird beim Start geladen).

Fehlt die Datei oder ist sie defekt, greift automatisch ein eingebautes
Minimal-Design (`src/ui/theme.py` → `_ADMIN_FALLBACK_QSS`) – der Adminbereich
bleibt immer bedienbar.

## Selektor-Vertrag

Eine Design-Datei darf **ausschließlich** diese Selektoren verwenden (der
Python-Code garantiert sie):

| Selektor | Element |
|---|---|
| `#AdminRoot` | Gesamter Adminbereich (Hintergrund) |
| `#AdminSidebar` | Linke Hauptnavigation |
| `QLabel[kind="appname"]` | App-Name „Fotobox" in der Sidebar |
| `QLabel[kind="subtitle"]` | Untertitel „Adminbereich" |
| `QLabel[kind="title"]` | Seitenüberschrift („Szenen", „Pfade") |
| `QLabel[kind="section"]` | Abschnitts-Überschriften in Formularen |
| `QLabel[kind="hint"]` | Gedämpfter Erklärtext |
| `QLabel[kind="warn"]` | Warnhinweise (z. B. falsches Dateiformat) |
| `QLabel` (ohne kind) | Normale Formular-Beschriftungen |
| `QFrame[kind="separator"]` | 1 px hohe Trennlinie zwischen Blöcken |
| `QPushButton[kind="tab"]` | Sidebar-Tabs, abhakbar (`:checked` = aktiv) |
| `QPushButton[kind="pill"]` | Szenentyp-Umschalter, abhakbar |
| `QPushButton[kind="primary"]` | Hauptaktionen (Speichern, + Neu) |
| `QPushButton[kind="danger"]` | Löschen |
| `QPushButton[kind="close"]` | „✕ Schließen" unten in der Sidebar |
| `QPushButton[kind="tool"]` | Kleine Werkzeug-Buttons („…" Dateiauswahl) |
| `QPushButton` (ohne kind) | Sekundäre Aktionen (Export, Kamera testen …) |
| `QLineEdit`, `QComboBox` | Eingabefelder (inkl. `:focus`, `:disabled`) |
| `QComboBox QAbstractItemView` | Aufgeklappte Dropdown-Liste |
| `QListWidget` (+ `::item`, `:selected`, `:hover`) | Szenen-/Pfad-Listen |
| `QScrollArea`, `QScrollBar` | Scrollbereiche und -balken |
| `QMessageBox`, `QToolTip` | Dialoge und Tooltips |

**Nicht erlaubt:** neue Objektnamen erfinden, Layout-Geometrie erzwingen
(`min-width` auf Inhaltsflächen o. Ä.), externe Ressourcen/Bilder einbinden.

---

## Prompt für Claude Design

Den folgenden Block komplett kopieren und an Claude Design übergeben. Als
Referenz zusätzlich die aktuelle Datei `assets/themes/admin_dark.qss` und
nach Möglichkeit Screenshots des Adminbereichs anhängen.

````text
Du gestaltest das Theme für den Adminbereich einer Fotobox-Anwendung
(PyQt6 auf Raspberry Pi, Vollbild 1920×1080, Bedienung mit Maus).

## Deine Aufgabe
Erstelle EINE vollständige Qt-Stylesheet-Datei (QSS). Antworte
ausschließlich mit dem Dateiinhalt (reines QSS, mit Kommentaren),
ohne Erklärtext davor oder danach. Die Datei wird 1:1 als
assets/themes/admin_dark.qss gespeichert.

## Look & Feel (Pflicht)
- Dark Mode: sehr dunkler, leicht bläulicher Hintergrund; Flächen in
  2–3 abgestuften Helligkeiten (Sidebar dunkler als Inhalt, Eingabe-
  felder/Listen als „Cards" leicht abgesetzt).
- Modern und aufgeräumt, orientiert an aktuellen Admin-Dashboards
  (klare Hierarchie, viel Ruhe, wenige kräftige Akzente).
- Stark gerundete Ecken: Buttons/Eingabefelder ca. 10–12 px,
  Listen/Container 12–16 px, Pill-Buttons voll gerundet.
- Akzentfarbe: kräftiges Orange (#ff6600 oder harmonische Variante);
  sparsam einsetzen (aktiver Tab, Primär-Buttons, Fokus, Auswahl).
- Destruktive Aktionen in gedecktem Rot, sekundär (Outline statt Fläche).
- Text: Weiß bis hellgrau, gedämpfte Hinweistexte ca. #8b94a7,
  Grundgröße 16 px, Überschriften deutlich größer/fett.
- Alle interaktiven Elemente brauchen sichtbare :hover-, :pressed-,
  :checked-, :focus- und :disabled-Zustände mit gutem Kontrast.
- Klickflächen großzügig (Padding ≥ 8–12 px, gut mit Maus/Finger treffbar).

## Struktur der Oberfläche (zur Orientierung)
- Links eine feste Sidebar (230 px): App-Name, Untertitel, darunter
  3 abhakbare Tab-Buttons (Szenen/Pfade/Einstellungen), unten ein
  Schließen-Button über einer Trennlinie.
- Inhalt „Szenen"/„Pfade": Überschrift + Hinweistext, darunter links
  eine Liste (440 px) mit Primär-/Löschen-Button, rechts ein
  Formular-Editor mit Abschnitts-Überschriften und Trennlinien.
- Inhalt „Einstellungen": zweite, schmalere Tab-Spalte (200 px) mit
  6 Tabs und einem Speichern-Button, rechts scrollbare Formulare,
  gegliedert in Blöcke (Abschnitts-Label + Trennlinie).

## Technischer Vertrag (Pflicht!)
Verwende AUSSCHLIESSLICH diese Selektoren – keine neuen erfinden:

#AdminRoot                          gesamter Hintergrund
#AdminSidebar                       linke Hauptnavigation
QLabel                              normale Formular-Labels
QLabel[kind="appname"]              App-Name in der Sidebar
QLabel[kind="subtitle"]             Untertitel in der Sidebar
QLabel[kind="title"]                Seitenüberschriften
QLabel[kind="section"]              Abschnitts-Überschriften
QLabel[kind="hint"]                 gedämpfter Erklärtext
QLabel[kind="warn"]                 Warntexte
QFrame[kind="separator"]            1 px Trennlinie (Höhe ist fix im Code)
QPushButton                         sekundäre Buttons
QPushButton[kind="tab"]             Sidebar-Tabs (checkable, :checked = aktiv)
QPushButton[kind="pill"]            Pill-Umschalter (checkable)
QPushButton[kind="primary"]         Hauptaktionen
QPushButton[kind="danger"]          Löschen
QPushButton[kind="close"]           Schließen-Button
QPushButton[kind="tool"]            kleine „…"-Buttons
QLineEdit, QComboBox                Eingaben (+ :focus, :disabled)
QComboBox::drop-down                Pfeilbereich (KEIN ::down-arrow stylen,
                                    sonst verschwindet der Pfeil)
QComboBox QAbstractItemView         aufgeklappte Liste
QListWidget, QListWidget::item      Listen (+ :hover, :selected)
QScrollArea, QScrollBar             Scrollflächen/-balken
QMessageBox, QToolTip               Dialoge, Tooltips

Außerdem zwingend übernehmen (Funktions-Fixes):
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }

## QSS-Einschränkungen (Qt ist KEIN Browser-CSS)
Erlaubt: background, color, border, border-radius, padding, margin,
font-size, font-weight, selection-background-color, min-/max-Größen,
qlineargradient(...).
NICHT unterstützt (nicht verwenden): box-shadow, transition/animation,
transform, var()/CSS-Variablen, text-transform, letter-spacing, opacity,
flex/grid, :focus-visible, calc(), externe Bilder/Fonts.

## Qualitätskriterien
- Kontrast: Text auf allen Flächen klar lesbar (WCAG-AA-Niveau anstreben).
- Aktiver Tab und Primär-Button müssen sofort ins Auge springen.
- Disabled-Zustände erkennbar, aber nicht unleserlich.
- Datei vollständig: ALLE oben gelisteten Selektoren müssen vorkommen.
````

## Wo der Code das Theme lädt

- `src/ui/theme.py` → `admin_stylesheet(config)`: liest die Datei, Fallback eingebaut.
- `src/ui/admin/admin_main.py`: wendet das QSS einmalig auf `#AdminRoot` an –
  es wirkt auf alle Kind-Widgets (Kaskade wie bei CSS).
- `src/ui/widgets.py` → `set_kind()`, `make_hint()`, `make_separator()`,
  `add_form_section()`: setzen die `kind`-Eigenschaften, die der Vertrag nutzt.

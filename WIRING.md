# Fotobox – Wiring Guide

---

## Parts list

| Qty | Component | Value / Notes |
|-----|-----------|---------------|
| 2 | Tactile pushbutton | 4-pin, spans breadboard center gap |
| 2 | LED | Recommended: different colors (e.g. yellow = flash, green = ready) |
| 2 | Resistor | **220 Ω** – for LEDs (red–red–brown–gold) |
| 4 | Resistor | **10 kΩ** – for buttons, 2 per button (brown–black–orange–gold) |
| 5 | Jumper wire, male-to-female | Pi GPIO header → breadboard |
| 6 | Jumper wire, male-to-male | Breadboard internal connections |

---

## Raspberry Pi 4 GPIO header

Pin 1 is at the **top-left** corner of the header (nearest the SD card slot).
Pins used by the fotobox are marked with ◄.

```
                        ┌──────────────────┐
                 3.3V  1│ ● ○ │2  5V        │
                GPIO2  3│ ● ○ │4  5V        │
                GPIO3  5│ ● ○ │6  GND       │
                GPIO4  7│ ● ○ │8  GPIO14    │
  ◄ GND (common) GND  9│ ● ○ │10 GPIO15    │
  ◄ Start button GPIO17 11│ ● ○ │12 GPIO18  │
  ◄ Admin button GPIO27 13│ ● ○ │14 GND     │
  ◄ Flash LED   GPIO22 15│ ● ● │16 GPIO23 ► │ Ready LED
                3.3V  17│ ● ○ │18 GPIO24    │
               GPIO10 19│ ● ○ │20 GND       │
                GPIO9 21│ ● ○ │22 GPIO25    │
               GPIO11 23│ ● ○ │24 GPIO8     │
                  GND 25│ ● ○ │26 GPIO7     │
                ID_SD 27│ ● ○ │28 ID_SC     │
                GPIO5 29│ ● ○ │30 GND       │
                GPIO6 31│ ● ○ │32 GPIO12    │
               GPIO13 33│ ● ○ │34 GND       │
               GPIO19 35│ ● ○ │36 GPIO16    │
               GPIO26 37│ ● ○ │38 GPIO20    │
                  GND 39│ ● ○ │40 GPIO21    │
                        └──────────────────┘
```

| Pi physical pin | Signal | Goes to |
|----------------|--------|---------|
| Pin  9 | GND | Breadboard X− rail |
| Pin 11 | GPIO 17 | Start button circuit |
| Pin 13 | GPIO 27 | Admin button circuit |
| Pin 15 | GPIO 22 | Flash LED circuit |
| Pin 16 | GPIO 23 | Ready LED circuit |

---

## Circuit diagrams

### Buttons — 2 × 10 kΩ per button

One 10 kΩ sits between the GPIO pin and the button; the second 10 kΩ sits between the button and GND. The Pi's internal pull-up keeps the GPIO HIGH while the button is open. Pressing the button pulls it LOW through both resistors.

```
Pi GPIO pin ──[10 kΩ R1]──[BUTTON]──[10 kΩ R2]── GND

Button open:  GPIO = HIGH (held up by Pi's internal ~50 kΩ pull-up)
Button pressed: GPIO pulled LOW through R1 + R2 to GND → event fires
```

### LEDs — 220 Ω series resistor

```
Pi GPIO pin ──[220 Ω]── LED (+, long leg) → LED (−, short leg) ── GND

GPIO output: 3.3 V
LED forward voltage: ≈ 2.0 V
Current: (3.3 − 2.0) / 220 ≈ 5.9 mA  (safe; max per GPIO pin is 16 mA)
```

---

## Breadboard layout

Columns: **X−** | A B C D E | *center gap* | F G H I J | **X+**
Rows: 1 – 20. X− is the common GND bus throughout.

```
      X─   A    B    C    D    E  ┊  F    G    H    I    J    X+
     ──────────────────────────────────────────────────────────────
  1   .   [R1]  .    .    .    .  ┊  .    .    .    .    .    .
  2   .   [R1]  .    .    .    .  ┊  .    .    .    .    .    .
  3   .   [R1] [■]  [B1] [■]  .  ┊  .   [■]  [B1] [■]  [R2]  .
  4   .    .   [■]  [B1] [■]  .  ┊  .   [■]  [B1] [■]  [R2]  .
  5  [G]   .    .    .    .    .  ┊  .    .    .    .   [R2]   .
  6   .    .    .    .    .    .  ┊  .    .    .    .    .    .
  7   .   [R1]  .    .    .    .  ┊  .    .    .    .    .    .
  8   .   [R1]  .    .    .    .  ┊  .    .    .    .    .    .
  9   .   [R1] [■]  [B2] [■]  .  ┊  .   [■]  [B2] [■]  [R2]  .
 10   .    .   [■]  [B2] [■]  .  ┊  .   [■]  [B2] [■]  [R2]  .
 11  [G]   .    .    .    .    .  ┊  .    .    .    .   [R2]   .
 12   .    .    .    .    .    .  ┊  .    .    .    .    .    .
 13   .    .    .    .    .    .  ┊  [R]   .   [*]  .    .    .
 14   .    .    .    .    .    .  ┊  [R]   .    .    .    .    .
 15   .    .    .    .    .    .  ┊  [R]  [A]   .    .    .    .
 16  [G]   .    .    .    .    .  ┊   .   [K]   .    .    .    .
 17   .    .    .    .    .    .  ┊  [R]   .   [*]  .    .    .
 18   .    .    .    .    .    .  ┊  [R]   .    .    .    .    .
 19   .    .    .    .    .    .  ┊  [R]  [A]   .    .    .    .
 20  [G]   .    .    .    .    .  ┊   .   [K]   .    .    .    .
     ──────────────────────────────────────────────────────────────

Legend:
  [G]  = hole jumped to GND (X− rail)
  [R1] = 10 kΩ resistor leg (placed vertically in col A)
  [R2] = 10 kΩ resistor leg (placed vertically in col J)
  [B1] = Start button leg  (button body spans center gap, rows 3–4)
  [B2] = Admin button leg  (button body spans center gap, rows 9–10)
  [■]  = hole occupied by button leg (internally connected by button body)
  [R]  = 220 Ω LED resistor leg (placed vertically in col F)
  [A]  = LED anode  (long leg, +)
  [K]  = LED cathode (short leg, −)
  [*]  = GPIO wire plugged in here (row 13 = GPIO22, row 17 = GPIO23)
   .   = empty hole
```

### How rows connect internally (breadboard rules)

- All holes A–E in **the same row** are connected → e.g. A3, B3, C3, D3, E3 are one net.
- All holes F–J in **the same row** are connected → e.g. F3, G3, H3, I3, J3 are one net.
- A–E and F–J are **not** connected (the center gap isolates them — that's what the button bridges).

This means:
- R1 bottom (A3) connects automatically to button left leg (C3) — same left-side row ✓
- Button right leg (H3) connects automatically to R2 top (J3) — same right-side row ✓
- LED resistor bottom (F15) connects automatically to LED anode (G15) — same right-side row ✓

---

## Step-by-step wiring

### Step 1 – GND bus
Plug a **male-to-female jumper** from **Pi physical pin 9 (GND)** into the **X− rail** (any hole).

---

### Step 2 – Start button (GPIO 17)

**R1 (10 kΩ):** place vertically in **col A, rows 1–3** (one leg in A1, other in A3). Bend the leads so they reach 3 rows apart.

**Pi Pin 11 (GPIO 17)** → male-to-female jumper → **row 1, col A** (R1 top).

**Button:** press the tactile button into the breadboard so its legs sit at:
- Left side: **col C, rows 3–4** (and col D, rows 3–4 — the second pair of legs)
- Right side: **col G, rows 3–4** (and col H, rows 3–4)

Row 3 left side (A–E) is one net → R1 bottom (A3) and button left leg (C3) connect automatically ✓

**R2 (10 kΩ):** place vertically in **col J, rows 3–5** (one leg in J3, other in J5).

Row 3 right side (F–J) is one net → button right leg (H3) and R2 top (J3) connect automatically ✓

**Wire:** male-to-male jumper from **row 5, col J** (R2 bottom) → **X− rail**.

---

### Step 3 – Admin button (GPIO 27)

**R1 (10 kΩ):** place vertically in **col A, rows 7–9**.

**Pi Pin 13 (GPIO 27)** → male-to-female jumper → **row 7, col A** (R1 top).

**Button:** rows 9–10, same column pattern as Step 2 (left: col C, right: col H).

**R2 (10 kΩ):** place vertically in **col J, rows 9–11**.

**Wire:** male-to-male jumper from **row 11, col J** → **X− rail**.

---

### Step 4 – Flash LED (GPIO 22)

**220 Ω resistor:** place vertically in **col F, rows 13–15**.

**Pi Pin 15 (GPIO 22)** → male-to-female jumper → **row 13, col H**.
Row 13 right side (F–J) connects H13 to F13 (resistor top) automatically ✓

**LED:** place vertically in **col G**:
- Anode (long leg, +) → **row 15, col G**
- Cathode (short leg, −) → **row 16, col G**

Row 15 right side connects G15 to F15 (resistor bottom) automatically ✓

**Wire:** male-to-male jumper from **row 16, col G** (cathode) → **X− rail**.

---

### Step 5 – Ready LED (GPIO 23)

**220 Ω resistor:** place vertically in **col F, rows 17–19**.

**Pi Pin 16 (GPIO 23)** → male-to-female jumper → **row 17, col H**.
Row 17 right side connects H17 to F17 (resistor top) automatically ✓

**LED:** place vertically in **col G**:
- Anode (long leg, +) → **row 19, col G**
- Cathode (short leg, −) → **row 20, col G**

**Wire:** male-to-male jumper from **row 20, col G** (cathode) → **X− rail**.

---

## Complete wire and component summary

### Jumper wires (9 total)

| # | From | To | Type |
|---|------|----|------|
| 1 | Pi Pin 9 (GND) | X− rail (any row) | M-F |
| 2 | Pi Pin 11 (GPIO 17) | Row 1, col A | M-F |
| 3 | Row 5, col J | X− rail | M-M |
| 4 | Pi Pin 13 (GPIO 27) | Row 7, col A | M-F |
| 5 | Row 11, col J | X− rail | M-M |
| 6 | Pi Pin 15 (GPIO 22) | Row 13, col H | M-F |
| 7 | Row 16, col G | X− rail | M-M |
| 8 | Pi Pin 16 (GPIO 23) | Row 17, col H | M-F |
| 9 | Row 20, col G | X− rail | M-M |

### Components on breadboard (8 total)

| Component | Rows | Column | Notes |
|-----------|------|--------|-------|
| Start button R1 (10 kΩ) | 1–3 | A (vertical) | Top = GPIO17 input |
| Start button | 3–4 | C / H (spans gap) | Left side = GPIO, right side = GND |
| Start button R2 (10 kΩ) | 3–5 | J (vertical) | Bottom → GND wire |
| Admin button R1 (10 kΩ) | 7–9 | A (vertical) | Top = GPIO27 input |
| Admin button | 9–10 | C / H (spans gap) | Left side = GPIO, right side = GND |
| Admin button R2 (10 kΩ) | 9–11 | J (vertical) | Bottom → GND wire |
| Flash LED resistor (220 Ω) | 13–15 | F (vertical) | Top = GPIO22 input |
| Flash LED | 15–16 | G (vertical) | Anode row 15, cathode row 16 |
| Ready LED resistor (220 Ω) | 17–19 | F (vertical) | Top = GPIO23 input |
| Ready LED | 19–20 | G (vertical) | Anode row 19, cathode row 20 |

---

## GPIO configuration in the software

These values live in `config/settings.json` and can be changed in the admin menu:

```json
"gpio": {
    "pin_start_button": 17,
    "pin_admin_button": 27,
    "pin_led_flash":    22,
    "pin_led_ready":    23
}
```

---

## Notes

- **Resistor color code – 10 kΩ:** brown – black – orange – gold (4-band)
- **Resistor color code – 220 Ω:** red – red – brown – gold (4-band)
- **LED polarity:** long leg = anode (+), short leg = cathode (−). If an LED does not light up, try turning it around.
- **Bending resistor leads:** standard 1/4 W through-hole resistors have long flexible leads — bend them gently with needle-nose pliers to fit the 3-row spacing (0.3").
- **Button orientation:** a 4-pin tactile button can usually only fit across the center gap in one orientation. If pressing the button does nothing or it always reads as pressed, rotate it 90°.
- **Internal pull-up:** the software enables the Pi's internal ~50 kΩ pull-up on both button pins (`pull_up=True`). This is what holds the GPIO HIGH when the button is not pressed. R1 + R2 then pull it LOW when the button is pressed.

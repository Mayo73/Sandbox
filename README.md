# Sandbox

Temporary files

## Batch-Steuerung (Start / Fortsetzen)

Eine kleine Batch-Oberflaeche mit zwei Funktionen.

### Dateien
- `ui.hta`     – grafische **HTML-Oberflaeche** (HTA) mit Buttons **Start** und **Fortsetzen**
- `menu.bat`   – Hauptmenue mit den Optionen **Start**, **Fortsetzen** und **Beenden**
- `start.bat`  – wird von Option **Start** in einem eigenen Fenster geoeffnet
- `resume.bat` – wird von Option **Fortsetzen** in einem eigenen Fenster geoeffnet

### HTML-Oberflaeche (ui.hta)
Eine moderne, anklickbare Oberflaeche auf HTML/CSS-Basis.

1. `ui.hta` per Doppelklick starten (oeffnet sich mit `mshta.exe`).
2. Auf **Start** oder **Fortsetzen** klicken – oder die Tasten **1** / **2** druecken.
3. Die jeweilige Batch-Datei oeffnet sich in einem **separaten Fenster**.
4. **Esc** schliesst die Oberflaeche.

Hinweis: Eine reine `.html`-Datei im Browser darf aus Sicherheitsgruenden keine
Batch-Dateien starten. Die `.hta` (HTML Application) ist daher noetig – sie ist
unter Windows ohne Zusatzsoftware lauffaehig.

### Verwendung
1. `menu.bat` per Doppelklick starten.
2. Mit den **Pfeiltasten Hoch/Runter** den Eintrag waehlen (gruener Cursor),
   mit **Enter** bestaetigen.
3. Die jeweilige Batch-Datei oeffnet sich in einem **separaten Fenster**; das Menue bleibt geoeffnet.
4. Eintrag **Beenden** schliesst das Menue.

Darstellung: weisse Schrift mit gruenem Auswahl-Cursor (ANSI-Farben,
funktioniert in cmd unter Windows 10/11).

Die eigentliche Logik kannst du in `start.bat` bzw. `resume.bat` an den
markierten Stellen eintragen.

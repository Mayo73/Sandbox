# Sandbox

Temporary files

## Batch-Steuerung (Start / Fortsetzen)

Eine kleine Batch-Oberflaeche mit zwei Funktionen.

### Dateien
- `menu.bat`   – Hauptmenue mit den Optionen **Start**, **Fortsetzen** und **Beenden**
- `start.bat`  – wird von Option **Start** in einem eigenen Fenster geoeffnet
- `resume.bat` – wird von Option **Fortsetzen** in einem eigenen Fenster geoeffnet

### Verwendung
1. `menu.bat` per Doppelklick starten.
2. Im Menue `1` (Start) oder `2` (Fortsetzen) waehlen und mit Enter bestaetigen.
3. Die jeweilige Batch-Datei oeffnet sich in einem **separaten Fenster**; das Menue bleibt geoeffnet.
4. Mit `0` wird das Menue beendet.

Die eigentliche Logik kannst du in `start.bat` bzw. `resume.bat` an den
markierten Stellen eintragen.

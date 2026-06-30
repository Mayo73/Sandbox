# Sandbox

Temporary files

## AUTO LV 2.0

Eine Steuerung mit den Aktionen Start, Ueberspringen, Fortsetzen und Stop,
wahlweise als Batch-Menue, HTML-Oberflaeche oder Python-Oberflaeche.

### Dateien
- `ui.py`         – grafische **Python-Oberflaeche** (Tkinter), keine Zusatzpakete
- `ui.hta`        – grafische **HTML-Oberflaeche** (HTA) mit denselben Aktionen
- `menu.bat`      – Hauptmenue (Pfeiltasten) mit allen Optionen + **Beenden**
- `run.bat`       – Option **Start** (Vorgang neu starten)
- `skip.bat`      – Option **Ueberspringen und Fortsetzen**
- `continue.bat`  – Option **Fortsetzen** (ohne zu ueberspringen)

### Python-Oberflaeche (ui.py)
Gleiche fuenf Aktionen wie die HTA, als native Tkinter-Oberflaeche
(Tkinter ist Teil der Python-Standardbibliothek – keine Installation noetig).

Die Batch-Dateien laufen hier **ohne externes Terminalfenster** – ihre Ausgabe
erscheint live im **eingebauten Konsolen-Panel** rechts in der GUI.

1. Per Doppelklick oder `python ui.py` starten.
2. Button anklicken – oder die Tasten **1** bis **5** druecken, **Esc** schliesst.
3. Start/Ueberspringen/Fortsetzen starten ihre Batch-Datei eingebettet (Ausgabe
   im Panel rechts); **Stop** schreibt `STOP.flag`, **Stop erzwingen** killt den
   `copyData.py`-Prozess. **Leeren** loescht die Konsole.

Technik: Die Batch wird mit `subprocess.Popen` und `CREATE_NO_WINDOW` gestartet
(kein Konsolenfenster). Die Ausgabe wird in einem Hintergrund-Thread gelesen und
ueber eine Queue thread-sicher in das Text-Widget geschrieben – so bleibt die
GUI bedienbar. Es laeuft jeweils ein Vorgang gleichzeitig.

Die Dateinamen stehen oben in `ui.py` im **CONFIG**-Block und koennen dort
angepasst werden. Voraussetzung: `ui.py` liegt im selben Ordner wie `copyData.py`.

### HTML-Oberflaeche (ui.hta)
Eine moderne, anklickbare Oberflaeche auf HTML/CSS-Basis mit vier Buttons:

1. **Start** – startet den Vorgang neu
2. **Ueberspringen und Fortsetzen** – ueberspringe letzte Mappe und setze fort
3. **Fortsetzen** – ohne zu ueberspringen
4. **Stop** – haelt `copyData.py` **sanft** an (sauber nach der aktuellen Mappe)
5. **Stop erzwingen** – beendet `copyData.py` **sofort/hart** (Notbremse)

Bedienung:
1. `ui.hta` per Doppelklick starten (oeffnet sich mit `mshta.exe`).
2. Button anklicken – oder die Tasten **1** bis **5** druecken.
3. Start/Skip/Fortsetzen oeffnen ihre Batch-Datei in einem **separaten Fenster**.
4. **Esc** schliesst die Oberflaeche.

Die zugeordneten Namen stehen oben in `ui.hta` im **CONFIG**-Block
(`FILE_START`, `FILE_SKIP`, `FILE_RESUME`, `STOP_FLAG`, `KILL_TARGET`) und
koennen dort angepasst werden.

**Sanftes Beenden (Stop):** Der Stop-Button erzeugt eine Datei `STOP.flag` im
Skriptverzeichnis. `copyData.py` prueft zu Beginn jeder Schleife (also zwischen
zwei Mappen), ob diese Datei existiert, beendet sich dann kontrolliert und
entfernt das Flag wieder. Die aktuell laufende Mappe wird **nie mittendrin**
abgebrochen, daher kann **Fortsetzen** danach korrekt weitermachen.
Voraussetzung: `ui.hta` liegt im selben Ordner wie `copyData.py`.

**Hartes Beenden (Stop erzwingen):** Notbremse, wenn das Skript nicht reagiert.
Sucht den Prozess, dessen Kommandozeile `KILL_TARGET` (Standard: `copyData.py`)
enthaelt, und beendet ihn sofort mit `Stop-Process -Force`. Eine Sicherheits-
abfrage muss bestaetigt werden. Achtung: die aktuelle Mappe kann dabei mitten
im Vorgang abgebrochen werden.

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

Die eigentliche Logik kannst du in `run.bat`, `skip.bat` bzw. `continue.bat`
an den markierten Stellen eintragen.

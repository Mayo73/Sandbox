# copilot-bridge

Startet Microsoft Edge mit offenem Debugging-Port, liest deinen Copilot-Chat
über das Chrome DevTools Protocol mit und führt Werkzeugaufrufe aus, die in den
Antworten stehen — Dateien, PowerShell, Prozesse, Maus/Tastatur. Das Ergebnis
schreibt die Bridge automatisch zurück in den Chat, sodass Copilot damit
weiterarbeiten kann.

```
  Edge (--remote-debugging-port)
        │  CDP WebSocket
        ▼
  watcher   liest den Chat aus dem DOM (inkl. Shadow-DOM)
        ▼
  protocol  findet {"bridge":1,...}-Aufrufe im Text und in Codeblöcken
        ▼
  policy    fragt dich an der Konsole / Allowlist / Rate-Limit
        ▼
  tools     fs.* shell.* proc.* ui.* window.* clipboard.*
        ▼
  responder schreibt das Ergebnis zurück in die Eingabezeile
```

## Installation

Python 3.11 oder neuer (wegen `tomllib`).

```powershell
cd copilot-bridge
pip install -r requirements.txt
python run_bridge.py doctor
```

`doctor` prüft Edge, Port, Pakete, Konfiguration und sagt dir, was fehlt.

Nur `websocket-client` ist Pflicht. `psutil`, `pyautogui`, `pygetwindow` und
`pyperclip` schalten zusätzliche Werkzeuge frei; fehlen sie, meldet das jeweilige
Werkzeug das beim Aufruf und alles andere läuft weiter.

## Schnellstart

```powershell
python run_bridge.py init          # config.toml anlegen
notepad config.toml                # allowed_roots anpassen
python run_bridge.py run
```

Beim ersten Start öffnet sich ein frisches Edge-Profil unter
`%LOCALAPPDATA%\CopilotBridge\EdgeProfile`. Dort einmal bei Copilot anmelden —
die Anmeldung bleibt erhalten.

Dann den Text aus [`PRIMER.md`](PRIMER.md) in den Chat kopieren und loslegen:

> Leg mir bitte auf dem Desktop eine Datei `notizen.txt` mit meiner
> Systemübersicht an.

Im Konsolenfenster erscheint:

```
========================================================================
  TOOL CALL   sys.info      (id a1)
  Machine, OS and user overview.
  args        {}
  source      code[json]
========================================================================
  [y] run once   [a] always this tool   [n] skip   [x] never this tool >
```

## Kommandos

| Befehl | Zweck |
|---|---|
| `python run_bridge.py run` | Edge starten, Chat überwachen, Aufrufe ausführen |
| `python run_bridge.py doctor` | Setup prüfen |
| `python run_bridge.py probe` | zeigen, was der Adapter im Chat findet (Selektoren anpassen) |
| `python run_bridge.py targets` | offene DevTools-Ziele auflisten |
| `python run_bridge.py tools` | alle Werkzeuge mit Signatur |
| `python run_bridge.py init` | `config.toml` aus der Vorlage schreiben |

Nützliche Schalter: `--mode auto_safe`, `--no-respond`, `--attach`,
`--real-profile`, `--port 9333`, `--selector "div.meine-nachricht"`.

## Das Protokoll

Ein Aufruf ist ein JSON-Objekt mit dem Marker `"bridge": 1`:

```json
{"bridge": 1, "tool": "fs.list", "args": {"path": "%USERPROFILE%\\Desktop"}, "id": "a1"}
```

Der Marker ist nötig, weil der Browser Markdown rendert: Die ```-Zäune sind im
DOM nicht mehr da, wenn die Bridge den Text liest. Gefunden wird der Aufruf
deshalb an drei Stellen — im Text der Nachricht, in den extrahierten
`<pre>`/`<code>`-Blöcken und zwischen `<<<BRIDGE ... BRIDGE>>>`-Markern. JSON
ohne den Marker wird ignoriert, Prosa über Werkzeuge also auch.

Mehrere Aufrufe in einer Nachricht:

```json
{"bridge": 1, "calls": [{"tool": "sys.info", "id": "a"},
                        {"tool": "fs.list", "args": {"path": "%TEMP%"}, "id": "b"}]}
```

Die Antwort landet als eigene Chat-Nachricht:

```
[bridge] Ergebnis:
{"bridge_result": 1, "id": "a1", "ok": true, "result": {...}}
```

Ergebnisse tragen `bridge_result` statt `bridge` und lösen deshalb nie eine
neue Ausführung aus.

## Werkzeuge

29 Stück, `python run_bridge.py tools` zeigt sie mit Signatur. `[safe]` heißt
lesend — nur diese laufen im Modus `auto_safe` ohne Rückfrage.

| Gruppe | Werkzeuge |
|---|---|
| Datei | `fs.list` `fs.stat` `fs.read` `fs.search` · `fs.write` `fs.mkdir` `fs.move` `fs.copy` `fs.delete` |
| Shell | `shell.run` (powershell / pwsh / cmd / sh) |
| System | `sys.info` `sys.env` · `proc.list` `proc.kill` · `app.open` |
| Zwischenablage | `clipboard.get` `clipboard.set` |
| Desktop | `ui.screenshot` `ui.screen_size` `ui.click` `ui.move` `ui.type` `ui.key` `ui.scroll` |
| Fenster | `window.list` `window.focus` |
| Bridge | `bridge.ping` `bridge.tools` `bridge.limits` |

Eigenes Werkzeug hinzufügen — eine Funktion in `copilot_bridge/tools/` genügt:

```python
@tool("git.status", "Git-Status eines Projekts.", {"path": "str"}, safe=True)
def git_status(ctx: ToolContext, path: str) -> dict:
    repo = ctx.resolve(path, must_exist=True)      # Sandbox-Prüfung
    ...
```

`safe=True` nur für lesende Werkzeuge. Unbekannte Argumente weist die Registry
von selbst ab.

## Sicherheit

Der Chat darf deinen Rechner steuern — das ist der Zweck, und genau deshalb
liegen mehrere Schranken davor:

- **`policy.mode`** — `ask` (Voreinstellung, jeder Aufruf wird an der Konsole
  bestätigt), `auto_safe` (lesende Werkzeuge laufen allein), `auto` (alles läuft).
- **`allowed_roots`** — Datei-Werkzeuge kommen aus diesen Ordnern nicht heraus,
  auch nicht über `..`. Ohne Einträge sind sie komplett aus.
- **`shell_denylist`** — Kommandos werden vor dem Start gegen eine Liste geprüft.
- **`allowed_tools` / `denied_tools`** — strikte Allowlist bzw. Sperrliste.
- **`max_calls_per_minute`** — begrenzt Schleifen.
- **Audit-Log** — jeder Aufruf mit Argumenten, Ergebnis und Entscheidung landet
  in `%LOCALAPPDATA%\CopilotBridge\audit.jsonl`.

Ein Punkt, der nicht in der Konfiguration steht: **Copilot liest Webseiten.**
Was auf einer Seite steht, kann beeinflussen, was Copilot danach schreibt — und
damit, welche Aufrufe bei dir ankommen. Deshalb ist `ask` die Voreinstellung.
Wenn du auf `auto` stellst, tu es mit enger `allowed_tools`-Liste und kleinen
`allowed_roots`.

Das Debugging-Profil ist getrennt vom Alltagsprofil. Der DevTools-Port lauscht
nur auf `127.0.0.1`, jedes lokale Programm kann ihn aber ansprechen, solange die
Bridge läuft.

## Wenn etwas klemmt

**„Edge started but port 9222 never answered"**
Meist läuft schon ein Edge mit demselben Profil. Entweder alle Edge-Fenster
schließen (auch im Infobereich, `msedge.exe` im Task-Manager) oder bei
`use_existing_profile = false` bleiben — dann stört das Alltagsprofil nicht.

**„attach_only is set but nothing is listening"**
Edge von Hand starten:
`msedge.exe --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=C:\Temp\EdgeDebug`

**Die Bridge sieht den Chat nicht**
`python run_bridge.py probe` zeigt, welcher Selektor greift, wie viele Turns
gefunden wurden und ob die Eingabezeile erkannt ist. Copilots Markup ändert sich
regelmäßig. Ist `strategy` gleich `none` oder `heuristic` und stimmt das
Ergebnis nicht, in Edge mit F12 die Nachrichten-Elemente ansehen und den
passenden Selektor setzen:

```powershell
python run_bridge.py run --selector "[data-testid='chat-turn']"
```

Der eingebaute Adapter probiert der Reihe nach bekannte Selektoren, durchsucht
dabei auch Shadow-DOM, und fällt zuletzt auf eine Struktur-Heuristik zurück.
Der ganze Lesevorgang steckt in `copilot_bridge/profiles/default.js` — eine
Datei, angenehm zu ändern.

**Antworten werden nicht in den Chat geschrieben**
Die Eingabezeile wird per Selektor gesucht. `probe` zeigt unter `composer` und
`sendButton`, was gefunden wurde. Zur Not `respond.submit = false` setzen und
den Text von Hand abschicken.

**Copilot hält sich nicht ans Format** → siehe [`PRIMER.md`](PRIMER.md).

## Tests

```powershell
python run_tests.py              # 101 Python-Tests, kein Browser nötig
npm install jsdom && node tests/js/adapter.test.mjs    # 13 Tests für den DOM-Adapter
```

Die Python-Tests laufen gegen `tests/fake_devtools.py`, einen Ersatz für Edges
DevTools-Endpunkt: HTTP-Ziele, CDP über WebSocket und eine simulierte Chat-Seite.
Damit werden auch Streaming-Erkennung, Reconnect, Dedup und das Zurückschreiben
echt durchgespielt. Der DOM-Adapter wird mit jsdom gegen ein nachgebautes
Chat-Markup getestet.

## Grenzen, ehrlich

- Getestet wurde gegen einen simulierten DevTools-Endpunkt und ein nachgebautes
  Chat-DOM, **nicht** gegen das echte copilot.microsoft.com — dafür fehlte mir
  hier Windows und ein Edge. Die Selektorenkette ist der Teil, der bei dir
  wahrscheinlich nachjustiert werden muss; `probe` ist dafür da.
- Die **Copilot-Seitenleiste** in Edge ist eine eigene WebView und taucht nicht
  zuverlässig als DevTools-Ziel auf. Der unterstützte Weg ist
  copilot.microsoft.com in einem normalen Tab.
- Copilot befolgt das Aufrufformat nicht garantiert und formuliert manchmal um.
- Ob das Automatisieren von Copilot mit Microsofts Nutzungsbedingungen vereinbar
  ist, solltest du selbst prüfen.

## Dateien

```
run_bridge.py              Einstiegspunkt
run_tests.py               Testlauf
config.example.toml        kommentierte Vorlage
PRIMER.md                  Text für den Chat
copilot_bridge/
  cli.py                   Kommandos und Überwachungsschleife
  cdp.py                   DevTools-Protokoll-Client
  edge.py                  Edge finden, starten, andocken
  watcher.py               Polling und Streaming-Erkennung
  protocol.py              Aufrufe finden und parsen
  policy.py                Regeln und Konsolen-Rückfrage
  executor.py              Policy + Werkzeug + Audit
  responder.py             Ergebnis in den Chat schreiben
  audit.py                 JSONL-Protokoll
  config.py                TOML-Konfiguration
  profiles/default.js      DOM-Adapter (hier anpassen)
  tools/                   fs, shell, system, desktop, bridge_meta
tests/                     Python- und JS-Tests, Fake-DevTools
```

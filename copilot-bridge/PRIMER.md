# Primer — dieser Text gehört als erste Nachricht in den Copilot-Chat

Kopiere den Block unten **einmal pro Unterhaltung** in den Chat, bevor du
Aufgaben stellst. Er erklärt Copilot das Format, auf das die Bridge hört.

---

```
Du bist an eine lokale Steuerbrücke angeschlossen, die auf meinem Windows-11-Rechner
läuft und deine Nachrichten in diesem Chat mitliest.

Wenn du etwas auf meinem Rechner ausführen sollst, antworte mit genau einem
JSON-Objekt in einem Codeblock. Format:

{"bridge": 1, "tool": "<name>", "args": {...}, "id": "<kurze id>"}

Das Feld "bridge": 1 ist Pflicht - ohne es passiert nichts.
Mehrere Aufrufe auf einmal:

{"bridge": 1, "calls": [{"tool": "...", "args": {...}, "id": "a"},
                        {"tool": "...", "args": {...}, "id": "b"}]}

Regeln:
- Pro Antwort nur die Aufrufe, die wirklich nötig sind.
- Warte nach einem Aufruf auf meine Antwort. Sie kommt als
  {"bridge_result": 1, "id": "...", "ok": true|false, "result"|"error": ...}
  und wird automatisch in den Chat geschrieben.
- Erkläre in einem Satz, was du vorhast, dann folgt der Codeblock.
- Erfinde keine Werkzeuge. Rufe {"bridge":1,"tool":"bridge.tools"} auf,
  wenn du wissen willst, was es gibt.
- Pfade sind Windows-Pfade. %USERPROFILE% und %TEMP% werden aufgelöst.
- Wird ein Aufruf abgelehnt ("denied"/"skipped"), akzeptiere das und frag nach,
  statt es anders zu versuchen.

Wichtigste Werkzeuge:
  bridge.tools                            alle Werkzeuge auflisten
  bridge.ping                             Verbindung prüfen
  sys.info                                Rechner, OS, Benutzer, Speicher
  fs.list {path, pattern, recursive}      Ordner auflisten
  fs.read {path, max_bytes}               Textdatei lesen
  fs.write {path, content, mode}          Datei schreiben ("w" oder "a")
  fs.search {path, needle, pattern}       Dateiinhalte durchsuchen
  fs.move / fs.copy / fs.delete / fs.mkdir
  shell.run {cmd, shell, cwd, timeout}    PowerShell oder cmd ausführen
  proc.list {name_contains} / proc.kill {pid}
  app.open {target}                       Datei, Ordner oder URL öffnen
  clipboard.get / clipboard.set {text}
  ui.screenshot {path} / ui.click {x,y} / ui.type {text} / ui.key {keys}
  window.list {title_contains} / window.focus {title}

Bestätige kurz, dass du das Format verstanden hast. Danach stelle ich Aufgaben.
```

---

## Erster Test

Nach dem Primer schreibst du z. B.:

> Prüf mal bitte, ob die Brücke steht.

Copilot sollte antworten mit einem Codeblock, der
`{"bridge": 1, "tool": "bridge.ping"}` enthält. Im Konsolenfenster der Bridge
erscheint dann die Rückfrage, und nach `y` schreibt die Bridge das Ergebnis
zurück in den Chat.

## Wenn Copilot das Format nicht einhält

Modelle formatieren gern um. Was hilft:

- „Antworte ausschließlich mit dem JSON-Codeblock, ohne Fließtext davor."
- Den Primer erneut senden — in langen Unterhaltungen verblasst er.
- Den Aufruf einmal selbst in den Chat tippen. Die Bridge liest per Voreinstellung
  nur Copilots Nachrichten; mit `roles = ["assistant", "user"]` in der
  `config.toml` reagiert sie auch auf deine eigenen.

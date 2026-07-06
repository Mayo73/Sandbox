"""
AUTO LV 2.0 - Grafische Steuerung (Python / Tkinter)

Die Batch-Dateien werden OHNE externes Terminalfenster gestartet; ihre Ausgabe
erscheint live in einem eingebauten Konsolen-Panel innerhalb der GUI.
Tkinter gehoert zur Python-Standardbibliothek - keine Zusatzpakete noetig.

Bedienung: Buttons anklicken oder Tasten 1-5, Esc schliesst das Fenster.
"""

import os
import queue
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

# =========================================================
#  CONFIG  -  hier die echten Dateinamen eintragen
# =========================================================
FILE_START  = "run.bat"        # Start
FILE_SKIP   = "skip.bat"       # Ueberspringen
FILE_RESUME = "continue.bat"   # Fortsetzen
STOP_FLAG   = "STOP.flag"      # Stop (sanft): Flag-Datei, die copyData.py auswertet
KILL_TARGET = "copyData.py"    # Stop erzwingen (hart): Prozess, der gekillt wird
# =========================================================

# Verzeichnis dieser Datei (damit Batch-Dateien/Flag gefunden werden)
BASE = os.path.dirname(os.path.abspath(__file__))

# Log-Verzeichnis wie in copyData.py: <Eltern-Ordner>/logs
LOG_DIR = Path(BASE).parent / "logs"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / f"log_ui_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
except Exception:
    LOG_FILE = None  # ohne Log-Datei weiterlaufen, falls Ordner nicht anlegbar

# Windows-Flag: Hilfsprozesse ohne eigenes Konsolenfenster starten
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# Ausgabe-Kodierung der Windows-Konsole (deutsche Umlaute im Batch-Output)
OUTPUT_ENCODING = "cp850" if os.name == "nt" else "utf-8"

# Farben
BG       = "#0c0c0c"
CARD     = "#161616"
CARD_HOV = "#1c1c1c"
WHITE    = "#f2f2f2"
GRAY     = "#9a9a9a"
SUBGRAY  = "#767676"
CONSOLE_BG = "#0a0a0a"
CONSOLE_FG = "#d8d8d8"

ACCENTS = {
    "start":  "#16c60c",
    "skip":   "#3b9eff",
    "resume": "#e5b700",
    "stop":   "#ff9d3d",
    "kill":   "#ff4d4d",
}


class App:
    def __init__(self, root):
        self.root = root
        self.proc = None                 # aktuell laufender Batch-Prozess
        self.out_q = queue.Queue()        # Ausgabe-Zeilen aus dem Lese-Thread

        root.title("AUTO LV 2.0")
        root.configure(bg=BG)
        root.geometry("1000x640")
        root.minsize(860, 560)

        # ----- Kopfbereich -----
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=22, pady=(18, 8))
        tk.Label(head, text="A U T O   L V   2 . 0",
                 font=("Segoe UI", 20, "bold"), fg=WHITE, bg=BG).pack(anchor="w")
        tk.Label(head, text="Waehle eine Option  -  Tasten 1 - 5  -  Esc zum Schliessen",
                 font=("Segoe UI", 9), fg=SUBGRAY, bg=BG).pack(anchor="w")

        # ----- Koerper: links Buttons, rechts Konsole -----
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=(4, 8))

        left = tk.Frame(body, bg=BG, width=360)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        self._button(left, "start",  "1", "▶", "Start",
                     "neue Zielmappe, Vorgang neu", self.do_start)
        self._button(left, "skip",   "2", "⏭", "Ueberspringen",
                     "aktuelle Mappe ueberspringen", self.do_skip)
        self._button(left, "resume", "3", "↻", "Fortsetzen",
                     "ohne zu ueberspringen", self.do_resume)
        tk.Frame(left, bg="#262626", height=1).pack(fill="x", pady=(8, 2))
        self._button(left, "stop",   "4", "■", "Stop",
                     "sanft - nach aktueller Mappe", self.do_stop)
        self._button(left, "kill",   "5", "✕", "Stop erzwingen",
                     "hart - sofort beenden", self.do_force_stop)

        # ----- Konsole rechts -----
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))

        bar = tk.Frame(right, bg=BG)
        bar.pack(fill="x")
        tk.Label(bar, text="Ausgabe", font=("Segoe UI", 10, "bold"),
                 fg=GRAY, bg=BG).pack(side="left")
        self.status = tk.Label(bar, text="bereit", font=("Segoe UI", 9),
                               fg=SUBGRAY, bg=BG)
        self.status.pack(side="left", padx=10)
        tk.Button(bar, text="Leeren", command=self.clear_console,
                  font=("Segoe UI", 8), fg=GRAY, bg=CARD, bd=0,
                  activebackground=CARD_HOV, activeforeground=WHITE,
                  padx=10, pady=2, cursor="hand2").pack(side="right")

        cframe = tk.Frame(right, bg=BG)
        cframe.pack(fill="both", expand=True, pady=(6, 0))
        scroll = tk.Scrollbar(cframe)
        scroll.pack(side="right", fill="y")
        self.console = tk.Text(
            cframe, bg=CONSOLE_BG, fg=CONSOLE_FG, insertbackground=CONSOLE_FG,
            font=("Consolas", 10), wrap="none", relief="flat", state="disabled",
            highlightbackground="#2a2a2a", highlightthickness=1,
            yscrollcommand=scroll.set,
        )
        self.console.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.console.yview)

        # Tastatur
        root.bind("1", lambda e: self.do_start())
        root.bind("2", lambda e: self.do_skip())
        root.bind("3", lambda e: self.do_resume())
        root.bind("4", lambda e: self.do_stop())
        root.bind("5", lambda e: self.do_force_stop())
        root.bind("<Escape>", lambda e: root.destroy())

        self._poll_output()

    # ----- Button-Bau -----
    def _button(self, parent, kind, key, icon, label, desc, command):
        accent = ACCENTS[kind]
        card = tk.Frame(parent, bg=CARD, highlightbackground="#2a2a2a",
                        highlightthickness=1, cursor="hand2")
        card.pack(fill="x", pady=6)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=14, pady=10)

        icon_lbl = tk.Label(inner, text=icon, font=("Segoe UI", 18, "bold"),
                            fg=accent, bg=CARD, width=2)
        icon_lbl.pack(side="left", padx=(0, 12))
        text = tk.Frame(inner, bg=CARD)
        text.pack(side="left", fill="x", expand=True)
        title_lbl = tk.Label(text, text=label, font=("Segoe UI", 12, "bold"),
                             fg=WHITE, bg=CARD, anchor="w")
        title_lbl.pack(fill="x")
        desc_lbl = tk.Label(text, text=desc, font=("Segoe UI", 8),
                            fg=GRAY, bg=CARD, anchor="w")
        desc_lbl.pack(fill="x")
        key_lbl = tk.Label(inner, text=key, font=("Segoe UI", 9), fg="#8a8a8a",
                           bg=CARD, padx=7, pady=1,
                           highlightbackground="#333", highlightthickness=1)
        key_lbl.pack(side="right")

        widgets = [card, inner, icon_lbl, text, title_lbl, desc_lbl, key_lbl]

        def on_enter(_):
            for w in widgets:
                w.configure(bg=CARD_HOV)
            card.configure(highlightbackground=accent)

        def on_leave(_):
            for w in widgets:
                w.configure(bg=CARD)
            card.configure(highlightbackground="#2a2a2a")

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e: command())

    # ----- Konsole -----
    def append(self, text):
        self.console.configure(state="normal")
        self.console.insert("end", text)
        self.console.see("end")
        self.console.configure(state="disabled")

    def write_log(self, message):
        """Schreibt einen Zeitstempel-Eintrag in die Log-Datei (wie in
        copyData.py) und zeigt ihn zusaetzlich in der eingebetteten Konsole."""
        line = "%s - %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
        if LOG_FILE is not None:
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as exc:
                line += "   [Log-Fehler: %s]" % exc
        self.append(line + "\n")

    def clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _poll_output(self):
        try:
            while True:
                self.append(self.out_q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(80, self._poll_output)

    # ----- Batch eingebettet ausfuehren -----
    def run_batch(self, filename):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning(
                "Laeuft bereits",
                "Es laeuft bereits ein Vorgang. Bitte zuerst stoppen.")
            return
        path = os.path.join(BASE, filename)
        if not os.path.exists(path):
            messagebox.showerror("Datei nicht gefunden", path)
            return

        self.append("\n" + "=" * 60 + "\n")
        self.append(">> %s\n" % filename)
        self.append("=" * 60 + "\n")
        self.status.configure(text="laeuft: %s" % filename, fg=ACCENTS["start"])

        def worker():
            try:
                # PYTHONUNBUFFERED=1 -> copyData.py flusht seine Ausgabe sofort,
                # statt sie zu puffern (sonst erscheint im Panel lange nichts,
                # obwohl das Skript laeuft).
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                if os.name == "nt":
                    self.proc = subprocess.Popen(
                        ["cmd", "/c", path],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        creationflags=CREATE_NO_WINDOW, cwd=BASE, env=env, bufsize=0,
                    )
                else:
                    self.proc = subprocess.Popen(
                        ["bash", path],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=BASE,
                        env=env, bufsize=0,
                    )
                # readline-Schleife statt "for line in ..." -> keine ~8 KB
                # Read-Ahead-Pufferung, Zeilen erscheinen sofort.
                for raw in iter(self.proc.stdout.readline, b""):
                    self.out_q.put(raw.decode(OUTPUT_ENCODING, errors="replace"))
                self.proc.wait()
                self.out_q.put("\n[Vorgang beendet, Exit-Code %s]\n"
                               % self.proc.returncode)
            except Exception as exc:
                self.out_q.put("\n[Fehler beim Ausfuehren: %s]\n" % exc)
            finally:
                self.root.after(0, lambda: self.status.configure(
                    text="bereit", fg=SUBGRAY))

        threading.Thread(target=worker, daemon=True).start()

    # ----- Aktionen -----
    def do_start(self):
        self.run_batch(FILE_START)

    def do_skip(self):
        self.write_log("Aktion 'Ueberspringen' - starte %s" % FILE_SKIP)
        self.run_batch(FILE_SKIP)

    def do_resume(self):
        self.write_log("Aktion 'Fortsetzen' - starte %s" % FILE_RESUME)
        self.run_batch(FILE_RESUME)

    def do_stop(self):
        """Sanft: schreibt STOP.flag. copyData.py beendet sich nach der Mappe."""
        open(os.path.join(BASE, STOP_FLAG), "w").close()
        self.write_log("Aktion 'Stop' (sanft) - %s geschrieben, %s beendet sich "
                       "nach der aktuellen Mappe" % (STOP_FLAG, KILL_TARGET))

    def do_force_stop(self):
        """Hart: killt copyData.py sofort (Notbremse)."""
        if not messagebox.askyesno(
            "Stop erzwingen",
            "%s wird SOFORT beendet - die aktuelle Mappe wird ggf. mittendrin "
            "abgebrochen.\n\nWirklich erzwingen?" % KILL_TARGET):
            self.write_log("Aktion 'Stop erzwingen' - abgebrochen (nicht bestaetigt)")
            return
        if self.kill_process():
            self.write_log("Aktion 'Stop erzwingen' (hart) - %s wurde beendet"
                           % KILL_TARGET)
        else:
            self.write_log("Aktion 'Stop erzwingen' (hart) - es lief kein %s"
                           % KILL_TARGET)

    def kill_process(self):
        """Beendet den copyData.py-Prozess hart. True, wenn etwas beendet wurde."""
        if os.name != "nt":
            return False
        ps = (
            "$p=Get-CimInstance Win32_Process | "
            "? {{ $_.CommandLine -like '*{t}*' }}; "
            "if($p){{ $p | % {{ Stop-Process -Id $_.ProcessId -Force }}; exit 0 }} "
            "else {{ exit 1 }}"
        ).format(t=KILL_TARGET)
        rc = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
        ).returncode
        return rc == 0


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

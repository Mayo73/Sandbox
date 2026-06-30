"""
AUTO LV 2.0 - Grafische Steuerung (Python / Tkinter)

Startet die Batch-Dateien in einem separaten Fenster und steuert copyData.py.
Tkinter gehoert zur Python-Standardbibliothek - keine Zusatzpakete noetig.

Bedienung: Buttons anklicken oder Tasten 1-5, Esc schliesst das Fenster.
"""

import os
import sys
import subprocess
import tkinter as tk
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

# Windows: kein zusaetzliches Konsolenfenster fuer Hilfsprozesse
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_CONSOLE = 0x00000010 if os.name == "nt" else 0


# ---------------------------------------------------------
#  Aktionen
# ---------------------------------------------------------
def run_batch(filename):
    """Oeffnet eine Batch-Datei in einem eigenen Konsolenfenster (bleibt offen)."""
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        messagebox.showerror("Datei nicht gefunden", path)
        return
    if os.name == "nt":
        # cmd /k -> Fenster bleibt nach dem Durchlauf offen
        subprocess.Popen(["cmd", "/k", path], creationflags=CREATE_NEW_CONSOLE)
    else:
        # Fallback fuer Nicht-Windows (Entwicklung/Test)
        subprocess.Popen(["bash", path])


def kill_process():
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


def do_start():
    run_batch(FILE_START)


def do_skip():
    run_batch(FILE_SKIP)


def do_resume():
    run_batch(FILE_RESUME)


def do_stop():
    """Sanft: schreibt STOP.flag. copyData.py beendet sich nach der aktuellen Mappe."""
    open(os.path.join(BASE, STOP_FLAG), "w").close()
    messagebox.showinfo(
        "Stop angefordert",
        f"{KILL_TARGET} beendet sich sauber nach der aktuellen Mappe.",
    )


def do_force_stop():
    """Hart: killt copyData.py sofort (Notbremse)."""
    if not messagebox.askyesno(
        "Stop erzwingen",
        f"{KILL_TARGET} wird SOFORT beendet - die aktuelle Mappe wird ggf. "
        "mittendrin abgebrochen.\n\nWirklich erzwingen?",
    ):
        return
    if kill_process():
        messagebox.showinfo("Stop erzwingen", f"{KILL_TARGET} wurde hart beendet.")
    else:
        messagebox.showinfo("Stop erzwingen", f"Es laeuft kein {KILL_TARGET}.")


# ---------------------------------------------------------
#  Oberflaeche
# ---------------------------------------------------------
BG       = "#0c0c0c"
CARD     = "#161616"
CARD_HOV = "#1c1c1c"
WHITE    = "#f2f2f2"
GRAY     = "#9a9a9a"
SUBGRAY  = "#767676"

ACCENTS = {
    "start":  "#16c60c",
    "skip":   "#3b9eff",
    "resume": "#e5b700",
    "stop":   "#ff9d3d",
    "kill":   "#ff4d4d",
}


def make_button(parent, kind, key, icon, label, desc, command):
    accent = ACCENTS[kind]
    card = tk.Frame(parent, bg=CARD, highlightbackground="#2a2a2a",
                    highlightthickness=1, cursor="hand2")
    card.pack(fill="x", pady=8)

    inner = tk.Frame(card, bg=CARD)
    inner.pack(fill="x", padx=16, pady=12)

    icon_lbl = tk.Label(inner, text=icon, font=("Segoe UI", 20, "bold"),
                        fg=accent, bg=CARD, width=2)
    icon_lbl.pack(side="left", padx=(0, 14))

    text = tk.Frame(inner, bg=CARD)
    text.pack(side="left", fill="x", expand=True)
    title_lbl = tk.Label(text, text=label, font=("Segoe UI", 13, "bold"),
                         fg=WHITE, bg=CARD, anchor="w")
    title_lbl.pack(fill="x")
    desc_lbl = tk.Label(text, text=desc, font=("Segoe UI", 9),
                        fg=GRAY, bg=CARD, anchor="w")
    desc_lbl.pack(fill="x")

    key_lbl = tk.Label(inner, text=key, font=("Segoe UI", 9), fg="#8a8a8a",
                       bg=CARD, padx=8, pady=1,
                       highlightbackground="#333", highlightthickness=1)
    key_lbl.pack(side="right")

    widgets = [card, inner, icon_lbl, text, title_lbl, desc_lbl, key_lbl]

    def on_enter(_):
        for w in widgets:
            w.configure(bg=CARD_HOV)
        card.configure(highlightbackground=accent)

    def on_leave(_):
        for w in widgets:
            w.configure(bg=CARD_HOV if False else CARD)
        card.configure(highlightbackground="#2a2a2a")

    def on_click(_):
        command()

    for w in widgets:
        w.bind("<Enter>", on_enter)
        w.bind("<Leave>", on_leave)
        w.bind("<Button-1>", on_click)

    return card


def main():
    root = tk.Tk()
    root.title("AUTO LV 2.0")
    root.configure(bg=BG)
    root.geometry("620x620")
    root.minsize(520, 560)

    wrap = tk.Frame(root, bg=BG)
    wrap.pack(fill="both", expand=True, padx=26, pady=22)

    tk.Label(wrap, text="A U T O   L V   2 . 0", font=("Segoe UI", 22, "bold"),
             fg=WHITE, bg=BG).pack()
    tk.Label(wrap, text="Waehle eine Option  -  Tasten 1 - 5  -  Esc zum Schliessen",
             font=("Segoe UI", 9), fg=SUBGRAY, bg=BG).pack(pady=(2, 20))

    btns = tk.Frame(wrap, bg=BG)
    btns.pack(fill="x")

    make_button(btns, "start",  "1", "▶", "Start",
                "erstellt neue Zielmappe und startet den Vorgang neu", do_start)
    make_button(btns, "skip",   "2", "⏭", "Ueberspringen",
                "ueberspringe aktuelle Mappe und setze den Vorgang fort", do_skip)
    make_button(btns, "resume", "3", "↻", "Fortsetzen",
                "ohne zu ueberspringen", do_resume)

    tk.Frame(btns, bg="#262626", height=1).pack(fill="x", pady=(8, 2))

    make_button(btns, "stop",   "4", "■", "Stop",
                "sanft - haelt nach der aktuellen Mappe an", do_stop)
    make_button(btns, "kill",   "5", "✕", "Stop erzwingen",
                "hart - beendet das Programm sofort", do_force_stop)

    tk.Label(wrap, text="Start / Ueberspringen / Fortsetzen oeffnen ihre Batch-Datei "
             "in einem separaten Fenster", font=("Segoe UI", 8), fg="#555",
             bg=BG).pack(side="bottom", pady=(16, 0))

    # Tastatur
    root.bind("1", lambda e: do_start())
    root.bind("2", lambda e: do_skip())
    root.bind("3", lambda e: do_resume())
    root.bind("4", lambda e: do_stop())
    root.bind("5", lambda e: do_force_stop())
    root.bind("<Escape>", lambda e: root.destroy())

    root.mainloop()


if __name__ == "__main__":
    main()

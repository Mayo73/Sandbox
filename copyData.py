from openpyxl import load_workbook
from openpyxl.styles import Font
from datetime import datetime
from pathlib import Path
import os
import warnings
import subprocess # Für Powershell
import sys # Für Powershell

# Warnung bezüglich bedingter Formatierung ignorieren, da openpyxl diese nicht unterstützt
warnings.filterwarnings(
    "ignore",
    message="Conditional Formatting extension is not supported and will be removed",
    category=UserWarning,
)

# Erzeugung des logs-Verzeichnisses, falls es nicht existiert
script_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = Path(script_dir).parent / "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
# Datei erstellen in AutoLV_2.0\logs mit aktuellem Zeitstempel
log_file = log_dir / f"log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
log_file.touch()
with open(log_file, "w") as datei:
    datei.write("Log-Datei erstellt\n")

# Funktion zum Schreiben von Log-Einträgen
def write_log(message):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        print(message)

# Skript-Verzeichnis ermitteln
script_dir = os.path.dirname(os.path.abspath(__file__))

# Anzahl Zeilen aus progress.txt aus erster Zeile lesen, damit Fortschritt berechnet werden kann
progress_file = os.path.join(script_dir, "progress.txt")
with open(progress_file, "r") as f:
    total_lines = int(f.readline().strip())

# Funktion zum Löschen einer Zeile in paths.txt und Berechnung des Fortschritts
paths_file = os.path.join(script_dir, "paths.txt")
def delete_line_from_paths_file():
    with open(paths_file, "r", encoding="cp1252") as f:
        lines = f.readlines()
    with open(paths_file, "w", encoding="cp1252") as f:
        f.writelines(lines[1:])
    write_log("Die Zeile in paths.txt wurde gelöscht.")
    # Prozentualen Fortschritt ausgeben
    progress = 100 - ((((len(lines) - 1) / total_lines)) * 100) if total_lines > 0 else 0
    write_log(f"Fortschritt: {progress:.2f}%")
    write_log("----------------------------------------")

# Schleife bis paths.txt leer ist
write_log("----------------------------------------")
while True:
    if not os.path.exists(paths_file):
        write_log("Die Datei paths.txt existiert nicht. Das Skript wird beendet.")
        break
    with open(paths_file, encoding="cp1252") as f:
        lines = f.readlines()
    if not lines:
        write_log("Die Datei paths.txt ist leer. Das Skript wird beendet.")
        break

    # Pfad zur Quelldatei aus der ersten Zeile von paths.txt lesen
    with open(paths_file, encoding="cp1252") as f:
        quelle = f.readline().strip()

    # Überprüfen, ob der Pfad gültig ist
    if not quelle:
        raise ValueError("Die erste Zeile in paths.txt darf nicht leer sein.")
    if not os.path.isabs(quelle):
        quelle = os.path.abspath(os.path.join(script_dir, quelle))
    # Prüfen ob Teilstring zProdstd im Pfad enthalten ist, wenn ja breakt die Schleife, da dies das Ende markiert
    if "zProdstd" in quelle:
        break

    # Prüfen, ob die Excel-Datei existiert
    if not os.path.exists(quelle):
        #raise ValueError(f"Die Excel-Datei '{quelle}' existiert nicht.")
        write_log(f"!!!!!!!!!!!!!!!!!!Die Excel-Datei '{quelle}' existiert nicht.")
        delete_line_from_paths_file() # Zeile löschen, damit continue.bat mit der nächsten Mappe fortfahren kann
        continue

    # Excel-Datei laden mit keep_vba=True, um VBA-Makros zu erhalten
    # keep_links=True erhält externe Formelbezüge beim Speichern (funktioniert nicht), aber verhindert das Entfernen von Formeln, die sonst durch Werte ersetzt würden
    # read_only=True ermöglicht das Laden von Dateien, die möglicherweise von einem Benutzer geöffnet sind, da es die Datei nicht sperrt und verhinert, dass openpyxl die Formatierung entfernt
    try:
        workbook = load_workbook(quelle, keep_vba=True, keep_links=True, read_only=True)
        write_log(f"Die Excel-Datei '{quelle}' wurde erfolgreich geladen.")
    except Exception as e:
        write_log(f"Fehler beim Laden der Excel-Datei, wahrscheinlich vom Benutzer geöffnet: {str(e)}")
        continue

    # Arbeitsblatt "Leistungsnachweis" auswählen
    if "Leistungsnachweis" not in workbook.sheetnames:
        #raise ValueError("Das Arbeitsblatt 'Leistungsnachweis' wurde in der Excel-Datei nicht gefunden.")
        write_log("!!!!!!!!!!!!!!!!!!Das Arbeitsblatt 'Leistungsnachweis' wurde in der Excel-Datei nicht gefunden.")
        delete_line_from_paths_file()
        continue
    worksheet = workbook["Leistungsnachweis"]

    # Zeile mit Wert in Spalte A suchen ab Zeile 11
    start_row = 11
    first_value_row = None
    for row in range(start_row, worksheet.max_row + 1):
        cell_value = worksheet.cell(row=row, column=1).value
        if cell_value is not None and str(cell_value).strip() != "":
            first_value_row = row
            break
    if first_value_row is None:
        #raise ValueError("Es wurde keine Zeile mit einem Wert in Spalte A ab Zeile 11 gefunden.")
        write_log("!!!!!!!!!!!!!!!!!!Es wurde keine Zeile mit einem Wert in Spalte A ab Zeile 11 gefunden.")
        delete_line_from_paths_file()
        continue

    # Zeile suchen welche "gezogen am" enthält in Spalte A ab first_value_row
    gezogen_am_row = None
    for row in range(first_value_row, worksheet.max_row + 1):
        cell_value = worksheet.cell(row=row, column=1).value
        if cell_value and "gezogen am" in str(cell_value).lower():
            gezogen_am_row = row
            break
    if gezogen_am_row is None:
        #raise ValueError("Es wurde keine Zeile gefunden, die 'gezogen am' in Spalte A enthält.")
        write_log("!!!!!!!!!!!!!!!!!!Es wurde keine Zeile gefunden, die 'gezogen am' in Spalte A enthält.")
        delete_line_from_paths_file()
        continue

    # Werte aus Bereich first_value_row bis gezogen_am_row in Spalten A bis N kopieren
    data = []
    for row in range(first_value_row, gezogen_am_row):
        row_data = []
        for col in range(1, 15):  # Spalten A bis N
            cell_value = worksheet.cell(row=row, column=col).value
            row_data.append(cell_value)
        data.append(row_data)
    # Wenn keine Daten gefunden wurden, schleife überspringen
    if not data:
        write_log("Keine neuen Einträge, Mappe wird übersprungen.")
        #workbook.save(quelle)
        workbook.close()
        delete_line_from_paths_file()
        continue
    write_log(f"Es wurden {len(data)} Zeilen mit Daten aus 'Leistungsnachweis' kopiert.")

    # Datei als speichern und schließen
    #workbook.save(quelle)
    workbook.close()

    # Zeile als Übergabeparameter für PowerShell-Skript definieren
    timestamp_row = first_value_row
    if timestamp_row < 13:
        timestamp_row = 13 # Wenn die Zeile für den Zeitstempel vor Zeile 13 liegt, wird stattdessen Zeile 13 verwendet, um Formatierungsfehler zu vermeiden
    write_log(f"Der Zeitstempel wird in Zeile {timestamp_row} eingefügt.")
    
    # Zeitstempel mit PowerShell-Skript --------------------------------------------------

    # PowerShell-Skript
    ps1_file = os.path.join(script_dir, "timestamp.ps1")

    # Kommando bauen
    command = [
        "powershell",
        "-ExecutionPolicy", "Bypass",
        "-File", ps1_file,
        "-filePath", quelle,  # Übergabe des Excel-Dateipfads als Argument
        "-PasteRange", str(timestamp_row)  # Übergabe der Zeilennummer für den Zeitstempel als Argument
    ]

    # Ausführen
    result = subprocess.run(command, capture_output=True, text=True)

    # Ausgabe prüfen
    #write_log("STDOUT:", result.stdout)
    #write_log("STDERR:", result.stderr)
    #Powershell Ende -----------------------------------------------------------------------

    # Projektverzeichnis von AutoLV_2.0 ermitteln
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = Path(script_dir).parent

    # Zielmappe.xlsx laden
    zielmappe_path = os.path.join(project_dir, "Zielmappe.xlsx")
    if not os.path.exists(zielmappe_path):
        raise ValueError(f"Die Zielmappe '{zielmappe_path}' existiert nicht.")
    zielmappe = load_workbook(zielmappe_path)
    ziel_worksheet = zielmappe.active

    # Ende des Datenbereichs ermitteln
    ziel_row = ziel_worksheet.max_row + 1
    write_log(f"Die Daten werden ab Zeile {ziel_row} in Zielmappe.xlsx eingefügt.")

    # Daten in Zielmappe.xlsx einfügen
    for row_data in data:
        for col_index, cell_value in enumerate(row_data, start=1):
            ziel_worksheet.cell(row=ziel_row, column=col_index).value = cell_value
        ziel_row += 1

    # Zielmappe speichern
    zielmappe.save(zielmappe_path)
    write_log("Daten wurden erfolgreich in Zielmappe.xlsx kopiert.")

    # Lösche Zeile in paths.txt
    delete_line_from_paths_file()

try:
    zielmappe.save(zielmappe_path)
    write_log("Zielmappe erfolgreich gespeichert.")
except Exception as e:
    write_log(f"Fehler beim Speichern der Zielmappe: {e}")
finally:
    try:
        zielmappe.close()
        write_log("Zielmappe geschlossen.")
    except Exception as e:
        write_log(f"Fehler beim Schließen der Zielmappe: {e}")

write_log("Das Skript wurde erfolgreich ausgeführt.")
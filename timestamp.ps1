param(
    [string]$filePath,
    [int]$pasteRange
)

if (-not (Test-Path $filePath)) {
    Write-Host "Datei nicht gefunden!"
    exit
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.AskToUpdateLinks = $false # Wichtig um Aktualisierungsmeldung zu unterdrücken

try {
    $workbook = $excel.Workbooks.Open($filePath, 3, $true) # , 3, $true - Um automatisch zu aktualisieren, falls Meldung doch kommt
    $sheet = $workbook.Sheets.Item("Leistungsnachweis")

    $range = $sheet.Range("A$pasteRange")
    $range.EntireRow.Insert() | Out-Null # Spuckt "True" in der Konsole aus
    #Start-Sleep -Seconds 2
    $rangeFormate = $sheet.Range("A$pasteRange")
    $rangeFormate.EntireRow.Interior.ColorIndex = 0
    $rangeFormate.EntireRow.Font.ColorIndex = 13
    $rangeFormate.EntireRow.Font.Bold = $true
    #Start-Sleep -Seconds 1
    $timestamp = Get-Date
    $sheet.Cells.Item($pasteRange, 1).Value() = "gezogen am $timestamp BFS - AutoLV"

    $workbook.Save()
    $workbook.Close()
}
catch {
    Write-Host "Fehler: $_"
}
finally {
    $excel.Quit()

    # Speicher freigeben
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($sheet) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($workbook) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null

    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

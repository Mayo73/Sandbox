@echo off
setlocal EnableExtensions
title Fortsetzen
color 0E

echo.
echo   ============================================================
echo   ==                 F O R T S E T Z E N                   ==
echo   ============================================================
echo.
echo   Der Vorgang wird fortgesetzt...
echo.

:: ------------------------------------------------------------
:: Hier kommt deine eigene Logik fuer "Fortsetzen" hinein.
:: Beispiel:
:: ------------------------------------------------------------
echo   [Schritt 1] Suche letzten Stand...
timeout /t 1 >nul
echo   [Schritt 2] Lade gespeicherte Sitzung...
timeout /t 1 >nul
echo   [Schritt 3] Vorgang wird fortgesetzt.
echo.

echo   Fertig. Dieses Fenster kann geschlossen werden.
echo.
pause
endlocal
exit /b 0

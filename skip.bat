@echo off
setlocal EnableExtensions
title Ueberspringen und Fortsetzen
color 0B

echo.
echo   ============================================================
echo   ==        U E B E R S P R I N G E N   +   F O R T        ==
echo   ============================================================
echo.
echo   Letzte Mappe wird uebersprungen, Vorgang wird fortgesetzt...
echo.

:: ------------------------------------------------------------
:: Hier kommt deine Logik fuer "Ueberspringen und Fortsetzen" hinein.
:: Beispiel:
:: ------------------------------------------------------------
echo   [Schritt 1] Suche letzten Stand...
timeout /t 1 >nul
echo   [Schritt 2] Ueberspringe letzte Mappe...
timeout /t 1 >nul
echo   [Schritt 3] Setze Vorgang fort.
echo.

echo   Fertig. Dieses Fenster kann geschlossen werden.
echo.
pause
endlocal
exit /b 0

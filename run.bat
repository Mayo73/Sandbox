@echo off
setlocal EnableExtensions
title Start
color 0A

echo.
echo   ============================================================
echo   ==                      S T A R T                        ==
echo   ============================================================
echo.
echo   Der Vorgang wird neu gestartet...
echo.

:: ------------------------------------------------------------
:: Hier kommt deine eigene Logik fuer "Start" hinein.
:: Beispiel:
:: ------------------------------------------------------------
echo   [Schritt 1] Initialisiere...
timeout /t 1 >nul
echo   [Schritt 2] Lege neue Sitzung an...
timeout /t 1 >nul
echo   [Schritt 3] Vorgang laeuft.
echo.

echo   Fertig. Dieses Fenster kann geschlossen werden.
echo.
pause
endlocal
exit /b 0

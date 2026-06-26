@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Batch Steuerung - Hauptmenue
color 0B

:: ============================================================
::  Verzeichnis dieser Datei (damit es von ueberall startet)
:: ============================================================
set "BASE=%~dp0"

:menu
cls
echo.
echo   ============================================================
echo   ==                                                        ==
echo   ==              B A T C H   S T E U E R U N G             ==
echo   ==                                                        ==
echo   ============================================================
echo.
echo      Bitte waehle eine Option:
echo.
echo        [1]  Start        -  startet den Vorgang neu
echo        [2]  Fortsetzen   -  setzt den Vorgang fort
echo.
echo        [0]  Beenden
echo.
echo   ------------------------------------------------------------
echo.

set "choice="
set /p "choice=   Deine Auswahl:  "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto resume
if "%choice%"=="0" goto ende

echo.
echo   [!] Ungueltige Eingabe - bitte 1, 2 oder 0 waehlen.
echo.
pause
goto menu

:: ============================================================
::  Option 1 - Start (oeffnet start.bat in neuem Fenster)
:: ============================================================
:start
if not exist "%BASE%start.bat" (
    echo.
    echo   [!] Datei nicht gefunden: %BASE%start.bat
    echo.
    pause
    goto menu
)
echo.
echo   Starte "Start" in einem neuen Fenster...
start "Start" cmd /k "%BASE%start.bat"
timeout /t 1 >nul
goto menu

:: ============================================================
::  Option 2 - Fortsetzen (oeffnet resume.bat in neuem Fenster)
:: ============================================================
:resume
if not exist "%BASE%resume.bat" (
    echo.
    echo   [!] Datei nicht gefunden: %BASE%resume.bat
    echo.
    pause
    goto menu
)
echo.
echo   Starte "Fortsetzen" in einem neuen Fenster...
start "Fortsetzen" cmd /k "%BASE%resume.bat"
timeout /t 1 >nul
goto menu

:: ============================================================
::  Beenden
:: ============================================================
:ende
cls
echo.
echo   Auf Wiedersehen!
echo.
timeout /t 1 >nul
endlocal
exit /b 0

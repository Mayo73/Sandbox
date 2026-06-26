@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AUTO LV 2.0 - Hauptmenue

:: ============================================================
::  Verzeichnis dieser Datei (damit es von ueberall startet)
:: ============================================================
set "BASE=%~dp0"

:: ============================================================
::  ANSI-Farben aktivieren (weisse Schrift, gruener Cursor)
:: ============================================================
for /f %%E in ('echo prompt $E ^| cmd') do set "ESC=%%E"
set "WHITE=%ESC%[97m"
set "GREEN=%ESC%[92m"
set "GRAY=%ESC%[90m"
set "RESET=%ESC%[0m"

:: schwarzer Hintergrund, weisse Standardschrift
color 0F

set "sel=0"
set "count=4"

:: ============================================================
::  Menue zeichnen
:: ============================================================
:draw
cls
echo(
echo   %WHITE%============================================================%RESET%
echo   %WHITE%==                    A U T O   L V   2 . 0              ==%RESET%
echo   %WHITE%============================================================%RESET%
echo(
echo   %GRAY%Pfeiltasten Hoch/Runter zum Waehlen  -  Enter zum Bestaetigen%RESET%
echo(
call :line 0 "Start                          -  startet den Vorgang neu"
call :line 1 "Ueberspringen und Fortsetzen   -  ueberspringe letzte Mappe und setze fort"
call :line 2 "Fortsetzen                     -  ohne zu Ueberspringen"
call :line 3 "Beenden"
echo(

:: ---- Taste einlesen (U=Hoch, D=Runter, E=Enter) ----
for /f "delims=" %%K in ('powershell -NoProfile -Command "switch([Console]::ReadKey($true).Key){'UpArrow'{'U'};'DownArrow'{'D'};'Enter'{'E'};default{'X'}}"') do set "KEY=%%K"

if "!KEY!"=="U" set /a sel=(sel+count-1) %% count & goto draw
if "!KEY!"=="D" set /a sel=(sel+1) %% count & goto draw
if "!KEY!"=="E" goto select
goto draw

:: ---- eine Menuezeile zeichnen (markiert = gruener Cursor) ----
:line
if "%~1"=="!sel!" (
    echo     %GREEN%^>%RESET% %WHITE%%~2%RESET%
) else (
    echo       %WHITE%%~2%RESET%
)
goto :eof

:: ============================================================
::  Auswahl auswerten
:: ============================================================
:select
if "!sel!"=="0" goto start
if "!sel!"=="1" goto skip
if "!sel!"=="2" goto resume
if "!sel!"=="3" goto ende
goto draw

:: ============================================================
::  Option 1 - Start (oeffnet run.bat in neuem Fenster)
:: ============================================================
:start
if not exist "%BASE%run.bat" (
    cls
    echo(
    echo   %WHITE%[!] Datei nicht gefunden: %BASE%run.bat%RESET%
    echo(
    pause
    goto draw
)
start "Start" cmd /k "%BASE%run.bat"
goto draw

:: ============================================================
::  Option 2 - Ueberspringen und Fortsetzen (oeffnet skip.bat)
:: ============================================================
:skip
if not exist "%BASE%skip.bat" (
    cls
    echo(
    echo   %WHITE%[!] Datei nicht gefunden: %BASE%skip.bat%RESET%
    echo(
    pause
    goto draw
)
start "Ueberspringen und Fortsetzen" cmd /k "%BASE%skip.bat"
goto draw

:: ============================================================
::  Option 3 - Fortsetzen (oeffnet continue.bat in neuem Fenster)
:: ============================================================
:resume
if not exist "%BASE%continue.bat" (
    cls
    echo(
    echo   %WHITE%[!] Datei nicht gefunden: %BASE%continue.bat%RESET%
    echo(
    pause
    goto draw
)
start "Fortsetzen" cmd /k "%BASE%continue.bat"
goto draw

:: ============================================================
::  Beenden
:: ============================================================
:ende
cls
echo(
echo   %WHITE%Auf Wiedersehen!%RESET%
echo(
timeout /t 1 >nul
endlocal
exit /b 0

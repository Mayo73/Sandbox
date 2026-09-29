@echo off
REM Startet die Copilot-Bridge. Doppelklick genuegt.
setlocal
cd /d "%~dp0"

where py >nul 2>&1 && (set PY=py -3) || (set PY=python)

if not exist "config.toml" (
    echo Keine config.toml gefunden - lege sie aus der Vorlage an.
    %PY% run_bridge.py init
    echo.
    echo Bitte config.toml pruefen ^(vor allem allowed_roots^) und neu starten.
    pause
    exit /b 0
)

%PY% run_bridge.py run %*
echo.
pause

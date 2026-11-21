@echo off
REM ============================================================
REM  Proteus-Pairing-MK1 Offline-Build-Kit v1.1.0
REM  Schritt 3 von 3 - auf dem Windows-10-PC ausfuehren, NACHDEM
REM  Schritt 2 (Pakete installieren) einmal erfolgreich lief.
REM
REM  Quelle des Projekts (in dieser Reihenfolge):
REM   a) genau EINE Proteus-Pairing-MK1-.zip neben diesem Skript
REM      -> wird nach "projekt" entpackt
REM   b) sonst: der Projektordner, in dem dieses Kit liegt
REM      (..\Proteus-Pairing-MK1.spec)
REM
REM  Baut mit PyInstaller (aus der venv von Schritt 2) ueber die
REM  Spec-Datei des Projekts - genau wie der GitHub-Actions-Workflow:
REM     Proteus-Pairing-MK1-v<Version>-windows.exe
REM  (eine einzelne exe, ohne Konsolenfenster). Komplett offline.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"
set "KITDIR=%~dp0"
set "EXEBASE=Proteus-Pairing-MK1"
set "SPECNAME=Proteus-Pairing-MK1.spec"

echo.
echo === Proteus-Pairing-MK1 Offline-Build-Kit v1.1.0 ===
echo === Schritt 3: exe bauen ===
echo.

if not exist "venv\Scripts\pyinstaller.exe" (
    echo [FEHLER] venv mit PyInstaller wurde nicht gefunden.
    echo Bitte zuerst "2_win10_pakete_installieren.bat" erfolgreich
    echo ausfuehren ^(im selben Ordner wie dieses Skript^).
    pause
    exit /b 1
)

REM --- .zip-Dateien in diesem Ordner zaehlen ---
set "ZIPFILE="
set /a ZIPCOUNT=0
for %%f in ("*.zip") do (
    set "ZIPFILE=%%f"
    set /a ZIPCOUNT+=1
)
if %ZIPCOUNT% GTR 1 (
    echo [FEHLER] Es liegen mehrere .zip-Dateien in diesem Ordner:
    for %%f in ("*.zip") do echo    - %%f
    echo Bitte nur die gewuenschte Projekt-.zip-Datei hier ablegen.
    pause
    exit /b 1
)

set "SPECFILE="
if %ZIPCOUNT%==1 (
    echo Quelle: Archiv !ZIPFILE!
    echo.
    echo [1/3] Entpacke !ZIPFILE! nach "projekt" ...
    if exist "projekt" rmdir /s /q "projekt"
    mkdir "projekt"
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '!ZIPFILE!' -DestinationPath 'projekt' -Force"
    if errorlevel 1 (
        echo [FEHLER] Entpacken fehlgeschlagen.
        pause
        exit /b 1
    )
    for /f "delims=" %%f in ('dir /s /b "projekt\!SPECNAME!" 2^>nul') do (
        if not defined SPECFILE set "SPECFILE=%%f"
    )
    if not defined SPECFILE (
        echo.
        echo [FEHLER] In der .zip-Datei wurde keine !SPECNAME! gefunden.
        echo Ist das wirklich das Proteus-Pairing-MK1-Projekt? Gefundener Inhalt:
        dir /b "projekt"
        pause
        exit /b 1
    )
) else (
    echo [1/3] Keine .zip neben dem Skript - nutze den Projektordner ...
    if exist "..\!SPECNAME!" (
        for %%s in ("..\!SPECNAME!") do set "SPECFILE=%%~fs"
        echo Quelle: Projektordner
    ) else (
        echo [FEHLER] Weder eine Projekt-.zip neben diesem Skript noch
        echo "..\!SPECNAME!" gefunden.
        echo Entweder die Proteus-Pairing-MK1-.zip neben die Skripte legen
        echo oder das Kit im Projektordner lassen ^(Ordner offline_build_kit^).
        pause
        exit /b 1
    )
)
for %%d in ("!SPECFILE!") do set "APPDIR=%%~dpd"
echo Projektordner: !APPDIR!

if not exist "!APPDIR!main.py" (
    echo [FEHLER] main.py fehlt im Projektordner - Projekt unvollstaendig.
    pause
    exit /b 1
)
if not exist "!APPDIR!app\config.py" (
    echo [FEHLER] app\config.py fehlt im Projektordner - Projekt unvollstaendig.
    pause
    exit /b 1
)

REM --- Versionsnummer aus APP_VERSION in app\config.py lesen ---
set "APPVER="
for /f "usebackq delims=" %%v in (`venv\Scripts\python.exe -c "import re,sys;m=re.search(r'^APP_VERSION\s*=\s*[\x22\x27]([0-9A-Za-z.\-]+)',open(sys.argv[1],encoding='utf-8').read(),re.M);print(m.group(1) if m else '')" "!APPDIR!app\config.py"`) do set "APPVER=%%v"
if not defined APPVER (
    echo [WARNUNG] Keine APP_VERSION in app\config.py gefunden - nutze "0.0.0".
    set "APPVER=0.0.0"
)
set "EXENAME=!EXEBASE!-v!APPVER!-windows"
echo Version: !APPVER!

echo.
echo [2/3] Pruefe die venv ^(PySide6, bleak, winrt^) ...
venv\Scripts\python.exe -c "import PySide6.QtWidgets, bleak, winrt.windows.devices.bluetooth" >nul 2>nul
if errorlevel 1 (
    echo [FEHLER] PySide6, bleak oder winrt fehlt in der venv. Bitte Schritt 2 erneut ausfuehren.
    pause
    exit /b 1
)
echo    venv ok

if not exist "fertige_exe" mkdir "fertige_exe"
if exist "fertige_exe\!EXENAME!.exe" del /q "fertige_exe\!EXENAME!.exe"

echo.
echo [3/3] Baue !EXENAME!.exe ^(dauert 1-3 Minuten^) ...
REM Gebaut wird im Projektordner mit der Spec-Datei (wie im
REM GitHub-Workflow); Ausgabe und Zwischendateien landen im Kit-Ordner.
pushd "!APPDIR!"
"!KITDIR!venv\Scripts\pyinstaller.exe" --noconfirm --clean ^
    --distpath "!KITDIR!build_tmp\dist" --workpath "!KITDIR!build_tmp\work" ^
    "!SPECFILE!"
set "PYIERR=!errorlevel!"
popd
if not "!PYIERR!"=="0" (
    echo [FEHLER] Build von !EXENAME!.exe fehlgeschlagen.
    pause
    exit /b 1
)
if not exist "build_tmp\dist\!EXEBASE!.exe" (
    echo [FEHLER] PyInstaller lief durch, aber die exe fehlt.
    pause
    exit /b 1
)
move /y "build_tmp\dist\!EXEBASE!.exe" "fertige_exe\!EXENAME!.exe" >nul

REM Aufraeumen der PyInstaller-Zwischendateien
if exist "build_tmp" rmdir /s /q "build_tmp"

echo.
echo ============================================================
echo  FERTIG!
echo.
echo  Im Ordner
echo    %~dp0fertige_exe
echo  liegt jetzt:
dir /b "fertige_exe"
echo.
echo  Die exe ist eigenstaendig ^(keine weiteren Dateien noetig^).
echo  Bluetooth am PC einschalten und die exe starten.
echo ============================================================
echo.
pause

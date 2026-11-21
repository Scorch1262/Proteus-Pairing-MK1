#!/bin/bash
# ============================================================
#  Proteus-Pairing-MK1 Offline-Build-Kit v1.1.0
#  Schritt 3 von 3 (macOS) - auf dem Offline-Mac ausfuehren, NACHDEM
#  Schritt 2 (2_mac_pakete_installieren.sh) einmal erfolgreich lief.
#
#  Quelle des Projekts (in dieser Reihenfolge):
#   a) genau EINE Proteus-Pairing-MK1-.zip neben diesem Skript
#      -> wird nach "projekt_mac" entpackt
#   b) sonst: der Projektordner, in dem dieses Kit liegt
#      (../Proteus-Pairing-MK1.spec)
#
#  Baut mit PyInstaller (aus venv_mac) ueber die Spec-Datei des
#  Projekts - genau wie der GitHub-Actions-Workflow:
#     fertige_app/Proteus-Pairing-MK1.app
#     fertige_app/Proteus-Pairing-MK1-v<Version>-macOS.zip
#  Komplett offline.
#
#  Aufruf im Terminal:   bash 3_mac_app_bauen.sh
# ============================================================

set -e
cd "$(dirname "$0")"
KITDIR="$(pwd)"
APPNAME="Proteus-Pairing-MK1"
SPECNAME="${APPNAME}.spec"

fehler() { echo; echo "[FEHLER] $*"; echo; exit 1; }

echo
echo "=== Proteus-Pairing-MK1 Offline-Build-Kit v1.1.0 ==="
echo "=== Schritt 3 (macOS): App bauen ==="
echo

[ "$(uname -s)" = "Darwin" ] || fehler "Dieses Skript ist fuer macOS. Unter Windows: 3_win10_exe_bauen.bat"
[ -x "venv_mac/bin/pyinstaller" ] || fehler "venv_mac mit PyInstaller wurde nicht gefunden.
Bitte zuerst \"bash 2_mac_pakete_installieren.sh\" erfolgreich ausfuehren
(im selben Ordner wie dieses Skript)."

# --- .zip-Dateien in diesem Ordner zaehlen ---
shopt -s nullglob
ZIPS=( *.zip )
shopt -u nullglob
if [ "${#ZIPS[@]}" -gt 1 ]; then
    echo "[FEHLER] Es liegen mehrere .zip-Dateien in diesem Ordner:"
    for z in "${ZIPS[@]}"; do echo "   - $z"; done
    fehler "Bitte nur die gewuenschte Projekt-.zip-Datei hier ablegen."
fi

SPECFILE=""
if [ "${#ZIPS[@]}" -eq 1 ]; then
    echo "Quelle: Archiv ${ZIPS[0]}"
    echo
    echo "[1/3] Entpacke ${ZIPS[0]} nach \"projekt_mac\" ..."
    rm -rf projekt_mac
    mkdir projekt_mac
    unzip -q "${ZIPS[0]}" -d projekt_mac || fehler "Entpacken fehlgeschlagen."
    SPECFILE=$(find projekt_mac -name "$SPECNAME" -type f | head -n 1)
    if [ -z "$SPECFILE" ]; then
        echo "[FEHLER] In der .zip-Datei wurde keine $SPECNAME gefunden."
        echo "Ist das wirklich das ${APPNAME}-Projekt? Gefundener Inhalt:"
        ls projekt_mac
        exit 1
    fi
    SPECFILE="$KITDIR/$SPECFILE"
else
    echo "[1/3] Keine .zip neben dem Skript - nutze den Projektordner ..."
    [ -f "../$SPECNAME" ] || fehler "Weder eine Projekt-.zip neben diesem Skript noch \"../$SPECNAME\" gefunden.
Entweder die ${APPNAME}-.zip neben die Skripte legen oder das Kit im
Projektordner lassen (Ordner offline_build_kit)."
    SPECFILE="$(cd .. && pwd)/$SPECNAME"
    echo "Quelle: Projektordner"
fi
APPDIR="$(dirname "$SPECFILE")"
echo "Projektordner: $APPDIR"
[ -f "$APPDIR/main.py" ]       || fehler "main.py fehlt im Projektordner - Projekt unvollstaendig."
[ -f "$APPDIR/app/config.py" ] || fehler "app/config.py fehlt im Projektordner - Projekt unvollstaendig."

# --- Versionsnummer aus APP_VERSION lesen ---
APPVER=$(sed -n 's/^APP_VERSION *= *["'\'']\([0-9A-Za-z.-]*\)["'\''].*/\1/p' "$APPDIR/app/config.py" | head -n 1)
if [ -z "$APPVER" ]; then
    echo "[WARNUNG] Keine APP_VERSION in app/config.py gefunden - nutze 0.0.0"
    APPVER="0.0.0"
fi
echo "Version: $APPVER"

echo
echo "[2/3] Pruefe die venv (PySide6, bleak, pyobjc) ..."
venv_mac/bin/python -c "import PySide6.QtWidgets, bleak, CoreBluetooth" >/dev/null 2>&1 \
    || fehler "PySide6, bleak oder pyobjc fehlt in venv_mac. Bitte Schritt 2 erneut ausfuehren."
echo "   venv ok"

echo
echo "[3/3] Baue ${APPNAME}.app (dauert 1-3 Minuten) ..."
rm -rf build_tmp_mac
( cd "$APPDIR" && "$KITDIR/venv_mac/bin/pyinstaller" --noconfirm --clean \
      --distpath "$KITDIR/build_tmp_mac/dist" --workpath "$KITDIR/build_tmp_mac/work" \
      "$SPECFILE" ) || fehler "Build der App fehlgeschlagen."
BUILT="build_tmp_mac/dist/${APPNAME}.app"
[ -d "$BUILT" ] || fehler "PyInstaller lief durch, aber die .app fehlt."

# Ad-hoc signieren (noetig auf Apple Silicon) und Quarantaene-Attribute entfernen
xattr -cr "$BUILT" 2>/dev/null || true
codesign --force --deep --sign - "$BUILT" >/dev/null 2>&1 \
    || echo "[HINWEIS] Ad-hoc-Signatur nicht moeglich - App laesst sich ggf. erst per Rechtsklick > Oeffnen starten."

mkdir -p fertige_app
rm -rf "fertige_app/${APPNAME}.app"
mv "$BUILT" "fertige_app/${APPNAME}.app"
ZIPOUT="fertige_app/${APPNAME}-v${APPVER}-macOS.zip"
rm -f "$ZIPOUT"
ditto -c -k --sequesterRsrc --keepParent "fertige_app/${APPNAME}.app" "$ZIPOUT"

# Aufraeumen der PyInstaller-Zwischendateien
rm -rf build_tmp_mac

echo
echo "============================================================"
echo " FERTIG!"
echo
echo " Im Ordner"
echo "   $KITDIR/fertige_app"
echo " liegt jetzt:"
ls -1 fertige_app | sed 's/^/   /'
echo
echo " Die .app per Doppelklick starten (beim ersten Start ggf."
echo " Rechtsklick > Oeffnen) und den Bluetooth-Zugriff erlauben."
echo " Die .zip ist zum Weitergeben an andere Macs gedacht."
echo "============================================================"
echo

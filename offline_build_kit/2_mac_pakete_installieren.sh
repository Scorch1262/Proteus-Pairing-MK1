#!/bin/bash
# ============================================================
#  Proteus-Pairing-MK1 Offline-Build-Kit v1.1.0
#  Schritt 2 von 3 (macOS) - auf dem OFFLINE-Mac ausfuehren.
#  Python 3 (passende Version, siehe unten) muss installiert sein.
#
#  Installiert PySide6/bleak/pyobjc/pyinstaller komplett OFFLINE
#  aus dem Ordner "offline_pakete_mac" (aus Schritt 1) in eine neue
#  virtuelle Umgebung "venv_mac". Kein Internetzugriff noetig.
#
#  Aufruf im Terminal:   bash 2_mac_pakete_installieren.sh
# ============================================================

set -e
cd "$(dirname "$0")"
DIR="offline_pakete_mac"

fehler() { echo; echo "[FEHLER] $*"; echo; exit 1; }

echo
echo "=== Proteus-Pairing-MK1 Offline-Build-Kit v1.1.0 ==="
echo "=== Schritt 2 (macOS): Pakete offline installieren ==="
echo

[ "$(uname -s)" = "Darwin" ] || fehler "Dieses Skript ist fuer macOS. Unter Windows: 2_win10_pakete_installieren.bat"
[ -f "$DIR/python_version.txt" ] || fehler "Ordner \"$DIR\" fehlt oder ist unvollstaendig.
Bitte zuerst auf dem Mac mit Internet \"1_mac_pakete_herunterladen.sh\"
ausfuehren (ohne Parameter oder mit \"mac\") und den Ordner hierher kopieren."
[ -f "paketliste.txt" ] || fehler "\"paketliste.txt\" fehlt - sie entsteht in Schritt 1."

PYVER=$(tr -d '[:space:]' < "$DIR/python_version.txt")
ARCH=$(tr -d '[:space:]' < "$DIR/arch.txt" 2>/dev/null || echo arm64)
echo "Pakete sind fuer: Python ${PYVER}, Prozessor ${ARCH}, macOS ab 14"

# --- macOS-Version pruefen (PySide6 6.12 braucht macOS 14+) ---
OSV=$(sw_vers -productVersion)
OSMAJOR=${OSV%%.*}
echo "Dieser Mac: macOS ${OSV}, Prozessor $(uname -m)"
if [ "$OSMAJOR" -lt 14 ]; then
    fehler "macOS ${OSV} ist zu alt - die Pakete (PySide6 6.12) brauchen macOS 14 (Sonoma) oder neuer."
fi

# --- passendes Python suchen ---
PYCMD=""
for c in "python${PYVER}" \
         "/Library/Frameworks/Python.framework/Versions/${PYVER}/bin/python3" \
         "/opt/homebrew/bin/python${PYVER}" "/usr/local/bin/python${PYVER}" \
         "python3"; do
    if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
        if "$c" -c "import sys,platform;v='%d.%d'%sys.version_info[:2];sys.exit(0 if v=='${PYVER}' and platform.machine()=='${ARCH}' else 1)" 2>/dev/null; then
            PYCMD="$c"
            break
        fi
    fi
done
if [ -z "$PYCMD" ]; then
    echo "[FEHLER] Kein passendes Python ${PYVER} (${ARCH}) gefunden."
    echo "Gefunden wurde:"
    for c in python3 python3.10 python3.11 python3.12 python3.13 python3.14; do
        command -v "$c" >/dev/null 2>&1 && echo "   $c -> $("$c" -c 'import sys,platform;print("%d.%d"%sys.version_info[:2], platform.machine())')"
    done
    echo
    echo "Loesung: entweder Python ${PYVER} installieren (Installer von python.org"
    echo "auf dem Mac mit Internet herunterladen und mitbringen), oder in"
    echo "1_mac_pakete_herunterladen.sh oben MAC_PY_VER / MAC_ARCH auf dieses"
    echo "Python einstellen und Schritt 1 wiederholen."
    exit 1
fi
echo "Verwende: $PYCMD ($("$PYCMD" --version))"

echo
echo "[1/4] Pruefe die Pakete auf Vollstaendigkeit (SHA256)..."
if [ -f "$DIR/SHA256SUMS.txt" ]; then
    if ! ( cd "$DIR" && shasum -a 256 -c SHA256SUMS.txt --quiet ); then
        fehler "Mindestens ein Paket ist beim Kopieren beschaedigt worden oder fehlt.
Bitte den Ordner \"$DIR\" erneut kopieren."
    fi
    echo "   alle Pakete in Ordnung"
else
    echo "   (keine Pruefsummen-Datei vorhanden, ueberspringe)"
fi

echo
echo "[2/4] Lege virtuelle Umgebung \"venv_mac\" an (falls noch nicht vorhanden)..."
if [ ! -x "venv_mac/bin/python" ]; then
    "$PYCMD" -m venv venv_mac || fehler "Anlegen der virtuellen Umgebung fehlgeschlagen."
else
    echo "   (existiert bereits, ueberspringe)"
fi

echo
echo "[3/4] Installiere Pakete rein aus \"$DIR\""
echo "      (--no-index = es wird NICHTS aus dem Internet geladen)..."
if ! venv_mac/bin/python -m pip install --no-index --find-links="$DIR" -r paketliste.txt; then
    fehler "Installation fehlgeschlagen.
Haeufigste Ursache: die .whl-Dateien passen nicht zur Python-Version
oder zum Prozessor der venv. Dann den Ordner \"venv_mac\" loeschen,
ggf. Schritt 1 mit passenden MAC_PY_VER/MAC_ARCH wiederholen."
fi

echo
echo "[4/4] Pruefe, ob alle Module importierbar sind ..."
venv_mac/bin/python -c "import PySide6.QtWidgets, bleak, objc, CoreBluetooth, PyInstaller; print('   PySide6', PySide6.__version__, '/ bleak / pyobjc / PyInstaller', PyInstaller.__version__, 'ok')" \
    || fehler "Mindestens ein Modul fehlt in der venv. Schritt 1 wiederholen und erneut kopieren."

echo
echo "============================================================"
echo " FERTIG. PySide6, bleak (mit pyobjc/CoreBluetooth) und"
echo " PyInstaller stecken jetzt in \"venv_mac\" in diesem Ordner."
echo
echo " Naechster Schritt:   bash 3_mac_app_bauen.sh"
echo " (Entweder liegt das Kit im Projektordner, oder die"
echo "  Proteus-Pairing-MK1-.zip liegt neben den Skripten.)"
echo "============================================================"
echo

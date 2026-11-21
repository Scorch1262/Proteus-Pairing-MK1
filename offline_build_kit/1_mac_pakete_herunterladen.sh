#!/bin/bash
# ============================================================
#  Proteus-Pairing-MK1 Offline-Build-Kit v1.0.0
#  Schritt 1 von 3 - auf dem MAC mit Internetverbindung ausfuehren.
#
#  Laedt alle fuer den Windows-Build benoetigten Python-Pakete
#  (PySide6-Essentials, bleak + winrt, pyinstaller + Abhaengigkeiten)
#  als fertige .whl-Dateien fuer 64-Bit-Windows / Python 3.11
#  herunter. Auf dem Mac selbst wird nichts installiert.
#
#  Ergebnis liegt im Ordner "offline_pakete" daneben.
#  Danach: diesen ganzen Ordner (bzw. den ganzen Projektordner,
#  in dem dieses Kit liegt) per USB-Stick/Kabel auf den Win10-PC
#  kopieren.
# ============================================================

set -e
cd "$(dirname "$0")"

KIT_VERSION="1.0.0"
PROJECT="Proteus-Pairing-MK1"
SPEC="${PROJECT}.spec"
# Python-Version des Windows-10-PCs (Major.Minor)
PY_VER="3.11"
PY_TAG="${PY_VER/./}"            # 3.11 -> 311

# Standardwerte (wie requirements.txt / GitHub-Actions-Build)
DEFAULT_REQS="PySide6-Essentials==6.12.0
bleak==3.1.0"
DEFAULT_PYINSTALLER="pyinstaller==6.22.3"

echo
echo "=== ${PROJECT} Offline-Build-Kit v${KIT_VERSION} ==="
echo "=== Schritt 1: Pakete fuer Windows 10 / Python ${PY_VER} herunterladen ==="
echo

# Python3 finden (nur als Download-Werkzeug, Version egal)
PYTHON=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYTHON="$cand"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "[FEHLER] Es wurde kein Python auf diesem Mac gefunden."
    echo "Bitte einmalig installieren, z. B. mit:  brew install python"
    echo "(oder von https://www.python.org/downloads/macos/)"
    exit 1
fi
echo "Verwende: $($PYTHON --version) ($PYTHON)"

# ------------------------------------------------------------
# Paketliste bestimmen (in dieser Reihenfolge):
#  1. Projekt-.zip neben diesem Skript (enthaelt ${SPEC})
#     -> requirements.txt daneben
#  2. Kit liegt im Projektordner (../${SPEC}) -> ../requirements.txt
#  3. Standardliste
# ------------------------------------------------------------
PROJ_REQS=""
for z in *.zip; do
    [ -f "$z" ] || continue
    SPEC_IN_ZIP=$(unzip -Z1 "$z" 2>/dev/null | grep -E "(^|/)${SPEC}\$" | head -n 1 || true)
    [ -n "$SPEC_IN_ZIP" ] || continue
    REQ_IN_ZIP="$(dirname "$SPEC_IN_ZIP")/requirements.txt"
    REQ_IN_ZIP="${REQ_IN_ZIP#./}"
    PROJ_REQS=$(unzip -p "$z" "$REQ_IN_ZIP" 2>/dev/null | tr -d '\r' | sed 's/#.*//' | grep -v '^[[:space:]]*$' || true)
    if [ -n "$PROJ_REQS" ]; then
        echo "Projekt-Archiv gefunden: $z  -> nutze dessen requirements.txt"
    fi
    break
done
if [ -z "$PROJ_REQS" ] && [ -f "../${SPEC}" ] && [ -f "../requirements.txt" ]; then
    PROJ_REQS=$(tr -d '\r' < ../requirements.txt | sed 's/#.*//' | grep -v '^[[:space:]]*$' || true)
    [ -n "$PROJ_REQS" ] && echo "Kit liegt im Projektordner -> nutze ../requirements.txt"
fi
if [ -z "$PROJ_REQS" ]; then
    PROJ_REQS="$DEFAULT_REQS"
    echo "Keine Projekt-requirements.txt gefunden - nutze Standardliste"
fi

REQ_FILE="paketliste.txt"
{
    echo "$PROJ_REQS"
    echo "$DEFAULT_PYINSTALLER"
} > "$REQ_FILE"
echo "Paketliste ($REQ_FILE):"
sed 's/^/   /' "$REQ_FILE"

rm -rf offline_pakete
mkdir -p offline_pakete
echo "$PY_VER" > offline_pakete/python_version.txt

echo
echo "Aktualisiere pip (falls moeglich)..."
"$PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null \
    || echo "   (pip-Aktualisierung uebersprungen - kein Problem)"

PIP_TARGET=(--platform win_amd64 --python-version "$PY_TAG" --implementation cp
            --abi "cp$PY_TAG" --abi abi3 --abi none --only-binary=:all: --no-deps)

# WICHTIG: "pip download --platform win_amd64" waehlt zwar korrekt
# Windows-Wheels aus, wertet bedingte Abhaengigkeiten (z. B.
# "sys_platform == 'win32'" oder "python_version < '3.12'") aber
# anhand DIESES Macs aus (bleak wuerde z. B. pyobjc fuer macOS
# verlangen, das es fuer Windows gar nicht gibt).
# Deshalb wird mit --no-deps geladen und die Abhaengigkeiten danach
# von einem kleinen Resolver fuer Windows/Python ${PY_VER} ergaenzt.
# Betroffen sind hier u. a.:
#  - bleak     -> winrt-runtime + winrt-windows-* (Bluetooth unter Windows)
#  - bleak     -> typing-extensions (Python < 3.12)
#  - PyInstaller -> pefile, pywin32-ctypes
# Die bekannten Pakete werden zusaetzlich explizit geladen.
cp "$REQ_FILE" offline_pakete_reqs_wheel.txt
{
    echo "pefile>=2022.5.30"
    echo "pywin32-ctypes>=0.2.0"
    echo "typing-extensions>=4.7.0"
    echo "winrt-runtime>=3.1"
    echo "winrt-windows-devices-bluetooth>=3.1"
    echo "winrt-windows-devices-bluetooth-advertisement>=3.1"
    echo "winrt-windows-devices-bluetooth-genericattributeprofile>=3.1"
    echo "winrt-windows-devices-enumeration>=3.1"
    echo "winrt-windows-devices-radios>=3.1"
    echo "winrt-windows-foundation>=3.1"
    echo "winrt-windows-foundation-collections>=3.1"
    echo "winrt-windows-storage-streams>=3.1"
} >> offline_pakete_reqs_wheel.txt

echo
echo "Lade fertige Wheels herunter (Ziel: Windows 64-Bit, Python ${PY_VER})..."
echo "(PySide6 ist gross, ca. 100 MB - je nach Leitung einige Minuten)"
"$PYTHON" -m pip download -r offline_pakete_reqs_wheel.txt -d offline_pakete "${PIP_TARGET[@]}"
rm -f offline_pakete_reqs_wheel.txt

echo
echo "Pruefe Abhaengigkeiten mit Windows-Bedingungen nach..."
RESOLVER="$(mktemp "${TMPDIR:-/tmp}/ppm_resolver.XXXXXX")"
cat > "$RESOLVER" <<'PYEOF'
import glob, os, subprocess, sys, zipfile
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename

dest, pyver = sys.argv[1], sys.argv[2]
pip_args = sys.argv[3:]
env = {
    "sys_platform": "win32", "platform_system": "Windows", "os_name": "nt",
    "platform_machine": "AMD64", "platform_release": "10", "platform_version": "10.0",
    "python_version": pyver, "python_full_version": pyver + ".0",
    "implementation_name": "cpython", "implementation_version": pyver + ".0",
    "platform_python_implementation": "CPython", "extra": "",
}
for _ in range(10):
    wheels = glob.glob(os.path.join(dest, "*.whl"))
    have = {canonicalize_name(parse_wheel_filename(os.path.basename(w))[0]) for w in wheels}
    missing = set()
    for w in wheels:
        with zipfile.ZipFile(w) as z:
            meta = [n for n in z.namelist() if n.endswith(".dist-info/METADATA")]
            if not meta:
                continue
            for line in z.read(meta[0]).decode("utf-8", "replace").splitlines():
                if not line.startswith("Requires-Dist:"):
                    continue
                r = Requirement(line.split(":", 1)[1].strip())
                if r.marker and not r.marker.evaluate(env):
                    continue
                if canonicalize_name(r.name) in have:
                    continue
                extras = "[" + ",".join(sorted(r.extras)) + "]" if r.extras else ""
                missing.add(f"{r.name}{extras}{r.specifier}")
    if not missing:
        print("   alle Abhaengigkeiten vorhanden")
        break
    for m in sorted(missing):
        print("   ergaenze:", m)
    subprocess.check_call([sys.executable, "-m", "pip", "download", *sorted(missing), "-d", dest, *pip_args])
else:
    sys.exit("[FEHLER] Abhaengigkeiten konnten nicht vollstaendig aufgeloest werden.")
PYEOF
"$PYTHON" "$RESOLVER" offline_pakete "$PY_VER" "${PIP_TARGET[@]}" --quiet
rm -f "$RESOLVER"

# Kontrolle: die wichtigsten Pakete muessen dabei sein
# (Dateinamen sind je nach Paket gross- oder kleingeschrieben -> ohne Beachtung)
for pkg in pyside6_essentials shiboken6 bleak winrt_runtime winrt_windows_devices_bluetooth pyinstaller pefile; do
    if ! ls offline_pakete | grep -qi "^${pkg}-.*\.whl$"; then
        echo "[FEHLER] Kein Wheel fuer '${pkg}' heruntergeladen."
        exit 1
    fi
done

# Pruefsummen fuer die Kontrolle auf dem Windows-PC
( cd offline_pakete && shasum -a 256 *.whl > SHA256SUMS.txt 2>/dev/null \
    || sha256sum *.whl > SHA256SUMS.txt )

echo
echo "Heruntergeladen:"
ls -1 offline_pakete | sed 's/^/   /'
du -sh offline_pakete | sed 's/^/   Gesamt: /'

echo
echo "============================================================"
echo " FERTIG. Der Ordner 'offline_pakete' enthaelt jetzt alle"
echo " benoetigten .whl-Dateien fuer Windows/Python ${PY_VER}."
echo
echo " Naechster Schritt: auf den Windows-10-PC kopieren, z. B. per"
echo " USB-Stick - entweder"
echo "   a) den ganzen Projektordner, in dem dieses Kit liegt, oder"
echo "   b) nur diesen Kit-Ordner"
echo "      $(pwd)"
echo "      plus die ${PROJECT}-.zip daneben."
echo "============================================================"
echo

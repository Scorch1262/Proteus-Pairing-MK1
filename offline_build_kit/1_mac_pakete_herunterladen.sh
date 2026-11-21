#!/bin/bash
# ============================================================
#  Proteus-Pairing-MK1 Offline-Build-Kit v1.1.0
#  Schritt 1 von 3 - auf einem MAC mit Internetverbindung ausfuehren.
#
#  Laedt alle fuer den Build benoetigten Python-Pakete
#  (PySide6-Essentials, bleak, pyinstaller + Abhaengigkeiten)
#  als fertige .whl-Dateien herunter - fuer
#    * Windows 64-Bit / Python 3.11          -> offline_pakete/
#    * macOS (ab 14, arm64 oder Intel)        -> offline_pakete_mac/
#  Auf diesem Mac selbst wird nichts installiert.
#
#  Aufruf:
#    ./1_mac_pakete_herunterladen.sh            beide Systeme
#    ./1_mac_pakete_herunterladen.sh windows    nur Windows
#    ./1_mac_pakete_herunterladen.sh mac        nur macOS
#
#  Danach: den ganzen Projektordner (bzw. diesen Kit-Ordner + die
#  Projekt-.zip) per USB-Stick/Kabel auf den Offline-Rechner kopieren.
# ============================================================

set -e
cd "$(dirname "$0")"

KIT_VERSION="1.1.0"
PROJECT="Proteus-Pairing-MK1"
SPEC="${PROJECT}.spec"

# ---- Ziel Windows ------------------------------------------
# Python-Version des Windows-10-PCs (Major.Minor)
WIN_PY_VER="3.11"

# ---- Ziel macOS --------------------------------------------
# Leer lassen = wie dieser Mac (Python-Version bzw. Prozessor).
# Fuer einen ANDEREN Offline-Mac hier eintragen, z. B.
#   MAC_PY_VER="3.12"   MAC_ARCH="x86_64"
MAC_PY_VER=""
MAC_ARCH=""
# PySide6 6.12 gibt es fuer macOS erst ab Version 14 (Sonoma)
MAC_OS_MIN="14_0"

# Standardwerte (wie requirements.txt / GitHub-Actions-Build)
DEFAULT_REQS="PySide6-Essentials==6.12.0
bleak==3.1.0"
DEFAULT_PYINSTALLER="pyinstaller==6.22.3"

ZIEL="${1:-alle}"
case "$ZIEL" in
    alle|windows|mac) ;;
    *) echo "Aufruf: $0 [alle|windows|mac]"; exit 1 ;;
esac

echo
echo "=== ${PROJECT} Offline-Build-Kit v${KIT_VERSION} ==="
echo "=== Schritt 1: Pakete herunterladen (Ziel: ${ZIEL}) ==="
echo

# Python3 finden (nur als Download-Werkzeug)
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

echo
echo "Aktualisiere pip (falls moeglich)..."
"$PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null \
    || echo "   (pip-Aktualisierung uebersprungen - kein Problem)"

# ------------------------------------------------------------
# WICHTIG: "pip download --platform ..." waehlt zwar passende
# Wheels aus, wertet bedingte Abhaengigkeiten (z. B.
# "sys_platform == 'win32'" oder "python_version < '3.12'") aber
# anhand DIESES Macs aus. bleak wuerde fuer Windows sonst pyobjc
# statt winrt verlangen. Deshalb wird mit --no-deps geladen und
# ein kleiner Resolver ergaenzt die Abhaengigkeiten gezielt fuer
# das Zielsystem.
# ------------------------------------------------------------
RESOLVER="$(mktemp "${TMPDIR:-/tmp}/ppm_resolver.XXXXXX")"
trap 'rm -f "$RESOLVER"' EXIT
cat > "$RESOLVER" <<'PYEOF'
import glob, json, os, subprocess, sys, zipfile
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename

dest, env_json = sys.argv[1], sys.argv[2]
pip_args = sys.argv[3:]
env = json.loads(env_json)
for _ in range(12):
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

# Prueft, ob fuer jedes Paket ein Wheel da ist (Dateinamen gross/klein egal)
pruefe_wheels() {
    local dir="$1"; shift
    for pkg in "$@"; do
        if ! ls "$dir" | grep -qi "^${pkg}-.*\.whl$"; then
            echo "[FEHLER] Kein Wheel fuer '${pkg}' in ${dir} heruntergeladen."
            exit 1
        fi
    done
}

pruefsummen() {
    ( cd "$1" && { shasum -a 256 *.whl > SHA256SUMS.txt 2>/dev/null || sha256sum *.whl > SHA256SUMS.txt; } )
}

# ============================================================
#  Windows
# ============================================================
lade_windows() {
    local tag="${WIN_PY_VER/./}"       # 3.11 -> 311
    local dir="offline_pakete"
    echo
    echo "------------------------------------------------------------"
    echo " WINDOWS 64-Bit / Python ${WIN_PY_VER}  -> ${dir}/"
    echo "------------------------------------------------------------"
    rm -rf "$dir"; mkdir -p "$dir"
    echo "$WIN_PY_VER" > "$dir/python_version.txt"
    local args=(--platform win_amd64 --python-version "$tag" --implementation cp
                --abi "cp$tag" --abi abi3 --abi none --only-binary=:all: --no-deps)
    cp "$REQ_FILE" reqs_tmp.txt
    {   # bekannte Windows-Abhaengigkeiten zusaetzlich explizit
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
    } >> reqs_tmp.txt
    echo "Lade Wheels (PySide6 ca. 80 MB - je nach Leitung einige Minuten)..."
    "$PYTHON" -m pip download -r reqs_tmp.txt -d "$dir" "${args[@]}"
    rm -f reqs_tmp.txt
    echo "Pruefe Abhaengigkeiten fuer Windows..."
    local env
    env=$(printf '{"sys_platform":"win32","platform_system":"Windows","os_name":"nt","platform_machine":"AMD64","platform_release":"10","platform_version":"10.0","python_version":"%s","python_full_version":"%s.0","implementation_name":"cpython","implementation_version":"%s.0","platform_python_implementation":"CPython","extra":""}' "$WIN_PY_VER" "$WIN_PY_VER" "$WIN_PY_VER")
    "$PYTHON" "$RESOLVER" "$dir" "$env" "${args[@]}" --quiet
    pruefe_wheels "$dir" pyside6_essentials shiboken6 bleak winrt_runtime winrt_windows_devices_bluetooth \
                         winrt_windows_devices_enumeration pyinstaller pefile
    pruefsummen "$dir"
    du -sh "$dir" | sed 's/^/   Gesamt Windows: /'
}

# ============================================================
#  macOS
# ============================================================
lade_mac() {
    local pyver="$MAC_PY_VER" arch="$MAC_ARCH"
    if [ -z "$pyver" ]; then
        pyver=$("$PYTHON" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
        case "$pyver" in
            3.10|3.11|3.12|3.13|3.14) ;;
            *) echo "   (Python ${pyver} dieses Macs ist ungeeignet - Ziel wird Python 3.12)"; pyver="3.12" ;;
        esac
    fi
    if [ -z "$arch" ]; then
        arch=$(uname -m)
        [ "$arch" = "arm64" ] || [ "$arch" = "x86_64" ] || arch="arm64"
    fi
    local tag="${pyver/./}"
    local dir="offline_pakete_mac"
    echo
    echo "------------------------------------------------------------"
    echo " macOS ab ${MAC_OS_MIN/_/.} / ${arch} / Python ${pyver}  -> ${dir}/"
    echo "------------------------------------------------------------"
    rm -rf "$dir"; mkdir -p "$dir"
    echo "$pyver" > "$dir/python_version.txt"
    echo "$arch"  > "$dir/arch.txt"
    local args=(--platform "macosx_${MAC_OS_MIN}_${arch}" --python-version "$tag" --implementation cp
                --abi "cp$tag" --abi abi3 --abi none --only-binary=:all: --no-deps)
    cp "$REQ_FILE" reqs_tmp.txt
    {   # bekannte macOS-Abhaengigkeiten zusaetzlich explizit
        echo "pyobjc-core>=10.3"
        echo "pyobjc-framework-CoreBluetooth>=10.3"
        echo "pyobjc-framework-libdispatch>=10.3"
        echo "macholib>=1.8"
    } >> reqs_tmp.txt
    echo "Lade Wheels (PySide6 ca. 100 MB - je nach Leitung einige Minuten)..."
    "$PYTHON" -m pip download -r reqs_tmp.txt -d "$dir" "${args[@]}"
    rm -f reqs_tmp.txt
    echo "Pruefe Abhaengigkeiten fuer macOS..."
    local machine="$arch"
    local env
    env=$(printf '{"sys_platform":"darwin","platform_system":"Darwin","os_name":"posix","platform_machine":"%s","platform_release":"23.0.0","platform_version":"","python_version":"%s","python_full_version":"%s.0","implementation_name":"cpython","implementation_version":"%s.0","platform_python_implementation":"CPython","extra":""}' "$machine" "$pyver" "$pyver" "$pyver")
    "$PYTHON" "$RESOLVER" "$dir" "$env" "${args[@]}" --quiet
    pruefe_wheels "$dir" pyside6_essentials shiboken6 bleak pyobjc_core pyobjc_framework_corebluetooth \
                         pyobjc_framework_libdispatch pyinstaller macholib
    pruefsummen "$dir"
    du -sh "$dir" | sed 's/^/   Gesamt macOS: /'
}

if [ "$ZIEL" = "alle" ] || [ "$ZIEL" = "windows" ]; then lade_windows; fi
if [ "$ZIEL" = "alle" ] || [ "$ZIEL" = "mac" ]; then lade_mac; fi

echo
echo "============================================================"
echo " FERTIG."
if [ -d offline_pakete ]; then     echo "   offline_pakete/      -> Windows-PC  (Schritte 2+3: *.bat)"; fi
if [ -d offline_pakete_mac ]; then echo "   offline_pakete_mac/  -> Offline-Mac (Schritte 2+3: *_mac_*.sh)"; fi
echo
echo " Naechster Schritt: auf den Offline-Rechner kopieren, z. B. per"
echo " USB-Stick - entweder"
echo "   a) den ganzen Projektordner, in dem dieses Kit liegt, oder"
echo "   b) nur diesen Kit-Ordner"
echo "      $(pwd)"
echo "      plus die ${PROJECT}-.zip daneben."
echo "============================================================"
echo

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spezifikation für Windows (eine einzelne .exe) und macOS (.app)
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

APP = "Proteus-Pairing-MK1"
VERSION = re.search(r'APP_VERSION = "([^"]+)"', Path("app/config.py").read_text(encoding="utf-8")).group(1)


def bleak_backends(skip):
    return collect_submodules("bleak", filter=lambda name: not any(s in name for s in skip))


if sys.platform == "win32":
    hidden = bleak_backends(("corebluetooth", "bluezdbus", "android")) + collect_submodules("winrt")
    icon = "assets/icon.ico"
elif sys.platform == "darwin":
    hidden = bleak_backends(("winrt", "bluezdbus", "android"))
    icon = "assets/icon.icns"
else:
    hidden = bleak_backends(("winrt", "corebluetooth", "android"))
    icon = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("assets/icon.png", "assets")],
    hiddenimports=hidden,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP, console=False,
              icon=icon, target_arch=None, codesign_identity=None, entitlements_file=None)
    coll = COLLECT(exe, a.binaries, a.datas, name=APP)
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon=icon,
        bundle_identifier="de.proteus-pairing.mk1",
        version=VERSION,
        info_plist={
            "CFBundleName": APP,
            "CFBundleDisplayName": "Proteus Pairing MK1",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",  # PySide6 6.12 braucht macOS 14+
            # Pflicht, sonst beendet macOS das Programm beim ersten Bluetooth-Zugriff
            "NSBluetoothAlwaysUsageDescription":
                "Proteus Pairing benötigt Bluetooth, um Proteus-II-Module zu finden und zu konfigurieren.",
            "NSBluetoothPeripheralUsageDescription":
                "Proteus Pairing benötigt Bluetooth, um Proteus-II-Module zu finden und zu konfigurieren.",
        },
    )
else:
    # Eine einzige .exe ohne daneben liegende Dateien/Ordner (--onefile).
    # Einstellungen/Verlauf landen in %APPDATA%\\Proteus-Pairing-MK1, nicht neben der exe.
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=APP, console=False,
              icon=icon, upx=False, runtime_tmpdir=None)

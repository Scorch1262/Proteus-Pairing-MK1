"""Einstellungen, Pfade und Verlauf von Proteus-Pairing-MK1."""
from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

APP_NAME = "Proteus-Pairing-MK1"
APP_VERSION = "1.0.0"


def data_dir() -> Path:
    """Benutzerverzeichnis für Einstellungen, Verlauf und Protokolle."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(rel: str) -> Path:
    """Pfad zu mitgelieferten Dateien (funktioniert auch in der PyInstaller-exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


LINE_ENDINGS = {
    "Kein Zeilenende": "",
    "CR (\\r)": "\r",
    "LF (\\n)": "\n",
    "CR+LF (\\r\\n)": "\r\n",
}


@dataclass
class Settings:
    # Erkennungsmarken im Gerätenamen (Groß-/Kleinschreibung egal)
    marker_host: str = "Host"
    marker_ptt: str = "PTT"
    # Befehle
    cmd_host_mac: str = "BT-MAC?"
    cmd_ptt_prefix: str = "Host:"
    line_ending: str = "Kein Zeilenende"
    proteus_header: bool = True          # 0x01-Datenheader des Proteus-II-Profils
    # Zeiten
    boot_wait_s: float = 5.0             # "ca. 5 s warten" nach dem Erkennen
    scan_timeout_s: float = 120.0
    response_timeout_s: float = 5.0
    retries: int = 3
    ptt_reply_wait_s: float = 3.0
    # Kopplung
    pair_host: bool = True
    pair_ptt: bool = False
    unpair_after: bool = False
    # Ablauf
    confirm_restart_steps: bool = True   # Schritte 14–17 einzeln bestätigen

    @classmethod
    def load(cls) -> "Settings":
        path = data_dir() / "settings.json"
        s = cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for f in fields(cls):
                if f.name in raw:
                    setattr(s, f.name, type(getattr(s, f.name))(raw[f.name]))
        except Exception:
            pass
        return s

    def save(self) -> None:
        path = data_dir() / "settings.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def line_ending_chars(self) -> str:
        return LINE_ENDINGS.get(self.line_ending, "")


HISTORY_HEADER = ["Zeitpunkt", "Host-Name", "Host-MAC", "PTT-Name", "PTT-Adresse", "Ergebnis"]


def history_path() -> Path:
    return data_dir() / "verlauf.csv"


def append_history(row: list[str]) -> None:
    path = history_path()
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        if new:
            w.writerow(HISTORY_HEADER)
        w.writerow(row)


def load_history(limit: int = 200) -> list[list[str]]:
    path = history_path()
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        return list(reversed(rows[1:]))[:limit]
    except Exception:
        return []


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

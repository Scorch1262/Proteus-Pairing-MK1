# Proteus-Pairing-MK1 — offline bauen: Mac lädt, Windows/Mac baut

**Offline-Build-Kit v1.1.0** · passend zu Proteus-Pairing-MK1 ab v1.2.1

Ein Mac **mit** Internet lädt alle Pakete. Der Rechner **ohne** Internet
installiert sie und baut – mit derselben Spec-Datei wie GitHub Actions:

| Ziel | Ergebnis |
|---|---|
| **Windows** 10/11 | `fertige_exe/Proteus-Pairing-MK1-v<Version>-windows.exe` – eine einzelne exe |
| **macOS** 14+ | `fertige_app/Proteus-Pairing-MK1.app` und `fertige_app/Proteus-Pairing-MK1-v<Version>-macOS.zip` |

```
offline_build_kit/
├── 1_mac_pakete_herunterladen.sh      <- Mac MIT Internet (lädt für Windows + macOS)
├── 2_win10_pakete_installieren.bat    <- Windows-PC (offline)
├── 3_win10_exe_bauen.bat              <- Windows-PC (offline)
├── 2_mac_pakete_installieren.sh       <- Mac OHNE Internet
├── 3_mac_app_bauen.sh                 <- Mac OHNE Internet
└── ANLEITUNG.md                       <- diese Datei
```

Das Kit liegt im Repo im Ordner `offline_build_kit`. Es gibt zwei Wege:

| Weg | Was wird kopiert | Wann sinnvoll |
|---|---|---|
| **A – Projektordner** | der ganze Projektordner (mit `offline_build_kit` darin) | einfachster Weg |
| **B – Kit + ZIP** | nur der Kit-Ordner + die Projekt-`.zip` daneben | neue Version bauen, ohne alles neu zu kopieren |

Der Mac mit Internet und der Offline-Mac dürfen auch **derselbe** Mac sein
(z. B. Pakete laden, solange Internet da ist, und später offline bauen).

---

## Schritt 1 — auf dem Mac mit Internet

1. Projekt-ZIP entpacken (oder Repo klonen). Für Weg B den Ordner
   `offline_build_kit` irgendwohin kopieren und die Projekt-`.zip`
   daneben legen.
2. Terminal öffnen, in den Kit-Ordner wechseln und starten:
   ```bash
   cd ~/Desktop/Proteus-Pairing-MK1/offline_build_kit
   bash 1_mac_pakete_herunterladen.sh            # Windows + macOS
   bash 1_mac_pakete_herunterladen.sh windows    # nur Windows
   bash 1_mac_pakete_herunterladen.sh mac        # nur macOS
   ```
3. Es entstehen
   - **`offline_pakete`** (ca. 85 MB) – Pakete für **Windows 64-Bit /
     Python 3.11**: `PySide6-Essentials`, `bleak` samt `winrt-*`,
     `pyinstaller` und alle Abhängigkeiten,
   - **`offline_pakete_mac`** (ca. 120 MB) – Pakete für **macOS ab 14**:
     `PySide6-Essentials`, `bleak` samt `pyobjc` (CoreBluetooth),
     `pyinstaller` und alle Abhängigkeiten,
   - je eine Prüfsummen-Datei `SHA256SUMS.txt` und die **`paketliste.txt`**.

   Auf dem Mac selbst wird nichts installiert.

   > **Ziel-Mac einstellen:** Ohne Angabe lädt das Skript die Mac-Pakete
   > passend zu **diesem** Mac (Python-Version und Prozessor). Ist der
   > Offline-Mac ein anderer, oben im Skript eintragen, z. B.
   > `MAC_PY_VER="3.12"` und `MAC_ARCH="x86_64"` (Intel) bzw. `"arm64"`
   > (Apple Silicon). Mit `python3 --version` und `uname -m` auf dem
   > Offline-Mac nachsehen.

   > Die Paketliste kommt aus der `requirements.txt` des Projekts
   > (zuerst aus einer `.zip` neben dem Skript, sonst aus dem
   > Projektordner darüber, sonst Standardliste). PyInstaller ist fest
   > auf `6.22.3` gesetzt (wie im GitHub-Workflow).

   > **Warum ein eigener Abhängigkeits-Abgleich?** `pip download` wertet
   > Bedingungen wie `sys_platform == 'win32'` anhand des Macs aus. bleak
   > würde für Windows dann pyobjc statt winrt verlangen. Das Skript lädt
   > deshalb ohne automatische Abhängigkeiten und ergänzt sie danach
   > gezielt für das jeweilige Zielsystem.

**Danach auf den Offline-Rechner kopieren** (USB-Stick, Kabel — egal wie):
- **Weg A:** den kompletten Projektordner (inkl. `offline_build_kit`
  mit `offline_pakete*` und `paketliste.txt`)
- **Weg B:** den Kit-Ordner (inkl. `offline_pakete*` und
  `paketliste.txt`) und die Projekt-`.zip` **im selben Ordner** neben
  den Skripten

---

## Windows — Schritt 2: Pakete installieren

Voraussetzung: Python 3.11 (64-Bit) ist installiert.

1. Doppelklick auf **`2_win10_pakete_installieren.bat`**.
2. Das Skript
   - sucht ein passendes Python 3.11 (64-Bit): erst `python`, sonst
     den Python-Launcher `py -3.11`,
   - prüft per SHA256, dass beim Kopieren keine Paketdatei beschädigt
     wurde,
   - legt die virtuelle Umgebung `venv` an und installiert alle Pakete
     **ausschließlich** aus `offline_pakete` (`--no-index`, kein Internet),
   - prüft, dass PySide6, bleak, winrt und PyInstaller importierbar sind.
3. Am Ende erscheint `FERTIG.`.

## Windows — Schritt 3: exe bauen

1. Doppelklick auf **`3_win10_exe_bauen.bat`**.
2. Quelle: liegt **genau eine** `.zip` neben den Skripten → wird nach
   `projekt` entpackt; sonst wird der Projektordner über dem Kit genommen.
3. Ergebnis: `fertige_exe\Proteus-Pairing-MK1-v<Version>-windows.exe`
   – eine einzige, eigenständige Datei.

---

## macOS — Schritt 2: Pakete installieren

Voraussetzungen auf dem Offline-Mac:
- **macOS 14 (Sonoma) oder neuer** – PySide6 6.12 gibt es für ältere
  macOS-Versionen nicht.
- **Python** in der Version, für die in Schritt 1 geladen wurde (steht
  in `offline_pakete_mac/python_version.txt`). Fehlt es: den Installer
  von python.org auf dem Mac mit Internet herunterladen und mitbringen.
  Gesucht wird `python3.X`, das python.org-Python, Homebrew und `python3`.

1. Terminal öffnen, in den Kit-Ordner wechseln:
   ```bash
   cd ~/Desktop/Proteus-Pairing-MK1/offline_build_kit
   bash 2_mac_pakete_installieren.sh
   ```
   (Mit `bash …` starten – so stören weder fehlende Ausführungsrechte
   noch die Quarantäne-Markierung von kopierten Dateien.)
2. Das Skript
   - prüft macOS-Version, Python-Version und Prozessor,
   - prüft per SHA256 alle Paketdateien,
   - legt die virtuelle Umgebung `venv_mac` an und installiert alles
     **ausschließlich** aus `offline_pakete_mac` (kein Internet),
   - prüft, dass PySide6, bleak, pyobjc (CoreBluetooth) und PyInstaller
     importierbar sind.
3. Am Ende erscheint `FERTIG.`.

## macOS — Schritt 3: App bauen

1. Im selben Ordner:
   ```bash
   bash 3_mac_app_bauen.sh
   ```
2. Quelle: liegt **genau eine** `.zip` neben den Skripten → wird nach
   `projekt_mac` entpackt; sonst wird der Projektordner über dem Kit genommen.
3. Das Skript baut über die Spec-Datei (mit Bluetooth-Berechtigung im
   Info.plist), entfernt Quarantäne-Markierungen und signiert die App
   ad hoc (nötig auf Apple Silicon).
4. Ergebnis in **`fertige_app`**:
   ```
   fertige_app/
   ├── Proteus-Pairing-MK1.app                 <- direkt starten
   └── Proteus-Pairing-MK1-v1.4.0-macOS.zip    <- zum Weitergeben
   ```
   Die App gilt für den Prozessor des Build-Macs (Apple Silicon bzw. Intel).

---

**Neue Projektversion später bauen:** Weg A – neuen Projektstand in den
Projektordner kopieren; Weg B – neue `.zip` gegen die alte austauschen.
Dann nur Schritt 3 erneut starten. Schritt 1/2 müssen nicht wiederholt
werden, solange sich die `requirements.txt` des Projekts nicht ändert.

---

## Programm benutzen

- **Windows:** Die exe ist eine einzige, eigenständige Datei – keine
  Installation, keine DLLs oder Ordner daneben. Bluetooth einschalten
  und starten. Einstellungen/Verlauf liegen unter
  `%APPDATA%\Proteus-Pairing-MK1`.
- **macOS:** App starten (beim ersten Mal ggf. Rechtsklick → „Öffnen“),
  Bluetooth-Zugriff erlauben. Einstellungen/Verlauf liegen unter
  `~/Library/Application Support/Proteus-Pairing-MK1`.

---

## Fehlerbehebung

**Windows**
- **„Kein passendes Python 3.11 (64-Bit) gefunden"** → `python --version`
  bzw. `py --list` prüfen. Anderes Python (mind. 3.10)? Dann im Mac-Skript
  oben `WIN_PY_VER` anpassen und Schritt 1 wiederholen.
- **„DEFEKT"/„FEHLT" bei der Paketprüfung** → `offline_pakete` erneut kopieren.
- **„Mindestens ein Modul fehlt in der venv"** → Schritt 1 wiederholen,
  Ordner `venv` löschen, Schritt 2 neu starten.
- **Windows Defender meldet die neue exe** → normal bei frisch gebauten,
  unsignierten exe-Dateien: „Trotzdem ausführen“ bzw. Ausnahme eintragen.

**macOS**
- **„macOS … ist zu alt"** → PySide6 6.12 braucht macOS 14+.
- **„Kein passendes Python … gefunden"** → das Skript zeigt, welche
  Pythons vorhanden sind. Entweder das passende Python installieren
  oder in Schritt 1 `MAC_PY_VER`/`MAC_ARCH` auf das vorhandene Python
  einstellen und Schritt 1 wiederholen.
- **„beschaedigt … oder fehlt"** → `offline_pakete_mac` erneut kopieren.
- **App startet nicht („beschädigt“ / „nicht geöffnet werden“)** →
  im Terminal `xattr -cr fertige_app/Proteus-Pairing-MK1.app` und dann
  Rechtsklick → „Öffnen“.
- **App beendet sich beim Suchen sofort** → Bluetooth-Zugriff in
  Systemeinstellungen → Datenschutz & Sicherheit → Bluetooth erlauben.

**Beide**
- **„mehrere .zip-Dateien"** → nur die gewünschte Projekt-`.zip` neben die
  Skripte legen (z. B. nicht die ZIP des Kits selbst).
- **„keine Proteus-Pairing-MK1.spec gefunden"** → falsches Archiv; das
  Skript zeigt den gefundenen Inhalt an.

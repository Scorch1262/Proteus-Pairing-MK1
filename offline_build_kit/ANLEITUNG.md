# Proteus-Pairing-MK1 — Windows-exe offline bauen: Mac lädt, Win10 baut

**Offline-Build-Kit v1.0.0** · passend zu Proteus-Pairing-MK1 ab v1.0.1

Drei Skripte, drei Schritte. Python 3.11 (64-Bit) ist auf dem
Windows-10-PC bereits installiert — dieses Kit kümmert sich nur noch um
die Pakete und den eigentlichen exe-Build. Gebaut wird mit derselben
Spec-Datei wie bei GitHub Actions (eine einzelne exe, ohne
Konsolenfenster, mit Programmsymbol):
`Proteus-Pairing-MK1-v<Version>-windows.exe`.

```
offline_build_kit/
├── 1_mac_pakete_herunterladen.sh      <- läuft auf dem Mac (mit Internet)
├── 2_win10_pakete_installieren.bat    <- läuft auf dem Win10-PC
├── 3_win10_exe_bauen.bat              <- läuft auf dem Win10-PC
└── ANLEITUNG.md                       <- diese Datei
```

Das Kit liegt im Repo im Ordner `offline_build_kit`. Es gibt zwei Wege:

| Weg | Was wird kopiert | Wann sinnvoll |
|---|---|---|
| **A – Projektordner** | der ganze Projektordner (mit `offline_build_kit` darin) | einfachster Weg |
| **B – Kit + ZIP** | nur der Kit-Ordner + die Projekt-`.zip` daneben | neue Version bauen, ohne alles neu zu kopieren |

---

## Schritt 1 — auf dem Mac

1. Projekt-ZIP entpacken (oder Repo klonen). Für Weg B den Ordner
   `offline_build_kit` irgendwohin kopieren und die Projekt-`.zip`
   daneben legen.
2. Terminal öffnen, in den Kit-Ordner wechseln, Skript ausführbar
   machen und starten:
   ```bash
   cd ~/Desktop/Proteus-Pairing-MK1/offline_build_kit
   chmod +x 1_mac_pakete_herunterladen.sh
   ./1_mac_pakete_herunterladen.sh
   ```
3. Es entstehen
   - der Ordner **`offline_pakete`** (ca. 85 MB) mit den `.whl`-Dateien für
     `PySide6-Essentials`, `bleak` samt den Windows-Bluetooth-Paketen
     `winrt-*`, `pyinstaller` und allen Abhängigkeiten — passend für
     **Windows 64-Bit / Python 3.11**, egal welches Python auf dem Mac
     läuft (auf dem Mac wird nichts installiert),
   - eine Prüfsummen-Datei `offline_pakete/SHA256SUMS.txt`,
   - die Datei **`paketliste.txt`**.

   > Die Paketliste kommt aus der `requirements.txt` des Projekts:
   > zuerst aus einer `.zip` neben dem Skript, sonst aus dem
   > Projektordner darüber, sonst aus der Standardliste
   > (`PySide6-Essentials==6.12.0`, `bleak==3.1.0`).
   > PyInstaller ist fest auf `6.22.3` gesetzt (wie im GitHub-Workflow).

   > **Warum ein eigener Abhängigkeits-Abgleich?** `pip download` wertet
   > Bedingungen wie `sys_platform == 'win32'` anhand des Macs aus. bleak
   > würde dann die macOS-Pakete (pyobjc) verlangen statt der
   > Windows-Pakete (winrt). Das Skript lädt deshalb ohne automatische
   > Abhängigkeiten und ergänzt sie danach gezielt für Windows/Python 3.11.

**Danach auf den Windows-10-PC kopieren** (USB-Stick, Kabel — egal wie):
- **Weg A:** den kompletten Projektordner (inkl. `offline_build_kit`
  mit `offline_pakete` und `paketliste.txt`)
- **Weg B:** den Kit-Ordner (inkl. `offline_pakete` und
  `paketliste.txt`) und die Projekt-`.zip` **im selben Ordner** neben
  den Skripten

---

## Schritt 2 — auf dem Windows-10-PC: Pakete installieren

1. Doppelklick auf **`2_win10_pakete_installieren.bat`**.
2. Das Skript
   - sucht ein passendes Python 3.11 (64-Bit): erst `python`, sonst
     den Python-Launcher `py -3.11`,
   - prüft per SHA256, dass beim Kopieren keine Paketdatei beschädigt
     wurde,
   - legt die virtuelle Umgebung `venv` an und installiert alle Pakete
     **ausschließlich** aus `offline_pakete` (`--no-index`, kein
     Internet),
   - prüft, dass PySide6, bleak, winrt und PyInstaller importierbar sind.
3. Am Ende erscheint `FERTIG.`.

---

## Schritt 3 — auf dem Windows-10-PC: exe bauen

1. Doppelklick auf **`3_win10_exe_bauen.bat`**.
2. Das Skript wählt die Quelle:
   - liegt **genau eine** `.zip` neben den Skripten → wird nach
     `projekt` entpackt, darin wird `Proteus-Pairing-MK1.spec` gesucht
     (egal in welchem Unterordner),
   - liegt **keine** `.zip` daneben → nimmt den Projektordner über dem
     Kit (`..\Proteus-Pairing-MK1.spec`).
3. Es liest die Versionsnummer aus `APP_VERSION` in `app\config.py`
   und baut mit PyInstaller über die Spec-Datei — wie der GitHub-Workflow.
4. Ergebnis liegt in **`fertige_exe`**:
   ```
   fertige_exe/
   └── Proteus-Pairing-MK1-v1.2.0-windows.exe
   ```

**Neue Projektversion später bauen:** Weg A – neuen Projektstand in den
Projektordner kopieren; Weg B – neue `.zip` gegen die alte austauschen.
Dann `3_win10_exe_bauen.bat` erneut starten. Schritt 1/2 müssen nicht
wiederholt werden, solange sich die `requirements.txt` des Projekts
nicht ändert.

---

## exe benutzen

Die exe ist eine einzige, eigenständige Datei – keine Installation, keine
DLLs oder Ordner daneben. Sie kann an einem beliebigen Ort liegen und legt
dort beim Start keine Dateien an.
Bluetooth am PC einschalten und starten. Einstellungen, Verlauf und
gespeicherte Protokolle legt das Programm unter
`%APPDATA%\Proteus-Pairing-MK1` ab.

---

## Was dieses Kit nicht baut

- **macOS-App:** Eine Mac-App lässt sich nur auf einem Mac bauen,
  nicht unter Windows. Dafür weiterhin den GitHub-Actions-Build nutzen.

---

## Fehlerbehebung

- **„Kein passendes Python 3.11 (64-Bit) gefunden"** (Schritt 2) →
  `python --version` bzw. `py --list` prüfen. Die Pakete aus Schritt 1
  passen nur zu 3.11 / 64-Bit. Ein anderes Python (mind. 3.10)? Dann im
  Mac-Skript oben `PY_VER="3.11"` anpassen und Schritt 1 wiederholen.
- **„DEFEKT"/„FEHLT" bei der Paketprüfung** → Kopiervorgang
  unvollständig; `offline_pakete` erneut auf den PC kopieren.
- **„Mindestens ein Modul fehlt in der venv"** (Schritt 2) → Schritt 1
  mit diesem Kit wiederholen und erneut kopieren; danach den Ordner
  `venv` löschen und Schritt 2 neu starten.
- **„venv mit PyInstaller wurde nicht gefunden"** (Schritt 3) → erst
  Schritt 2 erfolgreich durchlaufen lassen, im selben Ordner.
- **„mehrere .zip-Dateien"** → nur die gewünschte Projekt-`.zip`
  neben die Skripte legen (z. B. nicht die ZIP des Kits selbst).
- **„keine Proteus-Pairing-MK1.spec gefunden"** → falsches Archiv;
  das Skript zeigt den gefundenen Inhalt an.
- **Windows Defender meldet die neue exe** → normal bei frisch
  gebauten, unsignierten PyInstaller-exe-Dateien: „Trotzdem ausführen"
  bzw. Ausnahme eintragen.

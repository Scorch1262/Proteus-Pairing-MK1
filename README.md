# Proteus-Pairing-MK1

**Version 1.0.1** · Desktop-Programm für Windows und macOS (keine Web-App)

Arbeitet den Paarungsablauf zwischen einem **Host-Modul** und einem **PTT-Modul** mit
Würth-Elektronik-**Proteus-II**-Bluetooth-Modulen automatisch ab – über die Bluetooth-Schnittstelle
des PCs/Macs. Das Programm ersetzt die Bedienung der Proteus-App auf dem Smartphone.

![Proteus-Pairing-MK1](docs/screenshot.png)

## Funktionen

- **Automatischer Ablauf** aller Schritte aus der Paarungsanleitung (`docs/Paarungsanleitung.txt`)
- **Universell nutzbar:** Geräte werden nur über die Erkennungsmarken **„Host“** und **„PTT“** im
  Gerätenamen erkannt (Groß-/Kleinschreibung egal). Enthält ein Name beide Marken
  (z. B. `…-PTT_MK10_Host`), gilt er als Host.
- **Automatische Auswahl ohne Nutzerhandlung:** Suche, Verbindung, Auswahl des Proteus-II-Profils
  (Service `6E400001-C352-11E5-953D-0002A5D5C51B`), Kopplung, Befehle senden, Antwort auswerten.
  Sind mehrere passende Module in Reichweite, wird das mit dem stärksten Signal genommen.
- **Klare Nutzerhinweise:** Muss etwas von Hand erledigt werden (Modul einschalten, PTT-Taste
  halten, Neustart …), wird das in einer großen, orange blinkenden Karte „NUTZERAKTION
  ERFORDERLICH“ angezeigt, mit Signalton und Taskleisten-Hinweis. Die Schrittliste links
  markiert solche Schritte mit **NUTZER**.
- Ausgelesene **Host-MAC** groß angezeigt, kopierbar
- **Protokoll** aller gesendeten (TX) und empfangenen (RX) Daten, speicherbar
- **Verlauf** aller Paarungen (CSV im Benutzerordner)
- **Nur PTT:** MAC-Adresse von Hand eingeben und nur das PTT-Modul konfigurieren
- Fehler (z. B. Modul nicht gefunden, keine Antwort) mit „Wiederholen“ oder „Abbrechen“
- Alle Marken, Befehle, Zeiten und Optionen in den **Einstellungen** anpassbar

## Ablauf

| Programm | Anleitung | Art |
|---|---|---|
| Haupt-Modul einschalten | 1 | **Nutzer** (geht automatisch weiter, sobald das Modul gefunden wurde) |
| „Host“-Modul suchen | 3 | automatisch |
| Startzeit abwarten (ca. 5 s) | 2 | automatisch |
| Verbinden · Proteus-II-Profil | 4 | automatisch |
| Kopplung bestätigen | 5 | automatisch (ggf. Systemdialog bestätigen) |
| „BT-MAC?“ senden | 6 | automatisch |
| MAC-Adresse auslesen & merken | 7–8 | automatisch |
| PTT-Taste halten + PTT-Modul einschalten | 9 | **Nutzer** (geht automatisch weiter, sobald das Modul gefunden wurde) |
| „PTT“-Modul suchen | 11 | automatisch |
| Startzeit abwarten (ca. 5 s) | 10 | automatisch |
| Verbinden · Proteus-II-Profil | 12 | automatisch |
| „Host:&lt;MAC&gt;“ senden | 13 | automatisch |
| PTT-Modul aus / Haupt-Modul aus / Haupt-Modul ein / PTT-Modul ein | 14–17 | **Nutzer** (je „Erledigt“) |

## Download und Start

Das fertige Paket entsteht per GitHub Actions (Reiter **Actions** → letzter Lauf → Artefakt
`Proteus-Pairing-MK1-v1.0.1`, bzw. bei einem Tag `v*` als Release).

```
Proteus-Pairing-MK1-v1.0.1/
├── Windows/Proteus-Pairing-MK1.exe        ← einzelne exe, keine Installation nötig
├── macOS/Proteus-Pairing-MK1-macOS.zip    ← entpacken → Proteus-Pairing-MK1.app
├── Paarungsanleitung.txt
└── README.md
```

- **Windows 10/11:** exe starten. Bluetooth muss eingeschaltet sein. Beim ersten Start kann der
  SmartScreen-Hinweis erscheinen („Weitere Informationen“ → „Trotzdem ausführen“).
- **macOS (Apple Silicon, ab macOS 11):** ZIP entpacken, App per Rechtsklick → „Öffnen“ starten
  (nicht signiert). Bluetooth-Zugriff beim ersten Start erlauben. Falls macOS die App blockiert:
  `xattr -cr Proteus-Pairing-MK1.app` im Terminal ausführen.

Einstellungen, Verlauf (`verlauf.csv`) und gespeicherte Protokolle liegen unter
`%APPDATA%\Proteus-Pairing-MK1` (Windows) bzw. `~/Library/Application Support/Proteus-Pairing-MK1` (macOS).

## Einstellungen

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Marke Host-Modul / PTT-Modul | `Host` / `PTT` | Teil des Gerätenamens zur Erkennung |
| MAC-Abfrage am Host | `BT-MAC?` | Befehl an das Host-Modul |
| Präfix am PTT-Modul | `Host:` | wird mit der MAC zu `Host:00:18:DA:…` |
| Zeilenende | kein | wie in der Proteus-App; bei Bedarf CR / LF / CR+LF |
| Proteus-II-Datenheader 0x01 | an | Proteus-II-Profil: jedes Datenpaket beginnt mit 0x01 |
| Startzeit nach Erkennen | 5 s | „ca. 5 s warten“ |
| Max. Suchdauer | 120 s | danach Fehlermeldung mit „Wiederholen“ |
| Antwort-Timeout / Wiederholungen | 5 s / 3 | für die MAC-Abfrage |
| Kopplung Host / PTT | an / aus | Kopplung anfordern (Schritt 5) |
| Kopplung danach entfernen | aus | nur Windows; hält die Bluetooth-Geräteliste sauber |
| Neustart-Schritte einzeln bestätigen | an | sonst eine Sammelbestätigung für Schritt 14–17 |

## Offline bauen (ohne Internet am Windows-PC)

Im Ordner [`offline_build_kit`](offline_build_kit/ANLEITUNG.md) liegt ein
Offline-Build-Kit: **der Mac lädt die Pakete, der Windows-10-PC baut die exe**
– mit derselben Spec-Datei wie GitHub Actions.

1. Mac: `offline_build_kit/1_mac_pakete_herunterladen.sh` (lädt ca. 85 MB Pakete für Windows / Python 3.11)
2. Projektordner auf den Win10-PC kopieren → `2_win10_pakete_installieren.bat`
3. `3_win10_exe_bauen.bat` → `offline_build_kit/fertige_exe/Proteus-Pairing-MK1-v<Version>-windows.exe`

Details, beide Wege (Projektordner oder Kit + ZIP) und Fehlerbehebung:
[`offline_build_kit/ANLEITUNG.md`](offline_build_kit/ANLEITUNG.md).
Das Kit wird außerdem bei jedem Release als eigene ZIP mitgeliefert.

## Selbst bauen

```bash
pip install -r requirements.txt pyinstaller==6.22.3
python main.py                                        # direkt starten
pyinstaller --noconfirm --clean Proteus-Pairing-MK1.spec   # exe bzw. .app in dist/
```

Projektstruktur:

```
main.py                      Startpunkt
app/config.py                Version, Einstellungen, Verlauf
app/engine.py                Ablaufsteuerung + Bluetooth LE (bleak)
app/gui.py                   Oberfläche (PySide6/Qt)
app/style.py                 Farbschema im Dashboard-Design
assets/                      Programmsymbol (png/ico/icns)
tools/make_icon.py           erzeugt die Symbole neu
docs/                        Screenshot, Paarungsanleitung
.github/workflows/build.yml  Build Windows-exe + macOS-App + Gesamt-ZIP + Offline-Kit-ZIP
offline_build_kit/           Offline-Build-Kit (Mac lädt, Win10 baut)
```

Technik: Python 3.12 (Offline-Kit: 3.11), PySide6-Essentials 6.12 (Qt 6), bleak 3.1 (WinRT unter Windows, CoreBluetooth unter macOS),
PyInstaller.

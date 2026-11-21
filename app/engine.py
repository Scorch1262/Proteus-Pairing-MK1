"""Ablaufsteuerung des Paarungsprozesses (Bluetooth LE über bleak).

Die Klasse ``PairingEngine`` kennt keine Oberfläche. Sie meldet alles über ein
``ui``-Objekt mit diesen Methoden (werden im Bluetooth-Thread aufgerufen):

    on_step(step_id, state, detail)      state: pending|active|user|done|error|skipped
    on_action(dict)                      Hauptanzeige (Modus, Titel, Text, Knöpfe)
    on_progress(value, maximum)          Fortschritt; maximum == 0 -> unbestimmt
    on_log(kind, text)                   kind: info|tx|rx|ok|warn|error
    on_device(role, info | None)         role: host|ptt
    on_mac(mac)
    on_finished(result, summary)         result: ok|abort|error
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

from . import config as cfg
from . import winpair
from .config import Settings, append_history, now_str

# Würth Elektronik Proteus-II – SPP-ähnliches BLE-Profil
PROTEUS_SERVICE = "6e400001-c352-11e5-953d-0002a5d5c51b"
PROTEUS_TX_CHAR = "6e400002-c352-11e5-953d-0002a5d5c51b"  # PC -> Modul (Write)
PROTEUS_RX_CHAR = "6e400003-c352-11e5-953d-0002a5d5c51b"  # Modul -> PC (Notify)
PROTEUS_DATA_HEADER = b"\x01"
GAP_DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"
WURTH_OUI = "00:18:DA"  # Herstellerkennung Würth Elektronik eiSos

MAC_RE = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")
MAC_LINE_RE = re.compile(r"MAC\s*:?\s*([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", re.IGNORECASE)


def _is_auth_error(exc) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("authentication", "authorization", "encryption", "insufficient"))


class ProcessError(Exception):
    """Fehler in einem Schritt – dem Nutzer verständlich anzeigen."""


class AbortProcess(Exception):
    pass


@dataclass
class Step:
    id: str
    phase: str      # A = Host, B = PTT, C = Neustart
    title: str
    user: bool      # erfordert Handlung des Nutzers
    ref: str        # Schrittnummer(n) aus der Paarungsanleitung


def build_steps(s: Settings) -> list[Step]:
    return [
        Step("h_power", "A", "Haupt-Modul einschalten", True, "1"),
        Step("h_scan", "A", f"„{s.marker_host}“-Modul suchen & erkennen", False, "3"),
        Step("h_wait", "A", f"Startzeit abwarten (ca. {s.boot_wait_s:g} s)", False, "2"),
        Step("h_connect", "A", "Verbinden · Proteus-II-Profil", False, "4"),
        Step("h_pair", "A", "Kopplung bestätigen", False, "5"),
        Step("h_cmd", "A", f"„{s.cmd_host_mac}“ senden", False, "6"),
        Step("h_mac", "A", "MAC-Adresse auslesen & merken", False, "7–8"),
        Step("p_power", "B", "PTT-Taste halten + PTT-Modul einschalten", True, "9"),
        Step("p_scan", "B", f"„{s.marker_ptt}“-Modul suchen & erkennen", False, "11"),
        Step("p_wait", "B", f"Startzeit abwarten (ca. {s.boot_wait_s:g} s)", False, "10"),
        Step("p_connect", "B", "Verbinden · Proteus-II-Profil", False, "12"),
        Step("p_send", "B", f"„{s.cmd_ptt_prefix}<MAC>“ senden", False, "13"),
        Step("r_ptt_off", "C", "PTT-Modul ausschalten", True, "14"),
        Step("r_host_off", "C", "Haupt-Modul ausschalten", True, "15"),
        Step("r_host_on", "C", "Haupt-Modul einschalten", True, "16"),
        Step("r_ptt_on", "C", "PTT-Modul einschalten", True, "17"),
    ]


def role_of(name: str, s: Settings) -> str | None:
    """Ordnet einen Gerätenamen anhand der Erkennungsmarken zu.

    Der Host-Name enthält oft ebenfalls „PTT“ (z. B. „…-PTT_MK10_Host“),
    deshalb wird die Host-Marke zuerst geprüft.
    """
    if not name:
        return None
    low = name.lower()
    if s.marker_host and s.marker_host.lower() in low:
        return "host"
    if s.marker_ptt and s.marker_ptt.lower() in low:
        return "ptt"
    return None


def _visible(text: str) -> str:
    return text.replace("\r", "\\r").replace("\n", "\\n")


class PairingEngine:
    def __init__(self, ui, settings: Settings):
        self.ui = ui
        self.s = settings
        self.steps = build_steps(settings)
        self._response: asyncio.Future | None = None
        self._clients: list[BleakClient] = []
        self._rx_buf = ""
        self._rx_event: asyncio.Event | None = None
        self._tx_char = None
        self._expect_disconnect = False
        self._current: str | None = None
        self.host_info: dict | None = None
        self.ptt_info: dict | None = None
        self.mac: str | None = None
        self.name_cache: dict[str, str] = self._load_name_cache()  # Adresse -> voller Name
        self._auth_failed: set[str] = set()   # Adressen mit abgelehnter Authentifizierung
        self._cur_name: str = ""

    # ------------------------------------------------------------------ UI-Hilfen
    def respond(self, choice: str) -> None:
        """Antwort des Nutzers (im Bluetooth-Thread aufrufen)."""
        if self._response is not None and not self._response.done():
            self._response.set_result(choice)

    async def _ask(self, mode: str, title: str, text: str, buttons, hint: str = "", step: str = "") -> str:
        self._response = asyncio.get_running_loop().create_future()
        self.ui.on_action(dict(mode=mode, title=title, text=text, hint=hint,
                               buttons=list(buttons), step=step, busy=False))
        try:
            return await self._response
        finally:
            self._response = None

    def _show(self, mode: str, title: str, text: str, hint: str = "", step: str = "", busy: bool = True):
        self.ui.on_action(dict(mode=mode, title=title, text=text, hint=hint,
                               buttons=[], step=step, busy=busy))

    def _step(self, sid: str, state: str, detail: str = ""):
        if state in ("active", "user"):
            self._current = sid
        self.ui.on_step(sid, state, detail)

    def _log(self, kind: str, text: str):
        self.ui.on_log(kind, text)

    # ------------------------------------------------------------------ Ablauf
    async def run(self, mode: str = "full", manual_mac: str | None = None) -> None:
        result, summary = "error", ""
        try:
            for st in self.steps:
                self._step(st.id, "pending")
            if mode == "full":
                self.mac = await self._retryable("A", self._phase_host)
            else:
                self.mac = manual_mac.upper()
                for st in self.steps:
                    if st.phase == "A":
                        self._step(st.id, "skipped", "übersprungen")
                self.ui.on_mac(self.mac)
                self._log("info", f"Host-MAC manuell vorgegeben: {self.mac}")
            await self._retryable("B", self._phase_ptt)
            await self._phase_restart()
            result = "ok"
            summary = f"PTT-Modul wurde mit Host {self.mac} gepaart."
            self._show("done", "PAARUNG ABGESCHLOSSEN",
                       "Beide Module wurden neu gestartet und sind gepaart.",
                       hint=f"Host-MAC: {self.mac}", busy=False)
            self._log("ok", summary)
        except (asyncio.CancelledError, AbortProcess):
            result, summary = "abort", "Ablauf abgebrochen."
            self._show("idle", "ABGEBROCHEN", "Der Ablauf wurde abgebrochen.",
                       hint="Mit START kann ein neuer Durchlauf begonnen werden.", busy=False)
            self._log("warn", summary)
        except Exception as exc:  # unerwartet
            result, summary = "error", f"Unerwarteter Fehler: {exc}"
            self._show("error", "FEHLER", summary, busy=False)
            self._log("error", summary)
        finally:
            await self._cleanup()
            try:
                append_history([
                    now_str(),
                    (self.host_info or {}).get("name", "–"),
                    self.mac or "–",
                    (self.ptt_info or {}).get("name", "–"),
                    (self.ptt_info or {}).get("address", "–"),
                    {"ok": "OK", "abort": "Abgebrochen"}.get(result, "Fehler"),
                ])
            except Exception:
                pass
            self.ui.on_finished(result, summary)

    async def _retryable(self, phase: str, func):
        while True:
            try:
                return await func()
            except (asyncio.CancelledError, AbortProcess):
                raise
            except Exception as exc:
                msg = str(exc) or exc.__class__.__name__
                if not isinstance(exc, ProcessError):
                    msg = f"{exc.__class__.__name__}: {msg}"
                self._log("error", msg)
                if self._current:
                    self._step(self._current, "error", "Fehler")
                await self._cleanup()
                label = "Host" if phase == "A" else "PTT"
                choice = await self._ask(
                    "error", "FEHLER – EINGRIFF ERFORDERLICH", msg,
                    [("retry", f"{label}-Teil wiederholen"), ("abort", "Abbrechen")],
                    hint="Prüfen Sie, ob das Modul eingeschaltet und in Reichweite ist.")
                if choice != "retry":
                    raise AbortProcess()
                self._log("info", f"Wiederhole {label}-Teil …")
                for st in self.steps:
                    if st.phase == phase:
                        self._step(st.id, "pending")

    # ------------------------------------------------------------------ Phase A
    async def _phase_host(self) -> str:
        s = self.s
        self.ui.on_device("host", None)
        # Schritt 1 + Suche parallel: das Einschalten wird durch das Erkennen bestätigt
        self._step("h_power", "user")
        self._step("h_scan", "active", "Suche läuft …")
        self._show("user", "NUTZERAKTION ERFORDERLICH",
                   "Haupt-Modul einschalten",
                   hint=f"Das Programm sucht automatisch nach einem Proteus-II-Modul mit "
                        f"„{s.marker_host}“ im Namen und fährt fort, sobald es gefunden wurde. "
                        f"Gekürzte Namen (z. B. „Albre…“) werden per kurzer Verbindung geprüft.",
                   step="h_power")
        info, client = await self._acquire("host", set(), "h_power", "h_scan", "h_wait", "h_connect",
                                           "Haupt-Modul startet …", s.pair_host)
        self.host_info = info

        await self._pair_and_open(client, "h_pair", s.pair_host)

        mac = None
        for attempt in range(1, max(1, s.retries) + 1):
            self._step("h_cmd", "active", f"Versuch {attempt}")
            self._show("auto", "AUTOMATISCH", f"Sende „{s.cmd_host_mac}“ …",
                       hint=f"Versuch {attempt} von {s.retries}", step="h_cmd")
            self._rx_buf = ""
            await self._send(client, s.cmd_host_mac)
            self._step("h_cmd", "done")
            self._step("h_mac", "active", "warte auf Antwort …")
            mac = await self._wait_for_mac(s.response_timeout_s)
            if mac:
                break
            self._log("warn", f"Keine gültige Antwort innerhalb von {s.response_timeout_s:g} s.")
        if not mac:
            raise ProcessError(f"Das Host-Modul hat nicht mit „Bluetooth MAC: …“ geantwortet "
                               f"({s.retries} Versuche).")
        mac = mac.upper()
        self._step("h_mac", "done", mac)
        self.ui.on_mac(mac)
        self._log("ok", f"Host-MAC-Adresse: {mac}")

        await self._finish_client(client)
        return mac

    # ------------------------------------------------------------------ Phase B
    async def _phase_ptt(self) -> None:
        s = self.s
        self.ui.on_device("ptt", None)
        self._step("p_power", "user")
        self._step("p_scan", "active", "Suche läuft …")
        self._show("user", "NUTZERAKTION ERFORDERLICH",
                   "PTT-Knopf am PTT-Modul gedrückt halten und dabei das PTT-Modul einschalten",
                   hint=f"Das Haupt-Modul bleibt eingeschaltet. Das Programm sucht automatisch nach "
                        f"einem Modul mit „{s.marker_ptt}“ im Namen und fährt fort, sobald es "
                        f"gefunden wurde.",
                   step="p_power")
        exclude = {self.host_info["address"]} if self.host_info else set()
        info, client = await self._acquire("ptt", exclude, "p_power", "p_scan", "p_wait", "p_connect",
                                           "PTT-Modul startet …", s.pair_ptt)
        self.ptt_info = info
        await self._pair_and_open(client, None, s.pair_ptt)

        cmd = f"{s.cmd_ptt_prefix}{self.mac}"
        self._step("p_send", "active")
        self._show("auto", "AUTOMATISCH", f"Sende „{cmd}“ …", step="p_send")
        self._rx_buf = ""
        self._expect_disconnect = True  # Modul darf sich danach selbst trennen
        await self._send(client, cmd)
        await asyncio.sleep(max(0.0, s.ptt_reply_wait_s))
        if self._rx_buf.strip():
            self._log("info", f"Antwort PTT-Modul: {_visible(self._rx_buf.strip())}")
        self._step("p_send", "done", "gesendet")
        await self._finish_client(client)

    async def _acquire(self, role, exclude, sid_power, sid_scan, sid_wait, sid_connect, wait_text, do_pair):
        """Modul finden, Startzeit abwarten, verbinden – gemeinsam für Host und PTT."""
        dev, adv, name, client = await self._find(role, exclude, sid_scan)
        self._cur_name = name
        self._step(sid_power, "done")
        self._step(sid_scan, "done", name)
        info = dict(name=name, address=dev.address, rssi=adv.rssi)
        self.ui.on_device(role, info)
        waited = client is not None   # bei der Namensprüfung wurde die Startzeit schon abgewartet

        # Veraltete Windows-Kopplung entfernen (wie beim Handy wird danach neu gekoppelt)
        if winpair.AVAILABLE and self.s.repair_fresh and (do_pair or dev.address in self._auth_failed):
            try:
                paired = await winpair.is_paired(dev.address)
            except Exception as exc:
                paired = False
                self._log("warn", f"Kopplungsstatus nicht lesbar ({exc}).")
            if paired:
                self._log("warn", "Windows hat für dieses Modul noch eine Kopplung gespeichert – sie wird "
                                  "entfernt und gleich neu hergestellt.")
                if client is not None:
                    self._expect_disconnect = True
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    if client in self._clients:
                        self._clients.remove(client)
                    client = None
                try:
                    status = await winpair.unpair(dev.address)
                    self._log("info", f"Alte Kopplung entfernt ({status}).")
                except Exception as exc:
                    self._log("warn", f"Alte Kopplung konnte nicht entfernt werden ({exc}).")
                await asyncio.sleep(1.5)
                self._auth_failed.discard(dev.address)

        if client is None:
            if waited:
                self._step(sid_wait, "done", "während der Erkennung abgewartet")
            else:
                await self._countdown(sid_wait, wait_text)
            self._step(sid_connect, "active", "verbinde …")
            self._show("auto", "AUTOMATISCH", f"Verbinde mit „{name}“ …",
                       hint="Proteus-II-Profil wird automatisch ausgewählt.", step=sid_connect)
            client = await self._connect(dev, name)
        else:
            self._step(sid_wait, "done", "während der Erkennung abgewartet")
            self._step(sid_connect, "active", "bestehende Verbindung")
            await self._ensure_connected(client)
            await self._verify_proteus(client, name)
        self._step(sid_connect, "done", "Proteus-II-Profil gefunden")
        return info, client

    # ------------------------------------------------------------------ Phase C
    async def _phase_restart(self) -> None:
        texts = {
            "r_ptt_off": "PTT-Modul ausschalten",
            "r_host_off": "Haupt-Modul ausschalten",
            "r_host_on": "Haupt-Modul einschalten",
            "r_ptt_on": "PTT-Modul einschalten",
        }
        order = list(texts)
        if self.s.confirm_restart_steps:
            for i, sid in enumerate(order, 1):
                self._step(sid, "user")
                choice = await self._ask(
                    "user", "NUTZERAKTION ERFORDERLICH", texts[sid],
                    [("ok", "Erledigt  ▸"), ("abort", "Abbrechen")],
                    hint=f"Neustart {i}/4 – bitte bestätigen, sobald erledigt.", step=sid)
                if choice != "ok":
                    raise AbortProcess()
                self._step(sid, "done")
        else:
            for sid in order:
                self._step(sid, "user")
            listing = "\n".join(f"{i}. {texts[sid]}" for i, sid in enumerate(order, 1))
            choice = await self._ask("user", "NUTZERAKTION ERFORDERLICH",
                                     "Module neu starten – in dieser Reihenfolge:\n" + listing,
                                     [("ok", "Alles erledigt  ▸"), ("abort", "Abbrechen")])
            if choice != "ok":
                raise AbortProcess()
            for sid in order:
                self._step(sid, "done")

    # ------------------------------------------------------------------ Bausteine
    def _is_candidate(self, e: dict) -> bool:
        """Könnte ein Proteus-II-Modul sein, dessen voller Name erst nach dem Verbinden lesbar ist."""
        if e["uuid"] or e["oui"]:
            return True
        prefix = self.s.name_prefix.strip().lower()
        return bool(prefix) and e["name"].lower().startswith(prefix)

    def _known_name(self, e: dict) -> str:
        return self.name_cache.get(e["dev"].address) or e["name"]

    async def _find(self, role: str, exclude: set[str], sid_scan: str):
        """Sucht ein Modul der Rolle host/ptt.

        1. Voller Name schon in der Werbung (oder aus dem Namensspeicher) -> direkt.
        2. Sonst: Proteus-Kandidaten (UUID / Würth-Adresse 00:18:DA / Namensanfang) kurz
           verbinden und den vollständigen Gerätenamen lesen.
        Rückgabe: (BLEDevice, AdvertisementData, voller Name, verbundener Client oder None)
        """
        s = self.s
        loop = asyncio.get_running_loop()
        seen: dict[str, dict] = {}
        failed: dict[str, float] = {}       # Adresse -> Zeitpunkt des Fehlversuchs
        mismatch: set[str] = set()          # geprüft, falsche Rolle
        marker = s.marker_host if role == "host" else s.marker_ptt

        def detected(device, adv):
            addr = device.address
            if addr in exclude:
                return
            name = adv.local_name or device.name or ""
            now = loop.time()
            e = seen.get(addr)
            if e is None:
                e = seen[addr] = dict(
                    dev=device, adv=adv, name=name, first=now,
                    uuid=PROTEUS_SERVICE in [u.lower() for u in (adv.service_uuids or [])],
                    oui=addr.upper().startswith(WURTH_OUI))
                if self._is_candidate(e) or role_of(self._known_name(e), s):
                    tags = [t for t, on in (("Proteus-UUID", e["uuid"]), ("Würth-Adresse", e["oui"])) if on]
                    known = self.name_cache.get(addr)
                    self._log("info", f"Gesehen: „{name or '?'}“  [{addr}]  {adv.rssi} dBm"
                                      + (f"  · {', '.join(tags)}" if tags else "")
                                      + (f"  · bekannt als „{known}“" if known and known != name else ""))
            else:
                e["dev"], e["adv"] = device, adv
                if len(name) > len(e["name"]):
                    e["name"] = name
                if not e["uuid"] and PROTEUS_SERVICE in [u.lower() for u in (adv.service_uuids or [])]:
                    e["uuid"] = True

        scanner = BleakScanner(detection_callback=detected)

        async def start():
            try:
                await scanner.start()
            except Exception as exc:
                raise ProcessError(f"Bluetooth-Suche konnte nicht gestartet werden ({exc}). "
                                   f"Ist Bluetooth am Rechner eingeschaltet?")

        async def stop():
            try:
                await scanner.stop()
            except Exception:
                pass

        await start()
        self._log("info", f"Suche nach Modul mit „{marker}“ …")
        t0 = loop.time()
        try:
            while True:
                if loop.time() - t0 >= s.scan_timeout_s:
                    raise ProcessError(self._not_found_text(marker, seen))
                self.ui.on_progress(0, 0)
                await asyncio.sleep(0.5)

                # 1) Voller Name bekannt (Werbung oder Namensspeicher)
                direct = [e for e in seen.values() if role_of(self._known_name(e), s) == role]
                if direct:
                    await asyncio.sleep(1.0)  # weitere Kandidaten kurz sammeln
                    await stop()
                    direct = [e for e in seen.values() if role_of(self._known_name(e), s) == role]
                    direct.sort(key=lambda e: (e["uuid"], e["adv"].rssi or -999), reverse=True)
                    if len(direct) > 1:
                        self._log("warn", f"{len(direct)} passende Module gefunden – nehme das stärkste "
                                          f"Signal: {self._known_name(direct[0])} ({direct[0]['adv'].rssi} dBm)")
                    e = direct[0]
                    name = self._known_name(e)
                    self._log("info", f"Gefunden: {name}  [{e['dev'].address}]  {e['adv'].rssi} dBm")
                    return e["dev"], e["adv"], name, None

                # 2) Gekürzte Namen: Kandidaten per Verbindung prüfen
                if not s.identify_by_connect:
                    continue
                now = loop.time()
                todo = [e for addr, e in seen.items()
                        if self._is_candidate(e)
                        and addr not in mismatch
                        and addr not in self.name_cache
                        and now - e["first"] >= s.boot_wait_s
                        and now - failed.get(addr, -1e9) >= 10.0]
                if not todo:
                    continue
                todo.sort(key=lambda e: e["adv"].rssi or -999, reverse=True)
                e = todo[0]
                addr = e["dev"].address
                await stop()  # Verbinden während der Suche ist unter Windows unzuverlässig
                self._step(sid_scan, "active", f"prüfe „{e['name'] or addr}“ …")
                self._show("auto", "AUTOMATISCH", f"Prüfe Gerät „{e['name'] or addr}“ …",
                           hint="Der vollständige Name ist erst nach dem Verbinden lesbar. "
                                "Das Programm verbindet sich kurz und liest ihn aus.", step=sid_scan)
                client, full = await self._identify(e)
                if full is None:
                    failed[addr] = loop.time()
                elif role_of(full, s) == role and client is not None:
                    return e["dev"], e["adv"], full, client
                else:
                    mismatch.add(addr)
                self._step(sid_scan, "active", "Suche läuft …")
                self._show("user", "NUTZERAKTION ERFORDERLICH",
                           "Haupt-Modul einschalten" if role == "host" else
                           "PTT-Knopf am PTT-Modul gedrückt halten und dabei das PTT-Modul einschalten",
                           hint=f"Suche weiter nach einem Modul mit „{marker}“ im Namen …",
                           step="h_power" if role == "host" else "p_power")
                await start()
        finally:
            await stop()

    def _not_found_text(self, marker: str, seen: dict) -> str:
        lines = [f"Kein Modul mit „{marker}“ im Namen innerhalb von {self.s.scan_timeout_s:g} s gefunden."]
        named = sorted((e for e in seen.values() if e["name"] or e["uuid"] or e["oui"]),
                       key=lambda e: e["adv"].rssi or -999, reverse=True)[:6]
        if named:
            lines.append("Gesehene Geräte: " + ", ".join(
                f"„{self._known_name(e) or '?'}“ ({e['adv'].rssi} dBm)" for e in named))
            lines.append("Tipp: Zeigt das Modul nur einen gekürzten Namen (z. B. „Albre“), diesen in den "
                         "Einstellungen unter „Namensanfang prüfen“ eintragen.")
        return "\n".join(lines)

    async def _identify(self, e: dict):
        """Kurz verbinden und den vollständigen Gerätenamen lesen.

        Rückgabe (client | None, voller Name | None). Passt der Name nicht zur gesuchten
        Rolle, wird wieder getrennt; der Name landet im Namensspeicher.
        """
        addr = e["dev"].address
        holder = {"name": e["name"] or addr}

        def on_disconnect(_client):
            if not self._expect_disconnect:
                self._log("warn", f"Verbindung zu „{holder['name']}“ wurde getrennt.")

        self._log("info", f"Prüfe „{e['name'] or '?'}“ [{addr}] – verbinde, um den vollen Namen zu lesen …")
        self._expect_disconnect = False
        client = BleakClient(e["dev"], disconnected_callback=on_disconnect, timeout=15)
        try:
            await client.connect()
        except Exception as exc:
            self._log("warn", f"Prüfverbindung fehlgeschlagen ({exc}) – versuche später erneut.")
            return None, None
        self._clients.append(client)
        full = await self._read_full_name(client, e["name"])
        holder["name"] = full
        self.name_cache[addr] = full
        self._save_name_cache()
        role = role_of(full, self.s)
        self._log("info", f"Voller Name: „{full}“" + (f"  → {role.upper()}" if role else "  → nicht gesucht"))
        if role:
            return client, full
        self._expect_disconnect = True
        try:
            await client.disconnect()
        except Exception:
            pass
        if client in self._clients:
            self._clients.remove(client)
        return None, full

    async def _read_full_name(self, client: BleakClient, adv_name: str) -> str:
        names: list[str] = []

        def add(n):
            n = (n or "").strip("\x00 \r\n")
            if n and n not in names and not re.fullmatch(r"[0-9A-Fa-f:\-]{12,}", n):
                names.append(n)

        # a) GATT-Characteristic „Device Name“ 0x2A00 (unter Windows/macOS meist ausgeblendet)
        try:
            ch = client.services.get_characteristic(GAP_DEVICE_NAME)
            if ch is not None:
                add(bytes(await client.read_gatt_char(ch)).decode("utf-8", "replace"))
        except Exception:
            pass
        # b) Name des Betriebssystems nach der Verbindung (Windows: BluetoothLEDevice.Name,
        #    macOS: CBPeripheral.name) – wird u. U. erst kurz nach dem Verbinden aktualisiert
        for _ in range(15):
            try:
                add(client.name)
            except Exception:
                pass
            if any(role_of(n, self.s) for n in names):
                break
            await asyncio.sleep(0.2)
        # c) Windows: Gerät frisch beim System abfragen
        if sys.platform == "win32" and not any(role_of(n, self.s) for n in names):
            try:
                from winrt.windows.devices.bluetooth import BluetoothLEDevice
                d = await BluetoothLEDevice.from_bluetooth_address_async(
                    int(client.address.replace(":", "").replace("-", ""), 16))
                if d is not None:
                    add(d.name)
            except Exception:
                pass
        for n in names:
            if role_of(n, self.s):
                return n
        return max(names + [adv_name or ""], key=len) or client.address

    def _load_name_cache(self) -> dict:
        try:
            return dict(json.loads((cfg.data_dir() / "namen_cache.json").read_text(encoding="utf-8")))
        except Exception:
            return {}

    def _save_name_cache(self):
        try:
            (cfg.data_dir() / "namen_cache.json").write_text(
                json.dumps(self.name_cache, indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    async def _countdown(self, sid: str, text: str):
        secs = max(0.0, self.s.boot_wait_s)
        self._step(sid, "active")
        self._show("auto", "AUTOMATISCH", text, hint=f"Warte {secs:g} s", step=sid, busy=False)
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        while (el := loop.time() - t0) < secs:
            self.ui.on_progress(int(el * 10), int(secs * 10))
            await asyncio.sleep(0.1)
        self.ui.on_progress(int(secs * 10), max(1, int(secs * 10)))
        self._step(sid, "done")

    async def _connect(self, dev, name: str) -> BleakClient:
        last = None
        self._expect_disconnect = False

        def on_disconnect(_client):
            if not self._expect_disconnect:
                self._log("warn", f"Verbindung zu „{name}“ wurde getrennt.")

        for attempt in range(1, max(1, self.s.retries) + 1):
            client = BleakClient(dev, disconnected_callback=on_disconnect, timeout=20)
            try:
                self._log("info", f"Verbinde mit {name} (Versuch {attempt}) …")
                await client.connect()
                self._clients.append(client)
                break
            except Exception as exc:
                last = exc
                self._log("warn", f"Verbindung fehlgeschlagen: {exc}")
                await asyncio.sleep(1.0)
        else:
            raise ProcessError(f"Verbindung zu „{name}“ nicht möglich ({last}).")
        await self._verify_proteus(client, name)
        return client

    async def _verify_proteus(self, client: BleakClient, name: str):
        svc = client.services.get_service(PROTEUS_SERVICE)
        tx = svc.get_characteristic(PROTEUS_TX_CHAR) if svc else None
        rx = svc.get_characteristic(PROTEUS_RX_CHAR) if svc else None
        if not (svc and tx and rx):
            raise ProcessError(f"„{name}“ bietet kein Proteus-II-Profil "
                               f"(Service {PROTEUS_SERVICE} fehlt).")
        self._tx_char = tx
        self._rx_char = rx
        # MTU-Aushandlung kurz abwarten (Windows/macOS erledigen das selbst)
        for _ in range(20):
            if tx.max_write_without_response_size > 20:
                break
            await asyncio.sleep(0.1)
        self._log("info", f"Verbunden. Proteus-II-Profil ausgewählt, "
                          f"max. {tx.max_write_without_response_size} Byte pro Paket.")

    async def _pair_and_open(self, client: BleakClient, sid: str | None, do_pair: bool):
        if sid:
            self._step(sid, "active")
        if do_pair:
            await self._do_pair(client, sid)
        self._rx_event = asyncio.Event()
        try:
            await self._ensure_connected(client)
            await asyncio.wait_for(client.start_notify(self._rx_char, self._on_rx), 60)
        except ProcessError:
            raise
        except Exception as exc:
            if not _is_auth_error(exc):
                raise ProcessError(f"Datenkanal konnte nicht geöffnet werden ({exc}).")
            self._auth_failed.add(client.address)
            if not winpair.AVAILABLE:
                raise ProcessError(self._auth_text(exc))
            # Einmal automatisch: alte Kopplung entfernen, neu koppeln, erneut öffnen
            self._log("warn", "Das Modul verlangt eine (neue) Kopplung – wird automatisch hergestellt …")
            await self._fresh_pair(client, sid)
            try:
                await self._ensure_connected(client)
                await asyncio.wait_for(client.start_notify(self._rx_char, self._on_rx), 60)
            except Exception as exc2:
                raise ProcessError(self._auth_text(exc2))
            self._auth_failed.discard(client.address)
            do_pair = True
        if sid:
            self._step(sid, "done", "gekoppelt" if do_pair else "")

    async def _do_pair(self, client: BleakClient, sid: str | None):
        name = self._cur_name or client.address
        if sys.platform == "darwin":
            # macOS koppelt selbst beim ersten geschützten Zugriff und zeigt ggf. einen Dialog
            self._show("user", "KOPPLUNG BESTÄTIGEN",
                       "Falls macOS einen Kopplungsdialog anzeigt: bitte „Verbinden“ bzw. "
                       "„Koppeln“ bestätigen.",
                       hint="Der Ablauf läuft danach automatisch weiter.", step=sid or "")
            return
        if not winpair.AVAILABLE:
            try:
                await asyncio.wait_for(client.pair(), 60)
            except Exception as exc:
                self._log("warn", f"Kopplung nicht möglich oder nicht nötig ({exc}) – fahre fort.")
            return

        self._show("auto", "KOPPLUNG", f"Kopplung mit „{name}“ wird hergestellt …",
                   hint=f"Wird automatisch bestätigt. Fragt das Modul nach einem Passkey, wird "
                        f"„{self.s.passkey}“ eingegeben (änderbar in den Einstellungen).",
                   step=sid or "")
        await self._ensure_connected(client)
        try:
            status, kinds = await asyncio.wait_for(
                winpair.pair(client.address, self.s.passkey, self._log), 60)
        except asyncio.TimeoutError:
            raise ProcessError("Kopplung: keine Antwort vom Modul (Zeitüberschreitung nach 60 s).")
        except Exception as exc:
            raise ProcessError(f"Kopplung fehlgeschlagen ({exc.__class__.__name__}: {exc}).")
        if kinds:
            self._log("info", "Angefragte Kopplungsart: " + ", ".join(kinds))
        if status == "PAIRED":
            self._log("ok", "Kopplung hergestellt.")
        elif status == "ALREADY_PAIRED":
            self._log("info", "Windows meldet: bereits gekoppelt.")
        else:
            self._auth_failed.add(client.address)
            hints = {
                "AUTHENTICATION_FAILURE": " Passkey falsch? In den Einstellungen prüfen.",
                "AUTHENTICATION_TIMEOUT": " Das Modul hat nicht rechtzeitig geantwortet.",
                "CONNECTION_REJECTED": " Das Modul hat die Verbindung abgelehnt.",
                "REJECTED_BY_HANDLER": " Kopplungsart wird nicht unterstützt.",
                "PAIRING_CANCELED": " Kopplung wurde abgebrochen.",
            }
            raise ProcessError(f"Kopplung fehlgeschlagen (Windows-Status: {status})."
                               + hints.get(status, "")
                               + " Beim Wiederholen wird eine evtl. gespeicherte Kopplung entfernt.")
        await self._ensure_connected(client)

    async def _fresh_pair(self, client: BleakClient, sid: str | None):
        """Windows: gespeicherte Kopplung entfernen (falls vorhanden) und neu koppeln."""
        addr = client.address
        try:
            paired = await winpair.is_paired(addr)
        except Exception:
            paired = False
        if paired:
            self._log("warn", "Windows hat noch eine alte Kopplung gespeichert – wird entfernt …")
            self._expect_disconnect = True
            try:
                await client.disconnect()
            except Exception:
                pass
            try:
                self._log("info", f"Alte Kopplung entfernt ({await winpair.unpair(addr)}).")
            except Exception as exc:
                self._log("warn", f"Alte Kopplung konnte nicht entfernt werden ({exc}).")
            await asyncio.sleep(1.5)
        await self._ensure_connected(client)
        await self._do_pair(client, sid)

    async def _ensure_connected(self, client: BleakClient):
        """Trennt das Modul z. B. während der Kopplung, wird einmal neu verbunden."""
        if client.is_connected:
            return
        name = self._cur_name or client.address
        self._log("info", f"Verbindung zu „{name}“ wird wiederhergestellt …")
        self._expect_disconnect = False
        try:
            await client.connect()
        except Exception as exc:
            raise ProcessError(f"Verbindung zu „{name}“ verloren und nicht wiederherstellbar ({exc}).")
        await self._verify_proteus(client, name)

    def _auth_text(self, exc) -> str:
        name = self._cur_name or "Modul"
        base = (f"Das Modul hat den Zugriff abgelehnt ({exc}). Meist ist auf dem Rechner noch eine "
                f"alte Kopplung gespeichert, die das Modul nicht mehr kennt (z. B. weil es "
                f"zwischendurch mit dem Handy gekoppelt war).")
        if sys.platform == "darwin":
            return (base + f" Bitte in Systemeinstellungen → Bluetooth das Gerät „{name}“ entfernen "
                           f"(„Ignorieren“) und dann wiederholen.")
        return base + " Beim Wiederholen wird sie automatisch entfernt und neu gekoppelt."

    def _on_rx(self, _char, data: bytearray):
        payload = bytes(data)
        if self.s.proteus_header and payload[:1] == PROTEUS_DATA_HEADER:
            payload = payload[1:]
        text = payload.decode("utf-8", errors="replace")
        self._rx_buf += text
        self._log("rx", _visible(text))
        if self._rx_event:
            self._rx_event.set()

    async def _send(self, client: BleakClient, text: str):
        if not client.is_connected:
            raise ProcessError("Verbindung zum Modul ist abgerissen.")
        s = self.s
        data = (text + s.line_ending_chars).encode("utf-8")
        hdr = PROTEUS_DATA_HEADER if s.proteus_header else b""
        tx = self._tx_char
        with_response = "write" in tx.properties
        room = max(1, tx.max_write_without_response_size - len(hdr))
        chunks = [data[i:i + room] for i in range(0, len(data), room)] or [b""]
        if len(chunks) > 1:
            self._log("warn", f"Nachricht ist länger als ein Paket – wird in {len(chunks)} Teilen gesendet.")
        self._log("tx", _visible(text + s.line_ending_chars))
        for chunk in chunks:
            await client.write_gatt_char(tx, hdr + chunk, response=with_response)

    async def _wait_for_mac(self, timeout: float) -> str | None:
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while True:
            m = MAC_LINE_RE.search(self._rx_buf) or MAC_RE.search(self._rx_buf)
            if m:
                await asyncio.sleep(0.2)  # evtl. folgende Teilpakete abwarten
                m = MAC_LINE_RE.search(self._rx_buf) or MAC_RE.search(self._rx_buf)
                return m.group(1)
            rest = end - loop.time()
            if rest <= 0:
                return None
            self._rx_event.clear()
            try:
                await asyncio.wait_for(self._rx_event.wait(), rest)
            except asyncio.TimeoutError:
                pass

    async def _finish_client(self, client: BleakClient):
        self._expect_disconnect = True
        if self.s.unpair_after and sys.platform != "darwin":
            try:
                await client.unpair()
                self._log("info", "Kopplung am Rechner wieder entfernt.")
            except Exception as exc:
                self._log("warn", f"Kopplung konnte nicht entfernt werden ({exc}).")
        try:
            await client.disconnect()
        except Exception:
            pass
        if client in self._clients:
            self._clients.remove(client)
        self._log("info", "Verbindung getrennt.")

    async def _cleanup(self):
        self._expect_disconnect = True
        for c in list(self._clients):
            try:
                await asyncio.wait_for(c.disconnect(), 5)
            except Exception:
                pass
        self._clients.clear()

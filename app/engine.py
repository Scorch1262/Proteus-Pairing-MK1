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
import re
import sys
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

from .config import Settings, append_history, now_str

# Würth Elektronik Proteus-II – SPP-ähnliches BLE-Profil
PROTEUS_SERVICE = "6e400001-c352-11e5-953d-0002a5d5c51b"
PROTEUS_TX_CHAR = "6e400002-c352-11e5-953d-0002a5d5c51b"  # PC -> Modul (Write)
PROTEUS_RX_CHAR = "6e400003-c352-11e5-953d-0002a5d5c51b"  # Modul -> PC (Notify)
PROTEUS_DATA_HEADER = b"\x01"

MAC_RE = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")
MAC_LINE_RE = re.compile(r"MAC\s*:?\s*([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", re.IGNORECASE)


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
        Step("h_scan", "A", f"„{s.marker_host}“-Modul suchen", False, "3"),
        Step("h_wait", "A", f"Startzeit abwarten (ca. {s.boot_wait_s:g} s)", False, "2"),
        Step("h_connect", "A", "Verbinden · Proteus-II-Profil", False, "4"),
        Step("h_pair", "A", "Kopplung bestätigen", False, "5"),
        Step("h_cmd", "A", f"„{s.cmd_host_mac}“ senden", False, "6"),
        Step("h_mac", "A", "MAC-Adresse auslesen & merken", False, "7–8"),
        Step("p_power", "B", "PTT-Taste halten + PTT-Modul einschalten", True, "9"),
        Step("p_scan", "B", f"„{s.marker_ptt}“-Modul suchen", False, "11"),
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
                        f"„{s.marker_host}“ im Namen und fährt fort, sobald es gefunden wurde.",
                   step="h_power")
        dev, adv, name = await self._scan("host", exclude=set())
        self._step("h_power", "done")
        self._step("h_scan", "done", name)
        self.host_info = dict(name=name, address=dev.address, rssi=adv.rssi)
        self.ui.on_device("host", self.host_info)

        await self._countdown("h_wait", "Haupt-Modul startet …")

        self._step("h_connect", "active", "verbinde …")
        self._show("auto", "AUTOMATISCH", f"Verbinde mit „{name}“ …",
                   hint="Proteus-II-Profil wird automatisch ausgewählt.", step="h_connect")
        client = await self._connect(dev, name)
        self._step("h_connect", "done", "Proteus-II-Profil gefunden")

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
        dev, adv, name = await self._scan("ptt", exclude=exclude)
        self._step("p_power", "done")
        self._step("p_scan", "done", name)
        self.ptt_info = dict(name=name, address=dev.address, rssi=adv.rssi)
        self.ui.on_device("ptt", self.ptt_info)

        await self._countdown("p_wait", "PTT-Modul startet …")

        self._step("p_connect", "active", "verbinde …")
        self._show("auto", "AUTOMATISCH", f"Verbinde mit „{name}“ …",
                   hint="Proteus-II-Profil wird automatisch ausgewählt.", step="p_connect")
        client = await self._connect(dev, name)
        self._step("p_connect", "done", "Proteus-II-Profil gefunden")
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
    async def _scan(self, role: str, exclude: set[str]):
        s = self.s
        found: dict[str, tuple] = {}
        hit = asyncio.Event()

        def detected(device, adv):
            name = adv.local_name or device.name or ""
            if device.address in exclude or role_of(name, s) != role:
                return
            first = device.address not in found
            found[device.address] = (device, adv, name)
            if first:
                has_uuid = PROTEUS_SERVICE in [u.lower() for u in (adv.service_uuids or [])]
                self._log("info", f"Gefunden: {name}  [{device.address}]  {adv.rssi} dBm"
                                  + ("  · Proteus-UUID" if has_uuid else ""))
            hit.set()

        scanner = BleakScanner(detection_callback=detected)
        try:
            await scanner.start()
        except Exception as exc:
            raise ProcessError(f"Bluetooth-Suche konnte nicht gestartet werden ({exc}). "
                               f"Ist Bluetooth am Rechner eingeschaltet?")
        self._log("info", f"Suche nach Modul mit „{s.marker_host if role == 'host' else s.marker_ptt}“ …")
        try:
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            while not hit.is_set():
                el = loop.time() - t0
                if el >= s.scan_timeout_s:
                    raise ProcessError(
                        f"Kein Modul mit „{s.marker_host if role == 'host' else s.marker_ptt}“ im Namen "
                        f"innerhalb von {s.scan_timeout_s:g} s gefunden.")
                self.ui.on_progress(0, 0)
                try:
                    await asyncio.wait_for(hit.wait(), 0.5)
                except asyncio.TimeoutError:
                    pass
            await asyncio.sleep(1.5)  # weitere Kandidaten kurz sammeln
        finally:
            try:
                await scanner.stop()
            except Exception:
                pass

        def key(item):
            dev, adv, _ = item
            has_uuid = PROTEUS_SERVICE in [u.lower() for u in (adv.service_uuids or [])]
            return (has_uuid, adv.rssi if adv.rssi is not None else -999)

        candidates = sorted(found.values(), key=key, reverse=True)
        if len(candidates) > 1:
            self._log("warn", f"{len(candidates)} passende Module gefunden – nehme das stärkste Signal: "
                              f"{candidates[0][2]} ({candidates[0][1].rssi} dBm)")
        return candidates[0]

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
        return client

    async def _pair_and_open(self, client: BleakClient, sid: str | None, do_pair: bool):
        if sid:
            self._step(sid, "active")
        if do_pair:
            if sys.platform == "darwin":
                self._show("user", "KOPPLUNG BESTÄTIGEN",
                           "Falls macOS einen Kopplungsdialog anzeigt: bitte „Verbinden“ bzw. "
                           "„Koppeln“ bestätigen.",
                           hint="Der Ablauf läuft danach automatisch weiter.", step=sid or "")
            else:
                self._show("user", "KOPPLUNG BESTÄTIGEN",
                           "Kopplung wird angefordert. Falls Windows eine Meldung zum Koppeln "
                           "anzeigt: bitte bestätigen.",
                           hint="Der Ablauf läuft danach automatisch weiter.", step=sid or "")
                try:
                    await asyncio.wait_for(client.pair(), 60)
                    self._log("ok", "Kopplung bestätigt.")
                except NotImplementedError:
                    pass
                except Exception as exc:
                    self._log("warn", f"Kopplung nicht möglich oder nicht nötig ({exc}) – fahre fort.")
        self._rx_event = asyncio.Event()
        try:
            await asyncio.wait_for(client.start_notify(self._rx_char, self._on_rx), 60)
        except Exception as exc:
            raise ProcessError(f"Datenkanal konnte nicht geöffnet werden ({exc}). "
                               f"Wurde die Kopplung abgelehnt?")
        if sid:
            self._step(sid, "done", "gekoppelt" if do_pair else "")

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

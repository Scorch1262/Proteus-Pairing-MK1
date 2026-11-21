"""Hauptfenster von Proteus-Pairing-MK1 (Qt / PySide6)."""
from __future__ import annotations

import asyncio
import html
import re
import sys
import threading
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from . import style
from .config import (
    APP_NAME, APP_VERSION, HISTORY_HEADER, LINE_ENDINGS, Settings, data_dir, load_history,
    resource_path,
)
from .engine import MAC_RE, PairingEngine, build_steps

PHASES = {"A": "PHASE 1 · HOST-MODUL", "B": "PHASE 2 · PTT-MODUL", "C": "PHASE 3 · NEUSTART"}
ICONS = {"pending": None, "active": "▸", "user": "!", "done": "✓", "error": "✕", "skipped": "–"}


def repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)


# ====================================================================== Bluetooth-Thread
class BleThread(threading.Thread):
    """Eigener asyncio-Loop für bleak – hält die Oberfläche flüssig."""

    def __init__(self):
        super().__init__(daemon=True, name="ble-loop")
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()

    def start_and_wait(self):
        self.start()
        self._ready.wait()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, fn, *args):
        self.loop.call_soon_threadsafe(fn, *args)


class Bridge(QObject):
    """Leitet Meldungen der Engine thread-sicher an die Oberfläche."""
    step = Signal(str, str, str)
    action = Signal(dict)
    progress = Signal(int, int)
    log = Signal(str, str)
    device = Signal(str, object)
    mac = Signal(str)
    finished = Signal(str, str)

    # Engine-Schnittstelle
    def on_step(self, sid, state, detail): self.step.emit(sid, state, detail)
    def on_action(self, d): self.action.emit(d)
    def on_progress(self, v, m): self.progress.emit(v, m)
    def on_log(self, kind, text): self.log.emit(kind, text)
    def on_device(self, role, info): self.device.emit(role, info)
    def on_mac(self, mac): self.mac.emit(mac)
    def on_finished(self, result, summary): self.finished.emit(result, summary)


# ====================================================================== Bausteine
def panel(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("panel")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(6)
    if title:
        t = QLabel(title)
        t.setObjectName("panelTitle")
        lay.addWidget(t)
    return f, lay


class StepRow(QFrame):
    def __init__(self, number: int, title: str, ref: str, user: bool):
        super().__init__()
        self.setObjectName("stepRow")
        self.number = number
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(9)
        self.icon = QLabel(str(number))
        self.icon.setObjectName("stepIcon")
        self.icon.setFixedSize(22, 22)
        self.icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.title = QLabel(title)
        self.title.setObjectName("stepTitle")
        self.title.setWordWrap(True)
        top.addWidget(self.title, 1)
        if user:
            tag = QLabel("NUTZER")
            tag.setObjectName("userTag")
            tag.setToolTip("Dieser Schritt erfordert eine Handlung von Ihnen.")
            top.addWidget(tag, 0, Qt.AlignTop)
        col.addLayout(top)
        self.detail = QLabel("")
        self.detail.setObjectName("stepDetail")
        self.detail.setVisible(False)
        col.addWidget(self.detail)
        lay.addLayout(col, 1)
        r = QLabel(f"Anl. {ref}")
        r.setObjectName("stepRef")
        r.setToolTip(f"Entspricht Schritt {ref} der Paarungsanleitung")
        lay.addWidget(r, 0, Qt.AlignTop)
        self.set_state("pending")

    def set_state(self, state: str, detail: str = ""):
        for w in (self, self.icon, self.title):
            w.setProperty("state", state)
            repolish(w)
        sym = ICONS.get(state)
        self.icon.setText(sym if sym else str(self.number))
        if detail or state == "pending":
            self.detail.setText(detail)
            self.detail.setVisible(bool(detail))


class DeviceCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        t = QLabel(title)
        t.setObjectName("panelTitle")
        lay.addWidget(t)
        self.name = QLabel("–")
        self.name.setObjectName("value")
        self.name.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.name.setWordWrap(True)
        self.addr = QLabel("Adresse: –")
        self.addr.setObjectName("muted")
        self.rssi = QLabel("Signal: –")
        self.rssi.setObjectName("muted")
        for w in (self.name, self.addr, self.rssi):
            lay.addWidget(w)
        lay.addStretch(1)

    def set_info(self, info: dict | None):
        if not info:
            self.name.setText("–")
            self.addr.setText("Adresse: –")
            self.rssi.setText("Signal: –")
            return
        self.name.setText(info.get("name", "–"))
        self.addr.setText(f"Adresse: {info.get('address', '–')}")
        rssi = info.get("rssi")
        self.rssi.setText(f"Signal: {rssi} dBm" if rssi is not None else "Signal: –")


# ====================================================================== Einstellungen
class SettingsDialog(QDialog):
    def __init__(self, parent, s: Settings):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(520)
        self.s = s
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 8, 0)

        g1 = QGroupBox("ERKENNUNG")
        f1 = QFormLayout(g1)
        self.m_host = QLineEdit(s.marker_host)
        self.m_ptt = QLineEdit(s.marker_ptt)
        f1.addRow("Marke Host-Modul:", self.m_host)
        f1.addRow("Marke PTT-Modul:", self.m_ptt)
        hint = QLabel("Groß-/Kleinschreibung egal. Enthält ein Name beide Marken, gilt er als Host.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        f1.addRow(hint)
        self.ident = QCheckBox("Gekürzte Namen per kurzer Verbindung prüfen")
        self.ident.setChecked(s.identify_by_connect)
        self.ident.setToolTip("Proteus-Module senden in der Suche oft nur einen gekürzten Namen (z. B. „Albre“).\n"
                              "Geprüft werden Geräte mit Proteus-UUID oder Würth-Adresse 00:18:DA.")
        f1.addRow(self.ident)
        self.prefix = QLineEdit(s.name_prefix)
        self.prefix.setPlaceholderText("optional, z. B. Albre")
        self.prefix.setToolTip("Zusätzlich alle Geräte prüfen, deren (gekürzter) Name so beginnt –\n"
                               "nötig z. B. unter macOS, wenn das Modul keine Proteus-UUID sendet.")
        f1.addRow("Namensanfang prüfen:", self.prefix)
        root.addWidget(g1)

        g2 = QGroupBox("BEFEHLE")
        f2 = QFormLayout(g2)
        self.c_mac = QLineEdit(s.cmd_host_mac)
        self.c_ptt = QLineEdit(s.cmd_ptt_prefix)
        self.le = QComboBox()
        self.le.addItems(list(LINE_ENDINGS))
        self.le.setCurrentText(s.line_ending)
        self.hdr = QCheckBox("Proteus-II-Datenheader 0x01 verwenden")
        self.hdr.setChecked(s.proteus_header)
        f2.addRow("MAC-Abfrage am Host:", self.c_mac)
        f2.addRow("Präfix am PTT-Modul:", self.c_ptt)
        self.c_conf = QLineEdit(s.ptt_confirm)
        self.c_conf.setPlaceholderText("leer = nicht prüfen")
        self.c_conf.setToolTip("Text, den das PTT-Modul nach dem Speichern zurückschickt\n"
                               "(z. B. „Neue Host MAC gespeichert“). Ohne diese Antwort gilt die Paarung als fehlgeschlagen.")
        f2.addRow("Bestätigung PTT-Modul:", self.c_conf)
        f2.addRow("Zeilenende:", self.le)
        f2.addRow(self.hdr)
        root.addWidget(g2)

        g3 = QGroupBox("ZEITEN")
        f3 = QFormLayout(g3)
        self.boot = self._dspin(s.boot_wait_s, 0, 60, " s")
        self.scan = self._dspin(s.scan_timeout_s, 5, 900, " s")
        self.resp = self._dspin(s.response_timeout_s, 1, 60, " s")
        self.pttw = self._dspin(s.ptt_reply_wait_s, 0, 30, " s")
        self.retr = QSpinBox()
        self.retr.setRange(1, 10)
        self.retr.setValue(s.retries)
        f3.addRow("Startzeit nach Erkennen:", self.boot)
        f3.addRow("Max. Suchdauer:", self.scan)
        self.sdelay = self._dspin(s.send_delay_s, 0, 10, " s")
        f3.addRow("Wartezeit vor dem Senden:", self.sdelay)
        f3.addRow("Antwort-Timeout:", self.resp)
        f3.addRow("Nachlauf PTT-Antwort:", self.pttw)
        f3.addRow("Wiederholungen:", self.retr)
        root.addWidget(g3)

        g4 = QGroupBox("KOPPLUNG && ABLAUF")
        v4 = QVBoxLayout(g4)
        self.p_host = QCheckBox("Kopplung mit Host-Modul anfordern (Schritt 5)")
        self.p_host.setChecked(s.pair_host)
        self.p_ptt = QCheckBox("Kopplung auch mit PTT-Modul anfordern")
        self.p_ptt.setChecked(s.pair_ptt)
        self.unpair = QCheckBox("Kopplung am Rechner danach wieder entfernen (Windows)")
        self.unpair.setChecked(s.unpair_after)
        self.fresh = QCheckBox("Vorhandene Windows-Kopplung vorher entfernen und neu koppeln")
        self.fresh.setChecked(s.repair_fresh)
        self.fresh.setToolTip("Empfohlen: Wurde das Modul zwischendurch z. B. mit dem Handy gekoppelt,\n"
                              "kennt es die alte Kopplung des PCs nicht mehr (Insufficient Authentication).")
        pk_row = QHBoxLayout()
        pk_lbl = QLabel("Passkey (falls verlangt):")
        self.passkey = QLineEdit(s.passkey)
        self.passkey.setMaximumWidth(140)
        pk_row.addWidget(pk_lbl)
        pk_row.addWidget(self.passkey)
        pk_row.addStretch(1)
        self.fresh_ptt = QCheckBox("PTT-Modul erst nach Aus-/Einschalten verwenden (Einstellmodus)")
        self.fresh_ptt.setChecked(s.ptt_require_fresh)
        self.fresh_ptt.setToolTip("Ist das PTT-Modul beim Start von Phase 2 schon eingeschaltet (Normalbetrieb),\n"
                                  "wartet das Programm, bis es mit gedrückter PTT-Taste neu eingeschaltet wurde.")
        self.confirm = QCheckBox("Neustart-Schritte 14–17 einzeln bestätigen")
        self.confirm.setChecked(s.confirm_restart_steps)
        for w in (self.p_host, self.p_ptt, self.fresh):
            v4.addWidget(w)
        v4.addLayout(pk_row)
        for w in (self.unpair, self.fresh_ptt, self.confirm):
            v4.addWidget(w)
        root.addWidget(g4)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.button(QDialogButtonBox.Save).setText("Speichern")
        bb.button(QDialogButtonBox.Save).setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.button(QDialogButtonBox.RestoreDefaults).setText("Standardwerte")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        outer.addWidget(bb)
        # Höhe an den Bildschirm anpassen (Laptop mit Skalierung)
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry().height() if screen else 900
        self.resize(560, min(inner.sizeHint().height() + 90, int(avail * 0.85)))

    @staticmethod
    def _dspin(val, lo, hi, suffix):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(1)
        w.setSuffix(suffix)
        w.setValue(val)
        return w

    def _defaults(self):
        d = Settings()
        self.m_host.setText(d.marker_host); self.m_ptt.setText(d.marker_ptt)
        self.ident.setChecked(d.identify_by_connect); self.prefix.setText(d.name_prefix)
        self.c_mac.setText(d.cmd_host_mac); self.c_ptt.setText(d.cmd_ptt_prefix)
        self.le.setCurrentText(d.line_ending); self.hdr.setChecked(d.proteus_header)
        self.boot.setValue(d.boot_wait_s); self.scan.setValue(d.scan_timeout_s)
        self.resp.setValue(d.response_timeout_s); self.pttw.setValue(d.ptt_reply_wait_s)
        self.retr.setValue(d.retries); self.p_host.setChecked(d.pair_host)
        self.p_ptt.setChecked(d.pair_ptt); self.unpair.setChecked(d.unpair_after)
        self.confirm.setChecked(d.confirm_restart_steps)
        self.fresh.setChecked(d.repair_fresh); self.passkey.setText(d.passkey)
        self.c_conf.setText(d.ptt_confirm); self.sdelay.setValue(d.send_delay_s)
        self.fresh_ptt.setChecked(d.ptt_require_fresh)

    def result_settings(self) -> Settings:
        s = Settings(
            marker_host=self.m_host.text().strip() or "Host",
            marker_ptt=self.m_ptt.text().strip() or "PTT",
            identify_by_connect=self.ident.isChecked(),
            name_prefix=self.prefix.text().strip(),
            cmd_host_mac=self.c_mac.text() or "BT-MAC?",
            cmd_ptt_prefix=self.c_ptt.text() or "Host:",
            line_ending=self.le.currentText(),
            proteus_header=self.hdr.isChecked(),
            boot_wait_s=self.boot.value(),
            scan_timeout_s=self.scan.value(),
            response_timeout_s=self.resp.value(),
            retries=self.retr.value(),
            ptt_reply_wait_s=self.pttw.value(),
            pair_host=self.p_host.isChecked(),
            pair_ptt=self.p_ptt.isChecked(),
            unpair_after=self.unpair.isChecked(),
            confirm_restart_steps=self.confirm.isChecked(),
            repair_fresh=self.fresh.isChecked(),
            passkey=self.passkey.text().strip() or "123123",
            ptt_confirm=self.c_conf.text().strip(),
            send_delay_s=self.sdelay.value(),
            ptt_require_fresh=self.fresh_ptt.isChecked(),
        )
        return s


# ====================================================================== Hauptfenster
class MainWindow(QMainWindow):
    def __init__(self, ble: BleThread | None):
        super().__init__()
        self.ble = ble
        self.settings = Settings.load()
        self.engine: PairingEngine | None = None
        self.future = None
        self.rows: dict[str, StepRow] = {}
        self.current_mac = ""
        self.bridge = Bridge()
        self.bridge.step.connect(self._on_step)
        self.bridge.action.connect(self._on_action)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.log.connect(self._on_log)
        self.bridge.device.connect(self._on_device)
        self.bridge.mac.connect(self._on_mac)
        self.bridge.finished.connect(self._on_finished)

        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        icon = resource_path("assets/icon.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1240, 820)
        self.setMinimumSize(1020, 680)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(14, 14, 14, 14)
        body.setSpacing(14)
        outer.addLayout(body, 1)
        body.addWidget(self._build_steps_panel(), 0)
        right = QVBoxLayout()
        right.setSpacing(14)
        body.addLayout(right, 1)
        right.addWidget(self._build_action_card())
        right.addLayout(self._build_cards())
        right.addWidget(self._build_tabs(), 1)

        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(550)
        self.blink_timer.timeout.connect(self._blink)
        self._blink_on = False

        self._show_idle()
        self._log_line("info", f"{APP_NAME} v{APP_VERSION} bereit.")
        if ble is None:
            self._log_line("warn", "Bluetooth-Thread nicht aktiv (Demo-Modus).")

    # ------------------------------------------------------------------ Aufbau
    def _build_header(self):
        h = QFrame()
        h.setObjectName("header")
        h.setFixedHeight(64)
        lay = QHBoxLayout(h)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)
        logo = QLabel("P")
        logo.setObjectName("logo")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel("PROTEUS PAIRING")
        t.setObjectName("appTitle")
        sub = QLabel(f"MK1 · v{APP_VERSION} · HOST ⇄ PTT · WÜRTH PROTEUS-II")
        sub.setObjectName("appSub")
        col.addWidget(t)
        col.addWidget(sub)
        lay.addLayout(col)
        lay.addStretch(1)

        self.status = QLabel("BEREIT")
        self.status.setObjectName("statusPill")
        self.status.setFixedHeight(24)
        self.status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status, 0, Qt.AlignVCenter)
        lay.addSpacing(10)

        self.btn_start = QPushButton("▶  START")
        self.btn_start.setObjectName("primary")
        self.btn_start.setToolTip("Kompletten Paarungsablauf starten (Host + PTT)")
        self.btn_start.clicked.connect(lambda: self.start("full"))
        self.btn_ptt = QPushButton("NUR PTT")
        self.btn_ptt.setToolTip("Host-MAC von Hand eingeben und nur das PTT-Modul konfigurieren")
        self.btn_ptt.clicked.connect(self._start_ptt_only)
        self.btn_abort = QPushButton("ABBRECHEN")
        self.btn_abort.setObjectName("danger")
        self.btn_abort.clicked.connect(self.abort)
        self.btn_settings = QPushButton("⚙  EINSTELLUNGEN")
        self.btn_settings.clicked.connect(self._open_settings)
        for b in (self.btn_start, self.btn_ptt, self.btn_abort, self.btn_settings):
            lay.addWidget(b)
        return h

    def _build_steps_panel(self):
        f, lay = panel("ABLAUF")
        f.setFixedWidth(360)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        inner = QWidget()
        self.steps_layout = QVBoxLayout(inner)
        self.steps_layout.setContentsMargins(0, 0, 4, 0)
        self.steps_layout.setSpacing(2)
        scroll.setWidget(inner)
        self.steps_scroll = scroll
        lay.addWidget(scroll, 1)
        self._rebuild_steps()
        return f

    def _rebuild_steps(self):
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows.clear()
        phase = None
        for i, st in enumerate(build_steps(self.settings), 1):
            if st.phase != phase:
                phase = st.phase
                lbl = QLabel(PHASES[phase])
                lbl.setObjectName("phaseTitle")
                self.steps_layout.addWidget(lbl)
            row = StepRow(i, st.title, st.ref, st.user)
            self.rows[st.id] = row
            self.steps_layout.addWidget(row)
        self.steps_layout.addStretch(1)

    def _build_action_card(self):
        self.card = QFrame()
        self.card.setObjectName("actionCard")
        self.card.setMinimumHeight(210)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(8)
        top = QHBoxLayout()
        self.a_mode = QLabel()
        self.a_mode.setObjectName("actionMode")
        self.a_step = QLabel()
        self.a_step.setObjectName("actionStep")
        top.addWidget(self.a_mode)
        top.addStretch(1)
        top.addWidget(self.a_step)
        lay.addLayout(top)
        self.a_text = QLabel()
        self.a_text.setObjectName("actionText")
        self.a_text.setWordWrap(True)
        lay.addWidget(self.a_text)
        self.a_hint = QLabel()
        self.a_hint.setObjectName("actionHint")
        self.a_hint.setWordWrap(True)
        lay.addWidget(self.a_hint)
        lay.addStretch(1)
        self.a_progress = QProgressBar()
        self.a_progress.setFixedHeight(6)
        self.a_progress.setTextVisible(False)
        lay.addWidget(self.a_progress)
        self.a_buttons = QHBoxLayout()
        self.a_buttons.setSpacing(10)
        lay.addLayout(self.a_buttons)
        return self.card

    def _build_cards(self):
        row = QHBoxLayout()
        row.setSpacing(14)
        self.card_host = DeviceCard("HOST-MODUL")
        row.addWidget(self.card_host, 1)

        mac_frame, ml = panel("HOST-MAC-ADRESSE")
        self.mac_label = QLabel("––:––:––:––:––:––")
        self.mac_label.setObjectName("bigMac")
        self.mac_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ml.addWidget(self.mac_label)
        mrow = QHBoxLayout()
        self.btn_copy = QPushButton("KOPIEREN")
        self.btn_copy.setObjectName("small")
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy_mac)
        mrow.addWidget(self.btn_copy)
        mrow.addStretch(1)
        ml.addLayout(mrow)
        ml.addStretch(1)
        row.addWidget(mac_frame, 1)

        self.card_ptt = DeviceCard("PTT-MODUL")
        row.addWidget(self.card_ptt, 1)
        return row

    def _build_tabs(self):
        self.tabs = QTabWidget()
        log_w = QWidget()
        ll = QVBoxLayout(log_w)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        ll.addWidget(self.log, 1)
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        legend = QLabel(
            f'<span style="color:{style.AMBER}">TX</span> gesendet &nbsp; '
            f'<span style="color:{style.TEAL}">RX</span> empfangen')
        legend.setObjectName("muted")
        bar.addWidget(legend)
        bar.addStretch(1)
        b1 = QPushButton("LEEREN")
        b1.setObjectName("small")
        b1.clicked.connect(self.log.clear)
        b2 = QPushButton("SPEICHERN …")
        b2.setObjectName("small")
        b2.clicked.connect(self._save_log)
        bar.addWidget(b1)
        bar.addWidget(b2)
        ll.addLayout(bar)
        self.tabs.addTab(log_w, "PROTOKOLL")

        self.hist = QTableWidget(0, len(HISTORY_HEADER))
        self.hist.setHorizontalHeaderLabels(HISTORY_HEADER)
        self.hist.verticalHeader().setVisible(False)
        self.hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabs.addTab(self.hist, "VERLAUF")
        self._load_history()
        return self.tabs

    # ------------------------------------------------------------------ Steuerung
    def _running(self) -> bool:
        return self.future is not None and not self.future.done()

    def _set_running(self, on: bool):
        self.btn_start.setEnabled(not on)
        self.btn_ptt.setEnabled(not on)
        self.btn_settings.setEnabled(not on)
        self.btn_abort.setEnabled(on)

    def start(self, mode: str, manual_mac: str | None = None):
        if self._running() or self.ble is None:
            return
        self._rebuild_steps()
        self.card_host.set_info(None)
        self.card_ptt.set_info(None)
        self.mac_label.setText("––:––:––:––:––:––")
        self.btn_copy.setEnabled(False)
        self.current_mac = ""
        self.engine = PairingEngine(self.bridge, self.settings)
        self._log_line("info", "─" * 46)
        self._log_line("info", "Neuer Durchlauf gestartet" + (" (nur PTT)" if mode == "ptt" else ""))
        self.future = self.ble.submit(self.engine.run(mode, manual_mac))
        self._set_running(True)

    def _start_ptt_only(self):
        mac, ok = QInputDialog.getText(
            self, "Nur PTT-Modul", "MAC-Adresse des Host-Moduls (z. B. 00:18:DA:12:34:56):",
            text=self.current_mac or "00:18:DA:")
        if not ok:
            return
        mac = mac.strip()
        if not re.fullmatch(MAC_RE.pattern, mac):
            QMessageBox.warning(self, "Ungültige Eingabe", "Bitte eine MAC-Adresse im Format XX:XX:XX:XX:XX:XX eingeben.")
            return
        self.start("ptt", mac)

    def abort(self):
        if self._running():
            self.future.cancel()

    def respond(self, choice: str):
        if self.engine and self.ble:
            self.ble.call(self.engine.respond, choice)

    # ------------------------------------------------------------------ Signale
    def _on_step(self, sid, state, detail):
        row = self.rows.get(sid)
        if row:
            row.set_state(state, detail)
            if state in ("active", "user", "error"):
                self.steps_scroll.ensureWidgetVisible(row, 0, 40)

    def _on_action(self, d: dict):
        mode = d.get("mode", "idle")
        labels = {
            "idle": "BEREIT", "auto": "●  AUTOMATISCH",
            "user": "⚠  " + d.get("title", "NUTZERAKTION ERFORDERLICH"),
            "error": "✕  " + d.get("title", "FEHLER"), "done": "✓  " + d.get("title", "FERTIG"),
        }
        for w in (self.card, self.a_mode, self.a_text, self.a_progress):
            w.setProperty("mode", mode)
        self.card.setProperty("blink", "0")
        for w in (self.card, self.a_mode, self.a_text, self.a_progress):
            repolish(w)
        self.a_mode.setText(labels.get(mode, mode.upper()))
        self.a_text.setText(d.get("text", ""))
        self.a_hint.setText(d.get("hint", ""))
        sid = d.get("step", "")
        self.a_step.setText(f"SCHRITT {self.rows[sid].number:02d} / {len(self.rows):02d}"
                            if sid in self.rows else "")
        if d.get("busy"):
            self.a_progress.setRange(0, 0)
            self.a_progress.setVisible(True)
        elif mode in ("auto",):
            self.a_progress.setRange(0, 100)
            self.a_progress.setValue(0)
            self.a_progress.setVisible(True)
        else:
            self.a_progress.setVisible(False)

        while self.a_buttons.count():
            it = self.a_buttons.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        buttons = d.get("buttons") or []
        if buttons:
            for i, (bid, label) in enumerate(buttons):
                b = QPushButton(label)
                if i == 0:
                    b.setObjectName("amber" if mode == "user" else "primary")
                    b.setDefault(True)
                b.clicked.connect(lambda _=False, x=bid: self.respond(x))
                self.a_buttons.addWidget(b)
            self.a_buttons.addStretch(1)

        if mode == "user":
            self.status.setText("EINGRIFF NÖTIG")
            self._set_pill("user")
            self.blink_timer.start()
            QApplication.beep()
            QApplication.alert(self, 0)
        else:
            self.blink_timer.stop()
            if mode == "error":
                self.status.setText("FEHLER")
                self._set_pill("err")
                QApplication.alert(self, 0)
            elif mode == "auto":
                self.status.setText("LÄUFT")
                self._set_pill("run")

    def _on_progress(self, v, m):
        if m <= 0:
            if self.a_progress.maximum() != 0:
                self.a_progress.setRange(0, 0)
        else:
            self.a_progress.setRange(0, m)
            self.a_progress.setValue(v)
        self.a_progress.setVisible(True)

    def _on_log(self, kind, text):
        self._log_line(kind, text)

    def _on_device(self, role, info):
        (self.card_host if role == "host" else self.card_ptt).set_info(info)

    def _on_mac(self, mac):
        self.current_mac = mac
        self.mac_label.setText(mac)
        self.btn_copy.setEnabled(True)

    def _on_finished(self, result, summary):
        self._set_running(False)
        self.blink_timer.stop()
        self.future = None
        if result == "ok":
            self.status.setText("ERFOLGREICH")
            self._set_pill("ok")
            buttons_text = "Nächstes Paar starten"
            self._add_restart_button(buttons_text)
        elif result == "abort":
            self.status.setText("ABGEBROCHEN")
            self._set_pill("")
            self._add_restart_button("Neu starten")
        else:
            self.status.setText("FEHLER")
            self._set_pill("err")
            self._add_restart_button("Neu starten")
        self._load_history()

    # ------------------------------------------------------------------ Hilfen
    def _add_restart_button(self, label):
        while self.a_buttons.count():
            it = self.a_buttons.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        b = QPushButton("▶  " + label)
        b.setObjectName("primary")
        b.clicked.connect(lambda: self.start("full"))
        self.a_buttons.addWidget(b)
        self.a_buttons.addStretch(1)

    def _show_idle(self):
        self._on_action(dict(
            mode="idle", text="Bereit für die Paarung",
            hint="Mit START wird der Ablauf aus der Paarungsanleitung automatisch abgearbeitet. "
                 "Wenn Sie etwas tun müssen (Modul einschalten, Taste halten …), erscheint das "
                 "hier deutlich in Orange.",
            buttons=[]))
        self._add_restart_button("START")
        self.status.setText("BEREIT")
        self._set_pill("")
        self._set_running(False)

    def _set_pill(self, state):
        self.status.setProperty("state", state)
        repolish(self.status)

    def _blink(self):
        self._blink_on = not self._blink_on
        self.card.setProperty("blink", "1" if self._blink_on else "0")
        repolish(self.card)

    def _log_line(self, kind: str, text: str):
        colors = {"info": style.MUTED, "tx": style.AMBER, "rx": style.TEAL, "ok": style.GREEN,
                  "warn": "#e8c35a", "error": style.RED}
        tags = {"info": "INFO", "tx": "TX ▸", "rx": "◂ RX", "ok": "OK", "warn": "WARN", "error": "FEHLER"}
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        c = colors.get(kind, style.TEXT)
        body_color = style.TEXT if kind in ("tx", "rx", "ok", "error", "warn") else "#9aa6b2"
        self.log.appendHtml(
            f'<span style="color:{style.BORDER_2}">{ts}</span>&nbsp;&nbsp;'
            f'<span style="color:{c};font-weight:700">{tags.get(kind, kind).ljust(6).replace(" ", "&nbsp;")}</span>&nbsp;'
            f'<span style="color:{body_color}">{html.escape(text)}</span>')

    def _save_log(self):
        name = f"pairing-log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Protokoll speichern", str(data_dir() / name),
                                              "Textdateien (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.log.toPlainText())

    def _load_history(self):
        rows = load_history()
        self.hist.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row[:len(HISTORY_HEADER)]):
                item = QTableWidgetItem(val)
                if c == len(HISTORY_HEADER) - 1:
                    item.setForeground(Qt.green if val == "OK" else Qt.yellow if val == "Abgebrochen" else Qt.red)
                self.hist.setItem(r, c, item)

    def _copy_mac(self):
        if self.current_mac:
            QGuiApplication.clipboard().setText(self.current_mac)
            self._log_line("info", f"MAC-Adresse in die Zwischenablage kopiert: {self.current_mac}")

    def _open_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.result_settings()
            self.settings.save()
            self._rebuild_steps()
            self._log_line("info", "Einstellungen gespeichert.")

    def closeEvent(self, ev):
        if self._running():
            r = QMessageBox.question(self, "Beenden", "Der Ablauf läuft noch. Wirklich beenden?")
            if r != QMessageBox.Yes:
                ev.ignore()
                return
            self.future.cancel()
        ev.accept()


def make_app(argv) -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    f = QFont()
    f.setFamilies(["Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "DejaVu Sans"])
    f.setPointSize(10)
    app.setFont(f)
    app.setStyleSheet(style.QSS)
    icon = resource_path("assets/icon.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    return app

"""Startpunkt von Proteus-Pairing-MK1."""
import sys


def main() -> int:
    from app.gui import BleThread, MainWindow, make_app

    app = make_app(sys.argv)
    ble = BleThread()
    ble.start_and_wait()
    win = MainWindow(ble)
    win.show()
    code = app.exec()
    ble.loop.call_soon_threadsafe(ble.loop.stop)
    return code


if __name__ == "__main__":
    sys.exit(main())

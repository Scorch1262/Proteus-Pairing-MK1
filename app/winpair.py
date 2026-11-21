"""Kopplung unter Windows (WinRT) – erweitert gegenüber bleak.

bleak überspringt das Koppeln, sobald Windows das Gerät bereits als gekoppelt
führt, und unterstützt nur „Nur bestätigen“. Proteus-Module, die zwischendurch
mit einem anderen Gerät (z. B. Handy) gekoppelt wurden, kennen die alte
Windows-Kopplung aber nicht mehr -> „Insufficient Authentication“.

Dieses Modul kann
  * eine vorhandene Windows-Kopplung erkennen und entfernen,
  * neu koppeln mit „Nur bestätigen“, Zahlenvergleich und Passkey-Eingabe.
"""
from __future__ import annotations

import sys

AVAILABLE = sys.platform == "win32"


def _addr_int(address: str) -> int:
    return int(address.replace(":", "").replace("-", ""), 16)


async def _device(address: str):
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    return await BluetoothLEDevice.from_bluetooth_address_async(_addr_int(address))


async def _info(dev):
    from winrt.windows.devices.enumeration import DeviceInformation
    # frisches Objekt, sonst ist der Kopplungsstatus evtl. veraltet
    return await DeviceInformation.create_from_id_async(dev.device_information.id)


async def is_paired(address: str) -> bool:
    dev = await _device(address)
    if dev is None:
        return False
    try:
        return bool((await _info(dev)).pairing.is_paired)
    finally:
        dev.close()


async def unpair(address: str) -> str:
    dev = await _device(address)
    if dev is None:
        return "NOT_FOUND"
    try:
        result = await (await _info(dev)).pairing.unpair_async()
        return result.status.name
    finally:
        dev.close()


def _combine(enum_cls, *members):
    value = members[0]
    for m in members[1:]:
        value = value | m
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except Exception:
        return members[0]


async def pair(address: str, passkey: str, log=None) -> tuple[str, list[str]]:
    """Koppelt neu. Rückgabe: (Status-Name, angefragte Kopplungsarten)."""
    from winrt.windows.devices.enumeration import (
        DevicePairingKinds, DevicePairingProtectionLevel, DevicePairingResultStatus,
    )

    dev = await _device(address)
    if dev is None:
        return "NOT_FOUND", []
    info = await _info(dev)
    if info.pairing.is_paired:
        dev.close()
        return "ALREADY_PAIRED", []
    if not info.pairing.can_pair:
        dev.close()
        return "CANNOT_PAIR", []

    kinds = _combine(DevicePairingKinds,
                     DevicePairingKinds.CONFIRM_ONLY,
                     DevicePairingKinds.CONFIRM_PIN_MATCH,
                     DevicePairingKinds.PROVIDE_PIN,
                     DevicePairingKinds.DISPLAY_PIN)
    requested: list[str] = []

    def handler(_sender, args):
        kind = args.pairing_kind
        requested.append(getattr(kind, "name", str(kind)))
        if kind == DevicePairingKinds.PROVIDE_PIN:
            try:
                args.accept(passkey)
            except TypeError:
                args.accept_with_pin(passkey)
        else:
            # Nur bestätigen / Zahlenvergleich / PIN anzeigen -> automatisch bestätigen
            args.accept()

    custom = info.pairing.custom
    token = custom.add_pairing_requested(handler)
    try:
        result = None
        for level in (DevicePairingProtectionLevel.ENCRYPTION_AND_AUTHENTICATION,
                      DevicePairingProtectionLevel.ENCRYPTION):
            result = await custom.pair_with_protection_level_async(kinds, level)
            if result.status != DevicePairingResultStatus.PROTECTION_LEVEL_COULD_NOT_BE_MET:
                break
            if log:
                log("info", f"Schutzstufe {level.name} nicht möglich – versuche niedrigere …")
        else:
            result = await custom.pair_async(kinds)
        return result.status.name, requested
    finally:
        custom.remove_pairing_requested(token)
        dev.close()

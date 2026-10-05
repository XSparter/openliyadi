"""Scansione e sonda BLE per lampade Liyadi/LEDLYD (libreria, niente CLI)."""

import asyncio
import time

from .protocol import TARGET_NAMES

LAMP_SERVICES = ("fff0",)
HINT_SERVICES = ("feff",)


def classify(name: str | None, uuids) -> str:
    """LAMPADA / sospetta / '-' da nome advertising e service UUID."""
    n = (name or "").lower()
    if any(t.lower() in n for t in TARGET_NAMES):
        return "LAMPADA"
    ul = [u.lower() for u in (uuids or [])]
    if any(s in u for s in LAMP_SERVICES for u in ul):
        return "LAMPADA"
    if any(s in u for s in HINT_SERVICES for u in ul):
        return "sospetta"
    return "-"


def adv_to_dict(address: str, name: str | None, adv) -> dict:
    uuids = list(adv.service_uuids) if adv and adv.service_uuids else []
    mfg = {}
    if adv and adv.manufacturer_data:
        mfg = {str(k): bytes(v).hex(" ") for k, v in adv.manufacturer_data.items()}
    return {
        "address": address,
        "name": name or None,
        "rssi": adv.rssi if adv else None,
        "service_uuids": uuids,
        "manufacturer_data": mfg,
        "tx_power": adv.tx_power if adv else None,
        "match": classify(name, uuids),
    }


async def scan_once(timeout: float, on_device=None) -> list:
    """Scansione BLE: ritorna [{address, name, rssi, service_uuids,
    manufacturer_data, tx_power, match}]. on_device(info) opzionale per live."""
    from bleak import BleakScanner

    seen: dict[str, dict] = {}

    def cb(device, adv):
        name = device.name or (adv.local_name if adv else None) or ""
        info = adv_to_dict(device.address, name, adv)
        prev = seen.get(device.address)
        if prev is None or (info["rssi"] is not None and (
                prev["rssi"] is None or info["rssi"] > prev["rssi"])):
            seen[device.address] = info
        if on_device:
            on_device(info, prev is None)

    async with BleakScanner(cb):
        await asyncio.sleep(timeout)
    return list(seen.values())


async def probe_devices(devices: list, per_device_timeout: float = 10.0,
                        on_try=None) -> dict | None:
    """Prova TUTTI i dispositivi (dal segnale piu' forte) finche' uno espone
    FFF0 in GATT = lampada compatibile. Solo lettura + disconnect pulito."""
    from bleak import BleakClient

    ordered = sorted(devices,
                     key=lambda d: (d["rssi"] is not None, d["rssi"] or -999),
                     reverse=True)
    for i, dev in enumerate(ordered, 1):
        addr = dev["address"]
        if on_try:
            on_try(i, len(ordered), dev)
        try:
            async with BleakClient(addr, timeout=per_device_timeout) as client:
                uuids = [s.uuid for s in client.services]
                if any("fff0" in u.lower() for u in uuids):
                    dev["gatt_services"] = uuids
                    dev["match"] = "LAMPADA"
                    return dev
        except Exception:
            pass
    return None


async def watch() -> None:
    """Monitoraggio continuo (stampa solo lampade/sospette)."""
    from bleak import BleakScanner

    t0 = time.time()

    def cb(device, adv):
        name = device.name or (adv.local_name if adv else None) or ""
        uuids = list(adv.service_uuids) if adv and adv.service_uuids else []
        m = classify(name, uuids)
        if m == "-":
            return
        tag = ">>> LAMPADA" if m == "LAMPADA" else " (?) sospetta"
        print(f"[{time.time() - t0:6.1f}s] {tag}: {name or '(senza nome)'} "
              f"[{device.address}] rssi={adv.rssi} uuids={uuids}", flush=True)

    print("Monitoraggio solo lampade/sospette, Ctrl+C per fermare...", flush=True)
    async with BleakScanner(cb):
        while True:
            await asyncio.sleep(3600)

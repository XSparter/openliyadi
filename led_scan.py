#!/usr/bin/env python3
"""
Scanner BLE per lampade Liyadi / LEDLYD (LP540-PRO e compatibili).

Identifica le lampade da advertising:
  - nome: LTF_MWRGB / LYD_MWRGB / Bough_Systems / ... (case-insensitive)
  - service UUID: 0000FFF0-... (controllo GATT reale)
  - hint debole: 0000FEFF-... (la LP540-PRO lo trasmette, ma non e' esclusivo)

Uso:
  python led_scan.py                 # scansione 15s
  python led_scan.py --timeout 30
  python led_scan.py --watch         # monitoraggio continuo
  python led_scan.py --json          # output JSON (una riga per device)
"""

import argparse
import asyncio
import json
import sys
import time

from led_protocol import TARGET_NAMES

LAMP_SERVICES = ("fff0",)
HINT_SERVICES = ("feff",)


def classify(name: str, uuids: list[str]) -> str:
    n = (name or "").lower()
    if any(t.lower() in n for t in TARGET_NAMES):
        return "LAMPADA"
    ul = [u.lower() for u in uuids]
    if any(s in u for s in LAMP_SERVICES for u in ul):
        return "LAMPADA"
    if any(s in u for s in HINT_SERVICES for u in ul):
        return "sospetta"
    return "-"


def adv_to_dict(address: str, name: str, adv) -> dict:
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


async def scan_once(timeout: float, as_json: bool = False) -> list[dict]:
    from bleak import BleakScanner

    seen: dict[str, dict] = {}

    def cb(device, adv):
        name = device.name or (adv.local_name if adv else None) or ""
        info = adv_to_dict(device.address, name, adv)
        prev = seen.get(device.address)
        # tieni il campione con RSSI migliore
        if prev is None or (info["rssi"] is not None and (
                prev["rssi"] is None or info["rssi"] > prev["rssi"])):
            seen[device.address] = info
        if as_json:
            print(json.dumps(info), flush=True)
        elif prev is None:
            mark = {"LAMPADA": ">>> ", "sospetta": " (?) "}.get(info["match"], "     ")
            print(f"{mark}{info['address']}  rssi={info['rssi']}  "
                  f"name={info['name'] or '(senza nome)'}  uuids={info['service_uuids']}",
                  flush=True)

    async with BleakScanner(cb):
        await asyncio.sleep(timeout)
    return list(seen.values())


async def probe_devices(devices: list[dict], per_device_timeout: float = 10.0) -> dict | None:
    """Prova TUTTI i dispositivi trovati (dal segnale piu' forte) finche' uno
    espone il service FFF0 in GATT = lampada compatibile. Nessuna scrittura,
    solo lettura servizi + disconnect pulito."""
    from bleak import BleakClient

    ordered = sorted(devices,
                     key=lambda d: (d["rssi"] is not None, d["rssi"] or -999),
                     reverse=True)
    for i, dev in enumerate(ordered, 1):
        addr = dev["address"]
        print(f"[{i}/{len(ordered)}] provo {addr} "
              f"({dev['name'] or 'senza nome'}, rssi={dev['rssi']}) ...", flush=True)
        try:
            async with BleakClient(addr, timeout=per_device_timeout) as client:
                uuids = [s.uuid for s in client.services]
                print(f"    servizi: {uuids}", flush=True)
                if any("fff0" in u.lower() for u in uuids):
                    print(f"    >>> LAMPADA COMPATIBILE: {addr}", flush=True)
                    dev["gatt_services"] = uuids
                    dev["match"] = "LAMPADA"
                    return dev
        except Exception as e:
            print(f"    ({type(e).__name__})", flush=True)
    return None


async def watch() -> None:
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Scanner BLE lampade Liyadi/LEDLYD")
    ap.add_argument("--timeout", type=float, default=15.0, help="durata scansione (s)")
    ap.add_argument("--watch", action="store_true", help="monitoraggio continuo")
    ap.add_argument("--json", action="store_true", help="output JSON lines")
    ap.add_argument("--probe", action="store_true",
                    help="connette ogni device trovato e cerca FFF0 in GATT, "
                         "fino alla prima lampada compatibile (solo lettura)")
    ap.add_argument("--probe-timeout", type=float, default=10.0,
                    help="timeout connessione per device (s)")
    args = ap.parse_args()

    if args.watch:
        try:
            asyncio.run(watch())
        except KeyboardInterrupt:
            pass
        return

    devices = asyncio.run(scan_once(args.timeout, as_json=args.json))
    if args.json:
        return
    lamps = [d for d in devices if d["match"] == "LAMPADA"]
    maybe = [d for d in devices if d["match"] == "sospetta"]
    print(f"\n{len(devices)} dispositivi, {len(lamps)} lampade, {len(maybe)} sospetti.")
    for d in lamps + maybe:
        print(f"  [{d['match']}] {d['name'] or '(senza nome)'} "
              f"{d['address']} rssi={d['rssi']}")
    found = bool(lamps)
    if args.probe and not lamps:
        print("\nNessuna lampada da advertising: provo tutti i device in GATT...",
              flush=True)
        hit = asyncio.run(probe_devices(devices, args.probe_timeout))
        if hit:
            print(f"\nTROVATA lampada compatibile: {hit['address']} "
                  f"rssi={hit['rssi']}")
            found = True
        else:
            print("\nNessun device con service FFF0.")
    sys.exit(0 if found else 1)


if __name__ == "__main__":
    main()

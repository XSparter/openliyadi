#!/usr/bin/env python3
"""CLI scanner BLE (usa la libreria openliyadi.scanner).

Uso:
  python led_scan.py                 # scansione 15s
  python led_scan.py --timeout 30
  python led_scan.py --watch         # monitoraggio continuo
  python led_scan.py --json          # output JSON (una riga per device)
  python led_scan.py --probe         # sonda GATT fino a FFF0
"""

import argparse
import asyncio
import json
import sys

from openliyadi.scanner import scan_once, probe_devices, watch


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

    def on_device(info, is_new):
        if args.json:
            print(json.dumps(info), flush=True)
        elif is_new:
            mark = {"LAMPADA": ">>> ", "sospetta": " (?) "}.get(info["match"], "     ")
            print(f"{mark}{info['address']}  rssi={info['rssi']}  "
                  f"name={info['name'] or '(senza nome)'}  uuids={info['service_uuids']}",
                  flush=True)

    devices = asyncio.run(scan_once(args.timeout, on_device=on_device))
    lamps = [d for d in devices if d["match"] == "LAMPADA"]
    maybe = [d for d in devices if d["match"] == "sospetta"]
    if not args.json:
        print(f"\n{len(devices)} dispositivi, {len(lamps)} lampade, {len(maybe)} sospetti.")
        for d in lamps + maybe:
            print(f"  [{d['match']}] {d['name'] or '(senza nome)'} "
                  f"{d['address']} rssi={d['rssi']}")
    found = bool(lamps)
    if args.probe and not lamps:
        print("\nNessuna lampada da advertising: provo tutti i device in GATT...",
              flush=True)

        def on_try(i, total, dev):
            print(f"[{i}/{total}] provo {dev['address']} "
                  f"({dev['name'] or 'senza nome'}, rssi={dev['rssi']}) ...", flush=True)

        hit = asyncio.run(probe_devices(devices, args.probe_timeout, on_try=on_try))
        if hit:
            print(f"\nTROVATA lampada compatibile: {hit['address']} "
                  f"rssi={hit['rssi']}")
            if "gatt_services" in hit:
                print(f"  servizi: {hit['gatt_services']}")
            found = True
        else:
            print("\nNessun device con service FFF0.")
    sys.exit(0 if found else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Controllo luce RGB LEDLYD (ex azienda fallita) via BLE.
Reverse-engineered da LED.apk (uni-app __UNI__6FB700B, v2.0.15).

Protocollo:
  Pacchetto = [0xAA, CMD, LEN, ...payload..., CHECKSUM]
  CHECKSUM  = (0xAA + CMD + LEN + sum(payload)) & 0xFF

Trasporto BLE GATT:
  Nomi adv : LTF_MWRGB / LYD_MWRGB / Bough_Systems / LYDBough_Systems
  Service  : 0000FFF0-0000-1000-8000-00805F9B34FB
  TX (write, phone->lampada) : 0000FFF3-0000-1000-8000-00805F9B34FB
  RX (notify, lampada->phone): 0000FFF4-0000-1000-8000-00805F9B34FB

Uso:
  pip install bleak
  python led_lyd.py scan
  python led_lyd.py on --addr XX:XX:XX:XX:XX:XX
  python led_lyd.py rgb 255 0 0 --addr ...
  python led_lyd.py brightness 80 --addr ...
  python led_lyd.py off --addr ...
"""

import argparse
import asyncio
import sys


def _bleak():
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("Manca 'bleak'. Installa con: pip install bleak", file=sys.stderr)
        sys.exit(1)
    return BleakClient, BleakScanner

from openliyadi.protocol import (
    TARGET_NAMES, TX_UUID, RX_UUID, OFF_FALLBACK,
    pkt_open as _pkt_open,
    pkt_brightness,
    pkt_speed,
    pkt_fixed_mode,
    pkt_rgb_hsi as _pkt_rgb_hsi,
)
from openliyadi.scanner import classify as _classify


# --- Wrapper compatibili (firme storiche area-first) sui builder del pacchetto ---
def cmd_open() -> bytes:
    return _pkt_open()


def cmd_light(area: int, brightness: int) -> bytes:
    return pkt_brightness(brightness, area)


def cmd_speed(area: int, speed: int) -> bytes:
    return pkt_speed(speed, area)


def cmd_fixed_mode(area: int, mode: int) -> bytes:
    return pkt_fixed_mode(area, mode)


def cmd_rgb_hsi(r: int, g: int, b: int) -> bytes:
    return _pkt_rgb_hsi(r, g, b)


async def scan(timeout: float = 30.0):
    _, BleakScanner = _bleak()
    print(f"Scansione BLE ({timeout}s), cerco {TARGET_NAMES} / service FFF0/FEFF ...")
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    hits = 0
    for addr, (d, adv) in found.items():
        name = d.name or (adv.local_name if adv else None) or ""
        uuids = list(adv.service_uuids) if adv and adv.service_uuids else []
        is_hit = _is_lamp(name, uuids)
        mark = "TROVATA" if is_hit else "  visto"
        print(f"{mark}: {name or '(senza nome)'} [{addr}] uuids={uuids}")
        hits += is_hit
    if not hits:
        print("Nessuna lampada compatibile trovata.")
    return bool(hits)


def _is_lamp(name: str | None, uuids) -> bool:
    # Come prima: basta anche solo FEFF (la LP540-PRO lo trasmette senza nome).
    return _classify(name, uuids) in ("LAMPADA", "sospetta")


async def _wait_adv(address: str | None, timeout: float):
    """Aspetta un advertising fresco della lampada e lo restituisce.
    Collegarsi subito dopo l'ADV ricevuto e' molto piu' affidabile
    che usare la cache (la lampada trasmette di rado)."""
    _, BleakScanner = _bleak()
    got = asyncio.Event()
    holder = {}

    def cb(device, adv):
        name = device.name or (adv.local_name if adv else None) or ""
        uuids = list(adv.service_uuids) if adv and adv.service_uuids else []
        if address:
            ok = device.address.lower() == address.lower()
        else:
            ok = _is_lamp(name, uuids)
        if ok:
            print(f"Vista: {name or '(senza nome)'} [{device.address}] rssi={adv.rssi}",
                  flush=True)
            holder["dev"] = device
            got.set()

    async with BleakScanner(cb):
        await asyncio.wait_for(got.wait(), timeout=timeout)
    return holder["dev"]


async def _connect(dev, try_timeout: float = 15.0):
    BleakClient, _ = _bleak()
    client = BleakClient(dev, timeout=try_timeout)
    await client.connect()
    if not client.is_connected:
        raise ConnectionError("connect() senza errore ma non connesso")
    return client


async def send_packets(address: str | None, packets: list[bytes], listen: bool = True,
                       wait_total: float = 120.0):
    dev = None
    # Se --addr e' dato, prima un tentativo diretto veloce, poi race su ADV
    if address:
        try:
            print(f"Tentativo diretto a {address} ...", flush=True)
            client = await _connect(address, 12.0)
            dev = True  # connesso, salta la race
        except Exception as e:
            print(f"Diretto fallito ({type(e).__name__}), passo a race su ADV ...", flush=True)
            client = None
    else:
        client = None
    if client is None:
        deadline = asyncio.get_event_loop().time() + wait_total
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                print("Lampada non agganciata entro il tempo limite.", file=sys.stderr)
                sys.exit(2)
            try:
                dev = await _wait_adv(address, min(30.0, remaining))
            except asyncio.TimeoutError:
                print("Nessun ADV, riprovo...", flush=True)
                continue
            try:
                print(f"Connessione immediata a {dev.address} ...", flush=True)
                client = await _connect(dev, 15.0)
                break
            except asyncio.TimeoutError:
                print("Timeout connessione, attendo il prossimo ADV...", flush=True)
            except Exception as e:
                print(f"Connessione fallita ({type(e).__name__}: {e}), riprovo...",
                      flush=True)
    try:
        target = client.address
        print(f"Connesso a {target}: {client.is_connected}")
        if listen:
            def cb(_, data: bytearray):
                print(f"RX notify: {bytes(data).hex(' ')}")
            try:
                await client.start_notify(RX_UUID, cb)
            except Exception as e:
                print(f"Notify RX fallita (non fatale): {e}")
        for pkt in packets:
            print(f"TX -> {pkt.hex(' ')}")
            try:
                await client.write_gatt_char(TX_UUID, pkt, response=False)
            except Exception as e:
                print(f"  write-no-response fallita ({e}), riprovo con response=True")
                await client.write_gatt_char(TX_UUID, pkt, response=True)
            await asyncio.sleep(0.3)
        if listen:
            await asyncio.sleep(3.0)
            try:
                await client.stop_notify(RX_UUID)
            except Exception:
                pass
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        print("Disconnesso.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Controllo BLE lampada LEDLYD")
    ap.add_argument("--addr", default=None, help="MAC BLE lampada (se omesso, auto-scan)")
    sub = ap.add_subparsers(dest="action", required=True)

    sub.add_parser("scan", help="scansiona lampade compatibili")
    sub.add_parser("on", help="accendi (OPEN_CODE)")
    sub.add_parser("off", help="spegni (CLOSE_CODE)")

    p_rgb = sub.add_parser("rgb", help="colore diretto")
    p_rgb.add_argument("r", type=int)
    p_rgb.add_argument("g", type=int)
    p_rgb.add_argument("b", type=int)
    p_rgb.add_argument("--area", type=int, default=0)

    p_bri = sub.add_parser("brightness", help="luminosita 0-100")
    p_bri.add_argument("value", type=int)
    p_bri.add_argument("--area", type=int, default=0)

    p_spd = sub.add_parser("speed", help="velocita effetti 0-100")
    p_spd.add_argument("value", type=int)
    p_spd.add_argument("--area", type=int, default=0)

    p_mode = sub.add_parser("fixedmode", help="modalita fissa")
    p_mode.add_argument("mode", type=int)
    p_mode.add_argument("--area", type=int, default=0)

    p_raw = sub.add_parser("raw", help="pacchetto grezzo esadecimale, es. 'aa0b0100b6'")
    p_raw.add_argument("hex", help="byte in hex senza spazi")

    ap.add_argument("--listen", action="store_true", default=True,
                    help="ascolta notify RX dopo la scrittura (default: on)")
    ap.add_argument("--no-listen", dest="listen", action="store_false")

    args = ap.parse_args()

    if args.action == "scan":
        asyncio.run(scan())
        return

    if args.action == "on":
        pkts = [cmd_open()]
    elif args.action == "off":
        pkts = [bytes(OFF_FALLBACK)]
    elif args.action == "rgb":
        pkts = [cmd_rgb_hsi(args.r, args.g, args.b)]
    elif args.action == "brightness":
        pkts = [cmd_light(args.area, args.value)]
    elif args.action == "speed":
        pkts = [cmd_speed(args.area, args.value)]
    elif args.action == "fixedmode":
        pkts = [cmd_fixed_mode(args.area, args.mode)]
    elif args.action == "raw":
        pkts = [bytes.fromhex(args.hex)]
    else:
        ap.error("azione sconosciuta")

    asyncio.run(send_packets(args.addr, pkts, listen=args.listen))


if __name__ == "__main__":
    main()

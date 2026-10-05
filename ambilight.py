#!/usr/bin/env python3
"""CLI ambilight (usa la libreria openliyadi.ambilight)."""

import argparse
import asyncio

from openliyadi.ambilight import Ambilight, list_monitors, grab_average, boost_saturation


def _preview(monitor: int, fps: float):
    async def run():
        while True:
            r, g, b = grab_average(monitor)
            r, g, b = boost_saturation(r, g, b)
            print(f"\rRGB({r:3d},{g:3d},{b:3d})", end="", flush=True)
            await asyncio.sleep(1.0 / fps)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Ambilight Liyadi da schermo")
    ap.add_argument("--monitor", type=int, default=0,
                    help="schermo (0 = auto: il più luminoso)")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--lamp", action="store_true", help="invia davvero alla lampada")
    ap.add_argument("--list", action="store_true", help="elenca monitor ed esci")
    args = ap.parse_args()

    if args.list:
        for m in list_monitors():
            print(m)
        return
    if args.lamp:
        from openliyadi.controller import LEDController

        async def go():
            c = LEDController()
            await c.connect()
            amb = Ambilight(c)
            await amb.start(monitor=args.monitor, fps=args.fps)
            print("Ambilight attivo, Ctrl+C per fermare...")
            try:
                while True:
                    await asyncio.sleep(1.0)
            except KeyboardInterrupt:
                pass
            await amb.stop()
            await c.stop()

        asyncio.run(go())
    else:
        _preview(args.monitor, args.fps)


if __name__ == "__main__":
    main()

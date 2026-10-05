#!/usr/bin/env python3
"""CLI musica (usa la libreria openliyadi.music)."""

import argparse
import asyncio

from openliyadi.music import MusicSync, list_sources


def main() -> None:
    ap = argparse.ArgumentParser(description="Musica Liyadi da audio PC")
    ap.add_argument("--source", default=None, help="sorgente loopback (default: casse)")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--sensitivity", type=float, default=1.0)
    ap.add_argument("--list", action="store_true", help="elenca sorgenti ed esci")
    ap.add_argument("--levels", action="store_true",
                    help="mostra solo i livelli, senza lampada")
    args = ap.parse_args()

    if args.list:
        for s in list_sources():
            print(s["id"])
        return
    if args.levels:
        from openliyadi.music import list_sources as _ls, default_source
        import soundcard as sc
        import numpy as np
        from openliyadi.music import band_levels, SAMPLE_RATE, BLOCKSIZE

        async def show():
            src = args.source or default_source()
            print("sorgente:", src)
            mic = sc.get_microphone(src, include_loopback=True)
            with mic.recorder(samplerate=SAMPLE_RATE, channels=1,
                              blocksize=BLOCKSIZE) as rec:
                while True:
                    f = rec.record(numframes=BLOCKSIZE)
                    b, m, h = band_levels(f)
                    bar = lambda v: "#" * int(v * 30)
                    print(f"\rBASS {bar(b):30s} MID {bar(m):30s} HIGH {bar(h):30s}",
                          end="", flush=True)
                    await asyncio.sleep(0.05)
        try:
            asyncio.run(show())
        except KeyboardInterrupt:
            print()
        return

    from openliyadi.controller import LEDController

    async def go():
        c = LEDController()
        await c.connect()
        mus = MusicSync(c)
        await mus.start(source=args.source, fps=args.fps,
                        sensitivity=args.sensitivity)
        print("Musica attiva, Ctrl+C per fermare...")
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            pass
        await mus.stop()
        await c.stop()

    asyncio.run(go())


if __name__ == "__main__":
    main()

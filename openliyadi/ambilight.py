#!/usr/bin/env python3
"""
Ambilight stile Philips Hue per lampade Liyadi/LEDLYD.

Cattura lo schermo (mss), calcola il colore medio con smoothing esponenziale
e lo invia alla lampada (percorso HSI, come il color picker dell'app).
Dipendenze: mss (pip install mss).

Uso standalone:
    python ambilight.py --monitor 1 --fps 5        # anteprima a video (no lampada)
    python ambilight.py --monitor 1 --fps 5 --lamp # invia alla lampada
Uso da server.py: classe Ambilight (start/stop/status).
"""

import argparse
import asyncio
import time

try:
    import mss
except ImportError:
    mss = None


def list_monitors() -> list:
    """Elenco monitor: [{index, left, top, width, height, primary}]."""
    if mss is None:
        raise RuntimeError("manca 'mss': pip install mss")
    out = []
    with mss.MSS() as sct:
        for i, m in enumerate(sct.monitors[1:], start=1):
            out.append({"index": i, "left": m["left"], "top": m["top"],
                        "width": m["width"], "height": m["height"],
                        "primary": i == 1})
    return out


def grab_average(monitor: int = 1, step: int = 8) -> tuple:
    """Colore medio dello schermo (r, g, b 0-255). step = campionamento."""
    if mss is None:
        raise RuntimeError("manca 'mss': pip install mss")
    with mss.MSS() as sct:
        mon = sct.monitors[monitor]
        shot = sct.grab(mon)
        px = shot.rgb  # bytes RGB adiacenti
        n = len(px) // 3
        r = g = b = cnt = 0
        for i in range(0, n, step):
            o = i * 3
            r += px[o]
            g += px[o + 1]
            b += px[o + 2]
            cnt += 1
        return r // cnt, g // cnt, b // cnt


def boost_saturation(r: int, g: int, b: int, factor: float = 1.25) -> tuple:
    """Rende il colore piu' vivo (utile con medie slavate dello schermo)."""
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return r, g, b
    out = []
    for v in (r, g, b):
        nv = int(mn + (v - mn) * factor)
        out.append(max(0, min(255, nv)))
    return tuple(out)


class Ambilight:
    def __init__(self, controller):
        self.controller = controller
        self._task = None
        self.running = False
        self.monitor = 1
        self.fps = 10.0
        self.smooth = 0.35  # 0.0-1.0: peso del nuovo campione
        self.sat_boost = 1.25
        self.min_v = 8      # sotto questa soglia manda nero (P=0 = minima)
        self.last_rgb = (0, 0, 0)

    def status(self) -> dict:
        return {"running": self.running, "monitor": self.monitor,
                "fps": self.fps, "last_rgb": list(self.last_rgb)}

    async def start(self, monitor: int = 1, fps: float = 10.0) -> dict:
        await self.stop()
        self.monitor = monitor
        self.fps = max(1.0, min(15.0, fps))
        self.running = True
        self._task = asyncio.create_task(self._loop())
        return self.status()

    async def stop(self) -> dict:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        return self.status()

    async def _loop(self):
        cr, cg, cb = 0.0, 0.0, 0.0
        first = True
        try:
            while self.running:
                t0 = time.monotonic()
                try:
                    r, g, b = grab_average(self.monitor)
                    r, g, b = boost_saturation(r, g, b, self.sat_boost)
                    if first:
                        cr, cg, cb = float(r), float(g), float(b)
                        first = False
                    else:
                        a = self.smooth
                        cr += (r - cr) * a
                        cg += (g - cg) * a
                        cb += (b - cb) * a
                    rgb = (int(cr), int(cg), int(cb))
                    if max(rgb) < self.min_v:
                        rgb = (0, 0, 0)
                    self.last_rgb = rgb
                    await self.controller.set_rgb(*rgb)
                except Exception:
                    pass
                dt = time.monotonic() - t0
                await asyncio.sleep(max(0.0, 1.0 / self.fps - dt))
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False


def _preview(monitor: int, fps: float):
    """Anteprima a console senza lampada."""
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
    ap.add_argument("--monitor", type=int, default=1)
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--lamp", action="store_true", help="invia davvero alla lampada")
    ap.add_argument("--list", action="store_true", help="elenca monitor ed esci")
    args = ap.parse_args()

    if args.list:
        for m in list_monitors():
            print(m)
        return
    if args.lamp:
        from .controller import LEDController

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

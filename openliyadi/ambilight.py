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
import logging
import time

logger = logging.getLogger("ambilight")

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


def grab_center(monitor: int = 1, box: int = 9) -> tuple:
    """Colore del punto centrale (media su box*box px)."""
    if mss is None:
        raise RuntimeError("manca 'mss': pip install mss")
    with mss.MSS() as sct:
        mon = sct.monitors[monitor]
        cx, cy = mon["width"] // 2, mon["height"] // 2
    return grab_spot(monitor, cx, cy, box)


def grab_points(monitor: int = 1, margin: float = 0.06, box: int = 9,
                points: list | None = None) -> tuple:
    """Media di 5 punti: centro + 4 margini (stile ambilight perimetrale).
    points: opzionale [(rx, ry)]*5 in coordinate relative 0..1 (da WebUI)."""
    if mss is None:
        raise RuntimeError("manca 'mss': pip install mss")
    with mss.MSS() as sct:
        w, h = sct.monitors[monitor]["width"], sct.monitors[monitor]["height"]
    if points and len(points) == 5:
        pts = [(int(max(0.0, min(1.0, x)) * w), int(max(0.0, min(1.0, y)) * h))
               for x, y in points]
    else:
        mx, my = int(w * margin), int(h * margin)
        pts = [(w // 2, h // 2),
               (mx, h // 2), (w - mx, h // 2),
               (w // 2, my), (w // 2, h - my)]
    rs = gs = bs = 0
    for x, y in pts:
        r, g, b = grab_spot(monitor, x, y, box)
        rs += r
        gs += g
        bs += b
    return rs // 5, gs // 5, bs // 5


def grab_shot_jpeg(monitor: int = 1, max_w: int = 480, quality: int = 60) -> bytes:
    """Screenshot ridotto in JPEG (per preview WebUI). Ritorna bytes."""
    if mss is None:
        raise RuntimeError("manca 'mss': pip install mss")
    import io
    from PIL import Image
    with mss.MSS() as sct:
        shot = sct.grab(sct.monitors[monitor])
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def grab_spot(monitor: int = 1, x: int = 0, y: int = 0, box: int = 5) -> tuple:
    """Colore in un punto (x, y assoluti del monitor): media su box*box px."""
    if mss is None:
        raise RuntimeError("manca 'mss': pip install mss")
    with mss.MSS() as sct:
        mon = sct.monitors[monitor]
        half = box // 2
        region = {"left": mon["left"] + max(0, x - half),
                  "top": mon["top"] + max(0, y - half),
                  "width": box, "height": box}
        shot = sct.grab(region)
        px = shot.rgb
        n = len(px) // 3 or 1
        return (sum(px[0::3]) // n, sum(px[1::3]) // n, sum(px[2::3]) // n)


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
        self.mode = "avg"   # avg = media schermo | center = punto centrale |
                            # points = media 5 punti (4 margini + centro)
        self.points = None  # [(rx, ry)]*5 relative 0..1, o None = posizioni auto
        self.last_rgb = (0, 0, 0)

    def status(self) -> dict:
        return {"running": self.running, "monitor": self.monitor,
                "fps": self.fps, "mode": self.mode,
                "points": self.points,
                "last_rgb": list(self.last_rgb)}

    @staticmethod
    def _norm_points(points) -> list | None:
        """Valida 5 punti relativi, altrimenti None (posizioni auto)."""
        try:
            pts = [[max(0.0, min(1.0, float(x))), max(0.0, min(1.0, float(y)))]
                   for x, y in points]
        except (TypeError, ValueError):
            return None
        return pts if len(pts) == 5 else None

    async def start(self, monitor: int = 0, fps: float = 10.0,
                    mode: str = "avg", points: list | None = None) -> dict:
        await self.stop()
        if monitor <= 0:
            monitor = self._pick_live_monitor()
        self.monitor = monitor
        self.fps = max(1.0, min(30.0, fps))
        m = str(mode).lower()
        self.mode = m if m in ("avg", "center", "points") else "avg"
        self.points = self._norm_points(points)
        self.running = True
        self._task = asyncio.create_task(self._loop())
        return self.status()

    @staticmethod
    def _pick_live_monitor() -> int:
        """Sceglie lo schermo col contenuto piu' luminoso (0 = auto)."""
        try:
            mons = list_monitors()
        except Exception:
            return 1
        best, best_v = 1, -1
        for m in mons:
            try:
                r, g, b = grab_average(m["index"])
                v = max(r, g, b)
            except Exception:
                continue
            if v > best_v:
                best, best_v = m["index"], v
        return best

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
                    if self.mode == "center":
                        r, g, b = grab_center(self.monitor)
                    elif self.mode == "points":
                        r, g, b = grab_points(self.monitor, points=self.points)
                    else:
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
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("ambilight loop: %s: %s", type(e).__name__, e)
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

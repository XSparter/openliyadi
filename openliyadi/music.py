"""Modalita' musica: la lampada balla con l'audio del PC (loopback WASAPI).

Analisi spettrale (numpy rFFT): bassi 55-160 Hz, medi, alti + beat tracking
sul flusso dei bassi. Mapping: beat -> flash luminosita' + salto hue,
bassi -> potenza, andamento spettrale -> deriva hue.
Dipendenze: soundcard, numpy (pip install openliyadi[music]).
"""

import asyncio
import logging
import time

import numpy as np

logger = logging.getLogger("music")

SAMPLE_RATE = 44100
BLOCKSIZE = 2048  # ~46 ms a 44.1 kHz


def list_sources() -> list:
    """Sorgenti loopback (casse viste come microfoni)."""
    import soundcard as sc
    out = []
    try:
        mics = sc.all_microphones(include_loopback=True)
    except TypeError:  # versioni vecchie
        mics = sc.all_microphones()
    for m in mics:
        name = str(getattr(m, "name", m))
        if m.isloopback:
            out.append({"id": name, "name": name, "loopback": True})
    return out


def default_source() -> str | None:
    """Nome loopback delle casse predefinite, o None."""
    import soundcard as sc
    try:
        spk = sc.default_speaker()
        mic = sc.get_microphone(spk.name, include_loopback=True)
        return mic.name
    except Exception:
        srcs = list_sources()
        return srcs[0]["id"] if srcs else None


def band_levels(frame: np.ndarray, sr: int = SAMPLE_RATE) -> tuple:
    """Energia (bass, mid, high) del blocco mono float32 -1..1."""
    x = np.asarray(frame, dtype=np.float32).ravel()
    if x.size == 0:
        return 0.0, 0.0, 0.0
    x = x - x.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    freqs = np.fft.rfftfreq(x.size, 1.0 / sr)
    tot = float(spec.sum()) + 1e-9
    bass = float(spec[(freqs >= 55) & (freqs < 160)].sum()) / tot
    mid = float(spec[(freqs >= 160) & (freqs < 1200)].sum()) / tot
    high = float(spec[freqs >= 1200].sum()) / tot
    return bass, mid, high


class MusicSync:
    def __init__(self, controller):
        self.controller = controller
        self._task = None
        self.running = False
        self.source = None
        self.fps = 10.0
        self.sensitivity = 1.0  # >1 = beat piu' facile
        self.hue = 0.0
        self.levels = (0.0, 0.0, 0.0)
        self.beat = False
        self._bass_hist: list = []

    def status(self) -> dict:
        b, m, h = self.levels
        return {"running": self.running, "source": self.source,
                "fps": self.fps, "sensitivity": self.sensitivity,
                "levels": [round(b, 3), round(m, 3), round(h, 3)],
                "beat": self.beat, "hue": round(self.hue)}

    async def start(self, source: str | None = None, fps: float = 10.0,
                    sensitivity: float = 1.0) -> dict:
        await self.stop()
        self.source = source or default_source()
        if not self.source:
            raise RuntimeError("nessuna sorgente loopback trovata")
        self.fps = max(1.0, min(30.0, fps))
        self.sensitivity = max(0.2, min(3.0, sensitivity))
        self._bass_hist = []
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
        self.beat = False
        return self.status()

    async def _loop(self):
        import soundcard as sc
        loop = asyncio.get_running_loop()
        try:
            mic = sc.get_microphone(self.source, include_loopback=True)
        except TypeError:
            mic = sc.get_microphone(self.source)
        try:
            with mic.recorder(samplerate=SAMPLE_RATE, channels=1,
                              blocksize=BLOCKSIZE) as rec:
                while self.running:
                    t0 = time.monotonic()
                    try:
                        frame = await loop.run_in_executor(
                            None, lambda: rec.record(numframes=BLOCKSIZE))
                        bass, mid, high = band_levels(frame)
                        self.levels = (bass, mid, high)
                        self._bass_hist.append(bass)
                        if len(self._bass_hist) > 24:
                            self._bass_hist.pop(0)
                        avg = (sum(self._bass_hist) / len(self._bass_hist)
                               if self._bass_hist else bass)
                        # beat: picco bassi sopra media mobile
                        self.beat = (len(self._bass_hist) >= 8
                                     and bass > max(avg * 1.35 * self.sensitivity, 0.02))
                        energy = min(1.0, (bass * 2.2 + mid * 0.8 + high * 0.4))
                        if self.beat:
                            self.hue = (self.hue + 24 + bass * 60) % 360
                            bri = int(55 + 45 * min(1.0, energy * 1.5))
                        else:
                            self.hue = (self.hue + 2.5 + high * 12) % 360
                            bri = int(25 + 65 * energy)
                        await self.controller.set_hsi(int(self.hue), 100, bri)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning("music loop: %s: %s", type(e).__name__, e)
                    dt = time.monotonic() - t0
                    await asyncio.sleep(max(0.0, 1.0 / self.fps - dt))
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            self.beat = False

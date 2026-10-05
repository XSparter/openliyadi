"""
Controller BLE nativo Windows ad alte prestazioni per lampada LEDLYD / Bough_Systems.
Utilizza direttamente WinRT BluetoothLEDevice e GattSession per garantire
una connessione ultra-stabile e risposte istantanee (<50ms).
"""

import asyncio
import json
import logging
import os
from typing import Callable, Optional

import winrt.windows.devices.bluetooth as bt
import winrt.windows.devices.bluetooth.genericattributeprofile as gatt
import winrt.windows.storage.streams as streams
from bleak import BleakScanner

from .protocol import (
    pkt_open, pkt_close, pkt_rgb, pkt_brightness, pkt_cct, pkt_hsi, pkt_effect,
    pkt_rgb_hsi, pkt_off_last, EFFECTS, EFFECT_BY_NAME, TARGET_NAMES
)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
logger = logging.getLogger("led_controller")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_MAC = "12:22:33:44:70:E0"


def _to_ibuffer(b: bytes):
    dw = streams.DataWriter()
    dw.write_bytes(b)
    return dw.detach_buffer()


class LEDController:
    def __init__(self, mac_address: str = DEFAULT_MAC):
        self.mac_address = mac_address
        self.mac_int = int(mac_address.replace(":", ""), 16)
        
        self.le_device = None
        self.gatt_session = None
        self.char_tx = None
        
        self.is_connected = False
        self.state = {
            "power": False,
            "brightness": 100,
            "rgb": [255, 255, 255],
            "cct": {"kelvin": 5600, "brightness": 100},
            "hsi": {"hue": 0, "saturation": 100, "brightness": 100},
            "effect": {"name": "Flash", "id": 1, "speed": 5, "brightness": 100},
            "connected": False,
            "address": self.mac_address,
        }
        
        self._cmd_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._status_listeners: list[Callable[[dict], None]] = []
        self._lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()  # serializza worker e sequenze atomiche
        self._last_mode10: bytes | None = None  # ultimo pacchetto modo (per OFF)

    def add_status_listener(self, cb: Callable[[dict], None]):
        self._status_listeners.append(cb)

    def _notify_listeners(self):
        self.state["connected"] = self.is_connected
        for cb in self._status_listeners:
            try:
                cb(self.get_status())
            except Exception:
                pass

    def get_status(self) -> dict:
        self.state["connected"] = self.is_connected
        return dict(self.state)

    async def start(self):
        """Avvia la coda di invio comandi."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._queue_worker())

    async def stop(self):
        """Arresta il worker e disconnette."""
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None
        await self.disconnect()

    async def connect(self, address: Optional[str] = None) -> bool:
        """Connette la lampada via WinRT mantenendo la sessione GATT attiva."""
        async with self._lock:
            if address:
                self.mac_address = address
                self.mac_int = int(address.replace(":", ""), 16)
                self.state["address"] = self.mac_address

            if self.is_connected and self.char_tx:
                return True

            logger.info(f"Connessione a {self.mac_address}...")
            
            # 1. Attesa di un pacchetto ADV rapido per risvegliare lo stack Windows
            dev_found = asyncio.Event()
            def cb(dev, adv):
                if dev.address.upper() == self.mac_address.upper():
                    dev_found.set()

            scanner = BleakScanner(detection_callback=cb, scanning_mode="active")
            await scanner.start()
            try:
                await asyncio.wait_for(dev_found.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning("Nessun ADV recente ricevuto, tento connessione diretta...")
            finally:
                await scanner.stop()

            # 2. Apertura BluetoothLEDevice
            self.le_device = await bt.BluetoothLEDevice.from_bluetooth_address_async(self.mac_int)
            if not self.le_device:
                raise ConnectionError(f"Impossibile accedere a {self.mac_address}")

            # 3. Mantenimento sessione attiva
            self.gatt_session = await gatt.GattSession.from_device_id_async(self.le_device.bluetooth_device_id)
            self.gatt_session.maintain_connection = True

            # 4. Servizio FFF0
            fff0_uuid = bt.BluetoothUuidHelper.from_short_id(0xFFF0)
            gatt_res = None
            for attempt in range(1, 4):
                gatt_res = await self.le_device.get_gatt_services_for_uuid_async(fff0_uuid)
                if gatt_res.status == gatt.GattCommunicationStatus.SUCCESS and len(gatt_res.services) > 0:
                    break
                await asyncio.sleep(0.4)

            if not gatt_res or gatt_res.status != gatt.GattCommunicationStatus.SUCCESS:
                self.gatt_session.maintain_connection = False
                raise ConnectionError("Servizio GATT FFF0 non raggiungibile")

            service = gatt_res.services[0]

            # 5. Caratteristica TX FFF3
            fff3_uuid = bt.BluetoothUuidHelper.from_short_id(0xFFF3)
            chars_res = await service.get_characteristics_for_uuid_async(fff3_uuid)
            if chars_res.status != gatt.GattCommunicationStatus.SUCCESS or len(chars_res.characteristics) == 0:
                self.gatt_session.maintain_connection = False
                raise ConnectionError("Caratteristica FFF3 non trovata")

            self.char_tx = chars_res.characteristics[0]
            self.is_connected = True
            self.state["connected"] = True
            logger.info("Lampada connessa e pronta all'uso!")
            
            await self.start()
            self._notify_listeners()
            return True

    async def scan(self, timeout: float = 12.0) -> list:
        """Scansione BLE: restituisce [{address, name, rssi, service_uuids, is_lamp}].
        Usata da /api/scan e dalla WebUI."""
        from bleak import BleakScanner

        seen: dict[str, dict] = {}

        def cb(device, adv):
            name = device.name or (adv.local_name if adv else None) or ""
            uuids = list(adv.service_uuids) if adv and adv.service_uuids else []
            nl = name.lower()
            is_lamp = (any(t.lower() in nl for t in TARGET_NAMES)
                       or any("fff0" in u.lower() for u in uuids))
            prev = seen.get(device.address)
            entry = {"address": device.address, "name": name or None,
                     "rssi": adv.rssi if adv else None,
                     "service_uuids": uuids, "is_lamp": is_lamp}
            if prev is None or (entry["rssi"] is not None and (
                    prev["rssi"] is None or entry["rssi"] > prev["rssi"])):
                seen[device.address] = entry

        async with BleakScanner(cb):
            await asyncio.sleep(timeout)
        return sorted(seen.values(),
                      key=lambda d: (d["rssi"] is not None, d["rssi"] or -999),
                      reverse=True)

    async def disconnect(self):
        """Chiude la sessione GATT."""
        async with self._lock:
            if self.gatt_session:
                try:
                    self.gatt_session.maintain_connection = False
                except Exception:
                    pass
                self.gatt_session = None
            self.char_tx = None
            self.le_device = None
            self.is_connected = False
            self.state["connected"] = False
            self._notify_listeners()

    async def _write_pkt(self, pkt: bytes):
        """Scrittura singola su FFF3 con fallback write/with-response."""
        buf = _to_ibuffer(pkt)
        try:
            await self.char_tx.write_value_with_result_and_option_async(
                buf, gatt.GattWriteOption.WRITE_WITHOUT_RESPONSE
            )
        except Exception:
            try:
                await self.char_tx.write_value_async(buf)
            except Exception as e:
                logger.error(f"Errore scrittura BLE: {e}")

    async def _queue_worker(self):
        """Invia i comandi senza sovraccaricare la radio.
        Coalescing solo tra singoli pacchetti (slider); le sequenze atomiche
        passano da send_sequence e non possono essere spezzate/scartate."""
        while True:
            try:
                pkt = await self._cmd_queue.get()
                while not self._cmd_queue.empty():
                    pkt = self._cmd_queue.get_nowait()

                if not self.is_connected or not self.char_tx:
                    continue

                async with self._write_lock:
                    await self._write_pkt(pkt)

                await asyncio.sleep(0.04)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Errore worker: {e}")
                await asyncio.sleep(0.1)

    async def send_packet(self, pkt: bytes):
        if not self.is_connected:
            await self.connect()
        await self._cmd_queue.put(pkt)

    async def send_sequence(self, pkts: list[bytes], gap: float = 0.05):
        """Invia pacchetti IN ORDINE, atomicamente (nessun interleaving con
        lo slider/worker). Usata per sequenze tipo OPEN -> RGB."""
        if not self.is_connected:
            await self.connect()
        async with self._write_lock:
            for p in pkts:
                if not self.is_connected or not self.char_tx:
                    break
                await self._write_pkt(p)
                await asyncio.sleep(gap)

    # --- Comandi Studio ---

    async def turn_on(self):
        self.state["power"] = True
        await self.send_packet(pkt_open())
        self._notify_listeners()

    async def turn_off(self):
        # Spegnimento vero (verificato dal vivo): ripete l'ultimo pacchetto
        # modo con mode=0, come fa l'app. CLOSE_CODE headed dimmera soltanto.
        self.state["power"] = False
        await self.send_sequence([pkt_off_last(self._last_mode10)])
        self._notify_listeners()

    def _remember_mode10(self, pkt: bytes):
        if len(pkt) == 10:
            self._last_mode10 = bytes(pkt)

    async def set_rgb(self, r: int, g: int, b: int, area: int = 0):
        self.state["power"] = True
        self.state["rgb"] = [r, g, b]
        # Percorso reale del color picker (changeColor -> hsiMode): pacchetto
        # HSI raw a 10 byte. Il PALETTE headed (cmd 4) non ha chiamanti nella UI
        # e in modo CCT viene ignorato: niente OPEN davanti.
        pkt = pkt_rgb_hsi(r, g, b)
        self._remember_mode10(pkt)
        await self.send_sequence([pkt])
        self._notify_listeners()

    async def set_brightness(self, level: int, area: int = 0):
        self.state["brightness"] = level
        await self.send_packet(pkt_brightness(level, area))
        self._notify_listeners()

    async def set_cct(self, kelvin: int, brightness: int = 100):
        self.state["power"] = True
        self.state["cct"] = {"kelvin": kelvin, "brightness": brightness}
        self.state["brightness"] = brightness
        pkt = pkt_cct(kelvin=kelvin, brightness=brightness)
        self._remember_mode10(pkt)
        await self.send_packet(pkt)
        self._notify_listeners()

    async def set_hsi(self, hue: int, saturation: int = 100, brightness: int = 100):
        self.state["power"] = True
        self.state["hsi"] = {"hue": hue, "saturation": saturation, "brightness": brightness}
        self.state["brightness"] = brightness
        pkt = pkt_hsi(hue=hue, saturation=saturation, brightness=brightness)
        self._remember_mode10(pkt)
        await self.send_packet(pkt)
        self._notify_listeners()

    async def set_effect(self, effect_id_or_name: int | str, brightness: int = 100, speed: int = 5):
        self.state["power"] = True
        pkt = pkt_effect(effect_id_or_name, brightness=brightness, speed=speed)
        eff = None
        if isinstance(effect_id_or_name, int):
            eff = next((e for e in EFFECTS if e["id"] == effect_id_or_name), None)
        else:
            eff = EFFECT_BY_NAME.get(str(effect_id_or_name).lower())
        if eff:
            self.state["effect"] = {"name": eff["name"], "id": eff["id"], "speed": speed, "brightness": brightness}
        self._remember_mode10(pkt)
        await self.send_packet(pkt)
        self._notify_listeners()

"""
Server Web locale FastAPI per controllo studio della lampada LEDLYD / LTF_MWRGB.
Include API REST, WebSocket in tempo reale e una Web App completa offline.
"""

import asyncio
import json
import logging
import os
import webbrowser
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from openliyadi.protocol import EFFECTS
from openliyadi.controller import LEDController
from openliyadi.ambilight import Ambilight, list_monitors

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("led_server")

app = FastAPI(title="LEDLYD Studio Controller")
controller = LEDController()
amb = Ambilight(controller)
active_websockets: list[WebSocket] = []


# --- Modelli Pydantic per le API ---
class ConnectReq(BaseModel):
    address: Optional[str] = None

class PowerReq(BaseModel):
    state: bool

class RgbReq(BaseModel):
    r: int
    g: int
    b: int
    area: int = 0

class BrightnessReq(BaseModel):
    value: int
    area: int = 0

class CctReq(BaseModel):
    kelvin: int
    brightness: int = 100

class HsiReq(BaseModel):
    hue: int
    saturation: int = 100
    brightness: int = 100

class EffectReq(BaseModel):
    effect: str
    brightness: int = 100
    speed: int = 5

class AmbStartReq(BaseModel):
    monitor: int = 1
    fps: float = 5.0


# --- Listener per notifiche WebSocket ---
def on_controller_status(status: dict):
    msg = json.dumps({"type": "status", "data": status})
    # Invio broadcast non bloccante ai websocket attivi
    for ws in list(active_websockets):
        try:
            asyncio.create_task(ws.send_text(msg))
        except Exception:
            pass

controller.add_status_listener(on_controller_status)


@app.on_event("startup")
async def startup_event():
    await controller.start()
    # Se c'è un indirizzo salvato, prova a connettersi in background
    if controller.mac_address:
        asyncio.create_task(auto_connect_bg())

async def auto_connect_bg():
    try:
        await controller.connect(controller.mac_address)
    except Exception as e:
        logger.info(f"Auto-connessione all'avvio in background non riuscita (la lampada potrebbe essere spenta): {e}")


@app.on_event("shutdown")
async def shutdown_event():
    await controller.stop()


# --- Endpoint REST ---
@app.get("/api/status")
async def get_status():
    return controller.get_status()

@app.get("/api/effects")
async def get_effects():
    return EFFECTS

@app.post("/api/scan")
async def scan_devices(timeout: float = 12.0):
    try:
        devices = await controller.scan(timeout=timeout)
        return {"devices": devices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/connect")
async def connect_device(req: ConnectReq):
    try:
        ok = await controller.connect(req.address)
        return {"connected": ok, "status": controller.get_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/disconnect")
async def disconnect_device():
    await controller.disconnect()
    return {"connected": False}

@app.post("/api/power")
async def set_power(req: PowerReq):
    try:
        if req.state:
            await controller.turn_on()
        else:
            await controller.turn_off()
        return controller.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rgb")
async def set_rgb(req: RgbReq):
    try:
        await controller.set_rgb(req.r, req.g, req.b, req.area)
        return controller.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/brightness")
async def set_brightness(req: BrightnessReq):
    try:
        await controller.set_brightness(req.value, req.area)
        return controller.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cct")
async def set_cct(req: CctReq):
    try:
        await controller.set_cct(req.kelvin, req.brightness)
        return controller.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hsi")
async def set_hsi(req: HsiReq):
    try:
        await controller.set_hsi(req.hue, req.saturation, req.brightness)
        return controller.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/effect")
async def set_effect(req: EffectReq):
    try:
        await controller.set_effect(req.effect, req.brightness, req.speed)
        return controller.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Ambilight (schermo -> lampada) ---
@app.get("/api/ambilight/monitors")
async def amb_monitors():
    try:
        return {"monitors": list_monitors()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ambilight/start")
async def amb_start(req: AmbStartReq):
    try:
        return await amb.start(monitor=req.monitor, fps=req.fps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ambilight/stop")
async def amb_stop():
    return await amb.stop()

@app.get("/api/ambilight/status")
async def amb_status():
    return amb.status()


# --- WebSocket in tempo reale ---
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_websockets.append(ws)
    # Invia stato corrente subito
    await ws.send_text(json.dumps({"type": "status", "data": controller.get_status()}))
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")
            data = msg.get("data", {})
            try:
                if action == "rgb":
                    await controller.set_rgb(data["r"], data["g"], data["b"])
                elif action == "cct":
                    await controller.set_cct(data["kelvin"], data.get("brightness", 100))
                elif action == "hsi":
                    await controller.set_hsi(data["hue"], data["saturation"], data.get("brightness", 100))
                elif action == "brightness":
                    await controller.set_brightness(data["value"])
                elif action == "power":
                    if data.get("state"):
                        await controller.turn_on()
                    else:
                        await controller.turn_off()
                elif action == "effect":
                    await controller.set_effect(data["effect"], data.get("brightness", 100), data.get("speed", 5))
                elif action == "ambilight":
                    if data.get("on"):
                        await amb.start(monitor=data.get("monitor", 1), fps=data.get("fps", 5.0))
                    else:
                        await amb.stop()
            except Exception as e:
                await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
    except WebSocketDisconnect:
        if ws in active_websockets:
            active_websockets.remove(ws)
    except Exception:
        if ws in active_websockets:
            active_websockets.remove(ws)


# --- Frontend Web Studio (Single Page Application 100% Offline) ---
HTML_PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LED Studio Control</title>
  <style>
    :root {
      --bg: #0f1115;
      --card-bg: #1a1d24;
      --card-border: #262a34;
      --text: #f0f2f5;
      --text-muted: #8a919e;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --radius: 12px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 16px; display: flex; justify-content: center; min-height: 100vh; }
    .container { width: 100%; max-width: 680px; display: flex; flex-direction: column; gap: 16px; }

    /* Header & Power */
    header { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; }
    .brand { display: flex; align-items: center; gap: 10px; }
    .brand-icon { width: 32px; height: 32px; border-radius: 8px; background: linear-gradient(135deg, #f59e0b, #ef4444, #8b5cf6); display: flex; align-items: center; justify-content: center; font-weight: bold; }
    .brand-title { font-size: 1.15rem; font-weight: 700; }
    
    .status-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 0.8rem; padding: 4px 10px; border-radius: 20px; background: #262a34; color: var(--text-muted); cursor: pointer; transition: 0.2s; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #6b7280; }
    .status-badge.connected .status-dot { background: var(--accent); box-shadow: 0 0 8px var(--accent); }
    .status-badge.connected { color: #34d399; background: rgba(16, 185, 129, 0.15); }
    .status-badge.connecting .status-dot { background: var(--warning); animation: pulse 1s infinite; }

    @keyframes pulse { 0% { opacity: 0.3; } 50% { opacity: 1; } 100% { opacity: 0.3; } }

    .power-btn { width: 44px; height: 44px; border-radius: 50%; border: none; background: #262a34; color: #6b7280; font-size: 1.3rem; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
    .power-btn.on { background: #ef4444; color: #fff; box-shadow: 0 0 16px rgba(239, 68, 68, 0.5); }

    /* Navigation Tabs */
    .tabs { display: flex; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 4px; gap: 4px; }
    .tab-btn { flex: 1; padding: 10px; border: none; background: transparent; color: var(--text-muted); font-weight: 600; font-size: 0.9rem; border-radius: 8px; cursor: pointer; transition: 0.2s; }
    .tab-btn.active { background: #2a2f3a; color: var(--text); }

    /* Panels */
    .panel { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 20px; display: none; flex-direction: column; gap: 20px; }
    .panel.active { display: flex; }

    /* Controls */
    .control-group { display: flex; flex-direction: column; gap: 8px; }
    .control-header { display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-muted); font-weight: 600; }
    .control-value { color: var(--text); font-family: monospace; }
    
    input[type=range] { width: 100%; height: 8px; -webkit-appearance: none; background: #2d323f; border-radius: 4px; outline: none; }
    input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 22px; height: 22px; border-radius: 50%; background: #ffffff; cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.4); border: 2px solid #2d323f; }

    .cct-slider { background: linear-gradient(to right, #ff8c00, #ffb155, #fff4e5, #e0efff, #99c7ff) !important; height: 12px !important; }
    .hue-slider { background: linear-gradient(to right, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff, #ff00ff, #ff0000) !important; height: 12px !important; }

    /* Color Preview Box */
    .color-preview-box { height: 70px; border-radius: 10px; border: 2px solid #333a48; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; font-weight: 700; text-shadow: 0 1px 4px rgba(0,0,0,0.8); }

    /* Presets */
    .preset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(48px, 1fr)); gap: 8px; }
    .preset-btn { height: 40px; border-radius: 8px; border: 2px solid transparent; cursor: pointer; transition: 0.15s; }
    .preset-btn:hover { transform: scale(1.08); border-color: #fff; }

    .quick-k-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .k-btn { padding: 10px; border-radius: 8px; border: 1px solid var(--card-border); background: #222630; color: var(--text); font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: 0.2s; text-align: center; }
    .k-btn:hover { background: #2f3543; border-color: var(--primary); }
    .k-sub { display: block; font-size: 0.7rem; color: var(--text-muted); margin-top: 2px; }

    /* Effects Grid */
    .fx-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; max-height: 380px; overflow-y: auto; padding-right: 4px; }
    .fx-card { background: #222630; border: 1px solid var(--card-border); border-radius: 8px; padding: 12px 10px; cursor: pointer; text-align: center; transition: 0.2s; }
    .fx-card:hover { background: #2a303d; border-color: #4b5563; }
    .fx-card.active { border-color: var(--primary); background: rgba(59, 130, 246, 0.15); box-shadow: 0 0 12px rgba(59, 130, 246, 0.3); }
    .fx-title { font-size: 0.85rem; font-weight: 600; margin-bottom: 2px; }
    .fx-cat { font-size: 0.7rem; color: var(--text-muted); }

    /* Modal Device Scanner */
    .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: none; align-items: center; justify-content: center; z-index: 100; backdrop-filter: blur(4px); }
    .modal-overlay.open { display: flex; }
    .modal { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); width: 90%; max-width: 480px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
    .modal-header { display: flex; justify-content: space-between; align-items: center; }
    .device-list { max-height: 280px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
    .device-item { padding: 12px; border-radius: 8px; background: #222630; border: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: 0.2s; }
    .device-item:hover { background: #2a303d; border-color: var(--primary); }
    .device-item.is-lamp { border-color: #10b981; }
    .device-name { font-weight: 600; font-size: 0.9rem; }
    .device-addr { font-size: 0.75rem; color: var(--text-muted); font-family: monospace; }
    .btn { padding: 8px 16px; border-radius: 8px; border: none; font-weight: 600; cursor: pointer; transition: 0.2s; }
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-secondary { background: #2d323f; color: var(--text); }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header>
      <div class="brand">
        <div class="brand-icon">☀</div>
        <div>
          <div class="brand-title">LEDLYD Studio</div>
          <div id="statusBadge" class="status-badge" onclick="openScanner()">
            <span class="status-dot"></span>
            <span id="statusText">Disconnesso</span>
          </div>
        </div>
      </div>
      <button id="powerBtn" class="power-btn" data-i18n-title="power_title" onclick="togglePower()" title="Accendi/Spegni">⏻</button>
    </header>

    <!-- Navigation Tabs -->
    <div class="tabs">
      <button class="tab-btn active" data-i18n="tab_rgb" onclick="setTab('rgb')">🎨 Colore / HSI</button>
      <button class="tab-btn" data-i18n="tab_cct" onclick="setTab('cct')">☀️ Studio CCT</button>
      <button class="tab-btn" data-i18n="tab_fx" onclick="setTab('fx')">⚡ 24 Effetti</button>
      <button class="tab-btn" data-i18n="tab_amb" onclick="setTab('amb')">🖥️ Ambilight</button>
    </div>

    <!-- Panel 1: RGB / HSI -->
    <div id="panel-rgb" class="panel active">
      <div id="colorPreview" class="color-preview-box" style="background-color: #ff0055;">#FF0055</div>
      
      <div class="control-group">
        <div class="control-header">
          <span data-i18n="hue">Tonalità (Hue)</span>
          <span id="valHue" class="control-value">340°</span>
        </div>
        <input type="range" id="sliderHue" class="hue-slider" min="0" max="360" value="340" oninput="onHsiInput()">
      </div>

      <div class="control-group">
        <div class="control-header">
          <span data-i18n="sat">Saturazione</span>
          <span id="valSat" class="control-value">100%</span>
        </div>
        <input type="range" id="sliderSat" min="0" max="100" value="100" oninput="onHsiInput()">
      </div>

      <div class="control-group">
        <div class="control-header">
          <span data-i18n="bri">Luminosità</span>
          <span id="valBriHsi" class="control-value">100%</span>
        </div>
        <input type="range" id="sliderBriHsi" min="0" max="100" value="100" oninput="onHsiInput()">
      </div>

      <div class="control-group">
        <div class="control-header"><span data-i18n="presets">Colori Rapidi</span></div>
        <div class="preset-grid">
          <div class="preset-btn" style="background:#ff0000" onclick="setHex('#ff0000')"></div>
          <div class="preset-btn" style="background:#ff5500" onclick="setHex('#ff5500')"></div>
          <div class="preset-btn" style="background:#ffaa00" onclick="setHex('#ffaa00')"></div>
          <div class="preset-btn" style="background:#ffff00" onclick="setHex('#ffff00')"></div>
          <div class="preset-btn" style="background:#00ff00" onclick="setHex('#00ff00')"></div>
          <div class="preset-btn" style="background:#00ffff" onclick="setHex('#00ffff')"></div>
          <div class="preset-btn" style="background:#0066ff" onclick="setHex('#0066ff')"></div>
          <div class="preset-btn" style="background:#8800ff" onclick="setHex('#8800ff')"></div>
          <div class="preset-btn" style="background:#ff00ff" onclick="setHex('#ff00ff')"></div>
          <div class="preset-btn" style="background:#ffffff" onclick="setHex('#ffffff')"></div>
        </div>
      </div>
    </div>

    <!-- Panel 2: CCT Studio -->
    <div id="panel-cct" class="panel">
      <div id="cctPreview" class="color-preview-box" style="background-color: #ffe8cc; color: #1a1d24;">5600K Daylight</div>

      <div class="control-group">
        <div class="control-header">
          <span data-i18n="cct_temp">Temperatura Colore</span>
          <span id="valCct" class="control-value">5600 K</span>
        </div>
        <input type="range" id="sliderCct" class="cct-slider" min="2500" max="8500" step="50" value="5600" oninput="onCctInput()">
      </div>

      <div class="control-group">
        <div class="control-header">
          <span data-i18n="cct_bri">Luminosità CCT</span>
          <span id="valBriCct" class="control-value">100%</span>
        </div>
        <input type="range" id="sliderBriCct" min="0" max="100" value="100" oninput="onCctInput()">
      </div>

      <div class="control-group">
        <div class="control-header"><span data-i18n="k_presets">Preset Fotografici Kelvin</span></div>
        <div class="quick-k-grid">
          <button class="k-btn" onclick="setKelvin(2700)">2700 K<span class="k-sub" data-i18n="k2700">Lume / Candela</span></button>
          <button class="k-btn" onclick="setKelvin(3200)">3200 K<span class="k-sub" data-i18n="k3200">Tungsteno Studio</span></button>
          <button class="k-btn" onclick="setKelvin(4000)">4000 K<span class="k-sub" data-i18n="k4000">Bianco Naturale</span></button>
          <button class="k-btn" onclick="setKelvin(5600)">5600 K<span class="k-sub" data-i18n="k5600">Daylight Standard</span></button>
          <button class="k-btn" onclick="setKelvin(6500)">6500 K<span class="k-sub" data-i18n="k6500">Nuvoloso / D65</span></button>
          <button class="k-btn" onclick="setKelvin(8500)">8500 K<span class="k-sub" data-i18n="k8500">Cielo Freddo</span></button>
        </div>
      </div>
    </div>

    <!-- Panel 3: FX 24 Effects -->
    <div id="panel-fx" class="panel">
      <div class="control-group">
        <div class="control-header">
          <span data-i18n="fx_speed">Velocità Effetto (Frequency)</span>
          <span id="valFxSpeed" class="control-value">5 / 20</span>
        </div>
        <input type="range" id="sliderFxSpeed" min="1" max="20" value="5" oninput="onFxParamChange()">
      </div>

      <div class="control-group">
        <div class="control-header">
          <span data-i18n="fx_bri">Luminosità Effetto</span>
          <span id="valFxBri" class="control-value">100%</span>
        </div>
        <input type="range" id="sliderFxBri" min="0" max="100" value="100" oninput="onFxParamChange()">
      </div>

      <div class="control-header" style="margin-top: 8px;"><span data-i18n="fx_select">Seleziona Effetto Scena</span></div>
      <div id="fxGrid" class="fx-grid"></div>
    </div>

    <!-- Panel 4: Ambilight -->
    <div id="panel-amb" class="panel">
      <div id="ambPreview" class="color-preview-box" style="background-color: #222;"> Ambilight</div>

      <div class="control-group">
        <div class="control-header"><span data-i18n="amb_monitor">Schermo</span></div>
        <select id="ambMonitor" style="padding:10px; border-radius:8px; background:#222630; color:#fff; border:1px solid var(--card-border);"></select>
      </div>

      <div class="control-group">
        <div class="control-header">
          <span data-i18n="amb_fps">Frequenza</span>
          <span id="valAmbFps" class="control-value">5 /s</span>
        </div>
        <input type="range" id="sliderAmbFps" min="1" max="15" step="1" value="5" oninput="document.getElementById('valAmbFps').textContent = this.value + ' /s'">
      </div>

      <button id="btnAmb" class="btn btn-primary" data-i18n="amb_start" onclick="toggleAmbilight()" style="padding:12px;">Avvia Ambilight</button>
      <div style="font-size:0.8rem; color:var(--text-muted);" data-i18n="amb_hint">La lampada segue il colore medio dello schermo, stile Philips Hue.</div>
    </div>
  </div>

  <footer style="text-align:center; font-size:0.8rem; color:var(--text-muted); padding:8px;">
    <span data-i18n="footer_support">Ti piace openliyadi? Offrici un caffè:</span>
    <a href="https://buymeacoffee.com/dr_gaussx" target="_blank" rel="noopener" style="color:var(--warning); font-weight:600;">buymeacoffee.com/dr_gaussx</a>
  </footer>

  <!-- Scanner Modal -->  <div id="scannerModal" class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h3 data-i18n="modal_title">Dispositivi Bluetooth (BLE)</h3>
        <button class="btn btn-secondary" data-i18n="close" onclick="closeScanner()">Chiudi</button>
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span id="scanStatus" style="font-size:0.85rem; color:var(--text-muted);">Pronto per la scansione</span>
        <button id="btnScan" class="btn btn-primary" data-i18n="scan_btn" onclick="startScan()">Avvia Scansione</button>
      </div>
      <div id="deviceList" class="device-list">
        <div style="text-align:center; color:var(--text-muted); padding:20px;">Clicca su "Avvia Scansione" per trovare la lampada</div>
      </div>
    </div>
  </div>

  <script>
    // --- i18n: italiano / inglese dalla lingua del browser ---
    const LANG = (navigator.language || "en").toLowerCase().startsWith("it") ? "it" : "en";
    const I18N = {
      en: {
        tab_rgb: "🎨 Color / HSI", tab_cct: "☀️ CCT Studio", tab_fx: "⚡ 24 Effects",
        tab_amb: "🖥️ Ambilight",
        power_title: "On/Off", hue: "Hue", sat: "Saturation", bri: "Brightness",
        presets: "Quick colors", cct_temp: "Color temperature", cct_bri: "CCT brightness",
        k_presets: "Photo Kelvin presets",
        k2700: "Candlelight", k3200: "Studio tungsten", k4000: "Natural white",
        k5600: "Standard daylight", k6500: "Overcast / D65", k8500: "Cold sky",
        fx_speed: "Effect speed (Frequency)", fx_bri: "Effect brightness",
        fx_select: "Select scene effect",
        footer_support: "Like openliyadi? Buy us a coffee:",
        amb_monitor: "Screen", amb_fps: "Refresh rate", amb_start: "Start Ambilight",
        amb_stop: "Stop", amb_hint: "The lamp follows the average screen color, Philips Hue style.",
        modal_title: "Bluetooth (BLE) devices", close: "Close",
        scan_btn: "Start scan", scan_ready: "Ready to scan",
        scanning: "Scanning (12s)...", found: n => `Found ${n} devices`,
        searching: "Searching BLE devices...", none_found: "No devices found. Make sure the lamp is on.",
        scan_err: "Scan error", connecting_to: a => `Connecting to ${a}...`,
        conn_err: "Connection error: ", lamp: "⭐ (Lamp)", connect: "Connect",
        st_connected: a => `Connected (${a})`, st_connected_noaddr: "Connected",
        st_disconnected: a => `Disconnected (${a})`, st_disconnected_click: "Disconnected (click)"
      },
      it: {
        tab_rgb: "🎨 Colore / HSI", tab_cct: "☀️ Studio CCT", tab_fx: "⚡ 24 Effetti",
        tab_amb: "🖥️ Ambilight",
        power_title: "Accendi/Spegni", hue: "Tonalità (Hue)", sat: "Saturazione", bri: "Luminosità",
        presets: "Colori Rapidi", cct_temp: "Temperatura Colore", cct_bri: "Luminosità CCT",
        k_presets: "Preset Fotografici Kelvin",
        k2700: "Lume / Candela", k3200: "Tungsteno Studio", k4000: "Bianco Naturale",
        k5600: "Daylight Standard", k6500: "Nuvoloso / D65", k8500: "Cielo Freddo",
        fx_speed: "Velocità Effetto (Frequency)", fx_bri: "Luminosità Effetto",
        fx_select: "Seleziona Effetto Scena",
        footer_support: "Ti piace openliyadi? Offrici un caffè:",
        amb_monitor: "Schermo", amb_fps: "Frequenza", amb_start: "Avvia Ambilight",
        amb_stop: "Ferma", amb_hint: "La lampada segue il colore medio dello schermo, stile Philips Hue.",
        modal_title: "Dispositivi Bluetooth (BLE)", close: "Chiudi",
        scan_btn: "Avvia Scansione", scan_ready: "Pronto per la scansione",
        scanning: "Scansione in corso (12s)...", found: n => `Trovati ${n} dispositivi`,
        searching: "Ricerca dispositivi BLE in corso...", none_found: "Nessun dispositivo rilevato. Assicurati che la lampada sia accesa.",
        scan_err: "Errore durante la scansione", connecting_to: a => `Connessione a ${a}...`,
        conn_err: "Errore di connessione: ", lamp: "⭐ (Lampada)", connect: "Connetti",
        st_connected: a => `Connesso (${a})`, st_connected_noaddr: "Connesso",
        st_disconnected: a => `Disconnesso (${a})`, st_disconnected_click: "Disconnesso (Clicca)"
      }
    };
    function t(k, arg) {
      const v = (I18N[LANG] && I18N[LANG][k] !== undefined) ? I18N[LANG][k] : I18N.en[k];
      return typeof v === "function" ? v(arg) : (v !== undefined ? v : k);
    }
    function applyI18n() {
      document.documentElement.lang = LANG;
      document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
      document.querySelectorAll("[data-i18n-title]").forEach(el => { el.title = t(el.dataset.i18nTitle); });
      document.getElementById("scanStatus").textContent = t("scan_ready");
    }
    let ws = null;
    let currentPower = false;
    let currentEffect = "Flash";
    let isConnected = false;

    // Connessione WebSocket
    function connectWS() {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${proto}//${window.location.host}/ws`);

      ws.onopen = () => console.log("WebSocket collegato");
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "status") updateUIState(msg.data);
        } catch (err) { console.error(err); }
      };
      ws.onclose = () => {
        console.warn("WebSocket chiuso, riconnessione tra 2s...");
        setTimeout(connectWS, 2000);
      };
    }
    connectWS();
    applyI18n();

    function sendWS(action, data) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action, data }));
      }
    }

    function updateUIState(s) {
      isConnected = s.connected;
      currentPower = s.power;

      // Badge
      const badge = document.getElementById("statusBadge");
      const txt = document.getElementById("statusText");
      if (s.connected) {
        badge.className = "status-badge connected";
        txt.textContent = s.address ? t("st_connected", s.address) : t("st_connected_noaddr");
      } else {
        badge.className = "status-badge";
        txt.textContent = s.address ? t("st_disconnected", s.address) : t("st_disconnected_click");
      }

      // Power button
      const pBtn = document.getElementById("powerBtn");
      if (s.power) pBtn.classList.add("on");
      else pBtn.classList.remove("on");

      // CCT
      if (s.cct) {
        document.getElementById("sliderCct").value = s.cct.kelvin;
        document.getElementById("valCct").textContent = `${s.cct.kelvin} K`;
        document.getElementById("sliderBriCct").value = s.cct.brightness;
        document.getElementById("valBriCct").textContent = `${s.cct.brightness}%`;
        updateCctPreview(s.cct.kelvin);
      }

      // HSI
      if (s.hsi) {
        document.getElementById("sliderHue").value = s.hsi.hue;
        document.getElementById("valHue").textContent = `${s.hsi.hue}°`;
        document.getElementById("sliderSat").value = s.hsi.saturation;
        document.getElementById("valSat").textContent = `${s.hsi.saturation}%`;
        document.getElementById("sliderBriHsi").value = s.hsi.brightness;
        document.getElementById("valBriHsi").textContent = `${s.hsi.brightness}%`;
        updateHsiPreview(s.hsi.hue, s.hsi.saturation, s.hsi.brightness);
      }
    }

    // Tabs
    function setTab(name) {
      document.querySelectorAll(".tab-btn").forEach((b, i) => {
        b.classList.toggle("active", ["rgb", "cct", "fx", "amb"][i] === name);
      });
      document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
      document.getElementById(`panel-${name}`).classList.add("active");
    }

    // Power Toggle
    function togglePower() {
      currentPower = !currentPower;
      sendWS("power", { state: currentPower });
    }

    // HSI / RGB Handlers
    function onHsiInput() {
      const hue = parseInt(document.getElementById("sliderHue").value);
      const sat = parseInt(document.getElementById("sliderSat").value);
      const bri = parseInt(document.getElementById("sliderBriHsi").value);
      document.getElementById("valHue").textContent = `${hue}°`;
      document.getElementById("valSat").textContent = `${sat}%`;
      document.getElementById("valBriHsi").textContent = `${bri}%`;
      updateHsiPreview(hue, sat, bri);
      sendWS("hsi", { hue, saturation: sat, brightness: bri });
    }

    function updateHsiPreview(h, s, b) {
      const box = document.getElementById("colorPreview");
      const rgb = hsvToRgb(h / 360, s / 100, b / 100);
      const hex = rgbToHex(rgb[0], rgb[1], rgb[2]);
      box.style.backgroundColor = hex;
      box.textContent = hex.toUpperCase();
      box.style.color = b > 50 && s < 60 ? "#000" : "#fff";
    }

    function setHex(hex) {
      const rgb = hexToRgb(hex);
      const hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
      const hue = Math.round(hsv[0] * 360);
      const sat = Math.round(hsv[1] * 100);
      const bri = Math.round(hsv[2] * 100);
      document.getElementById("sliderHue").value = hue;
      document.getElementById("sliderSat").value = sat;
      document.getElementById("sliderBriHsi").value = bri;
      onHsiInput();
    }

    // CCT Handlers
    function onCctInput() {
      const k = parseInt(document.getElementById("sliderCct").value);
      const bri = parseInt(document.getElementById("sliderBriCct").value);
      document.getElementById("valCct").textContent = `${k} K`;
      document.getElementById("valBriCct").textContent = `${bri}%`;
      updateCctPreview(k);
      sendWS("cct", { kelvin: k, brightness: bri });
    }

    function setKelvin(k) {
      document.getElementById("sliderCct").value = k;
      onCctInput();
    }

    function updateCctPreview(k) {
      const box = document.getElementById("cctPreview");
      box.textContent = `${k} K`;
      const ratio = (k - 2500) / (8500 - 2500);
      // sfumatura calda -> fredda
      const r = Math.round(255 - ratio * 50);
      const g = Math.round(180 + ratio * 40);
      const b = Math.round(100 + ratio * 155);
      box.style.backgroundColor = `rgb(${r},${g},${b})`;
      box.style.color = "#111";
    }

    // FX Handlers
    function loadEffects() {
      fetch("/api/effects")
        .then(r => r.json())
        .then(effects => {
          const grid = document.getElementById("fxGrid");
          grid.innerHTML = "";
          effects.forEach(eff => {
            const card = document.createElement("div");
            card.className = "fx-card" + (eff.name === currentEffect ? " active" : "");
            card.innerHTML = `<div class="fx-title">${eff.name}</div><div class="fx-cat">${eff.cat}</div>`;
            card.onclick = () => selectEffect(eff.name, card);
            grid.appendChild(card);
          });
        });
    }
    loadEffects();

    function selectEffect(name, el) {
      currentEffect = name;
      document.querySelectorAll(".fx-card").forEach(c => c.classList.remove("active"));
      if (el) el.classList.add("active");
      onFxParamChange();
    }

    function onFxParamChange() {
      const spd = parseInt(document.getElementById("sliderFxSpeed").value);
      const bri = parseInt(document.getElementById("sliderFxBri").value);
      document.getElementById("valFxSpeed").textContent = `${spd} / 20`;
      document.getElementById("valFxBri").textContent = `${bri}%`;
      sendWS("effect", { effect: currentEffect, speed: spd, brightness: bri });
    }

    // Ambilight
    let ambOn = false, ambPoll = null;
    function loadMonitors() {
      fetch("/api/ambilight/monitors")
        .then(r => r.json())
        .then(data => {
          const sel = document.getElementById("ambMonitor");
          sel.innerHTML = "";
          (data.monitors || []).forEach(m => {
            const o = document.createElement("option");
            o.value = m.index;
            o.textContent = `#${m.index} ${m.width}x${m.height}${m.primary ? " (main)" : ""}`;
            sel.appendChild(o);
          });
        })
        .catch(() => {});
    }
    loadMonitors();

    function toggleAmbilight() {
      const btn = document.getElementById("btnAmb");
      if (!ambOn) {
        const monitor = parseInt(document.getElementById("ambMonitor").value || "1");
        const fps = parseInt(document.getElementById("sliderAmbFps").value || "5");
        fetch("/api/ambilight/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ monitor, fps })
        }).then(() => {
          ambOn = true;
          btn.textContent = t("amb_stop");
          ambPoll = setInterval(pollAmbilight, 1200);
        }).catch(err => alert(t("conn_err") + err.message));
      } else {
        fetch("/api/ambilight/stop", { method: "POST" }).then(() => {
          ambOn = false;
          btn.textContent = t("amb_start");
          if (ambPoll) { clearInterval(ambPoll); ambPoll = null; }
        });
      }
    }

    function pollAmbilight() {
      fetch("/api/ambilight/status")
        .then(r => r.json())
        .then(s => {
          if (!s.running && ambOn) {
            ambOn = false;
            document.getElementById("btnAmb").textContent = t("amb_start");
            if (ambPoll) { clearInterval(ambPoll); ambPoll = null; }
            return;
          }
          const [r, g, b] = s.last_rgb || [0, 0, 0];
          const box = document.getElementById("ambPreview");
          const hex = rgbToHex(r, g, b).toUpperCase();
          box.style.backgroundColor = hex;
          box.textContent = hex;
        })
        .catch(() => {});
    }

    // Modal Scanner
    function openScanner() {
      document.getElementById("scannerModal").classList.add("open");
    }
    function closeScanner() {
      document.getElementById("scannerModal").classList.remove("open");
    }

    function startScan() {
      const btn = document.getElementById("btnScan");
      const st = document.getElementById("scanStatus");
      const list = document.getElementById("deviceList");
      btn.disabled = true;
      st.textContent = t("scanning");
      list.innerHTML = `<div style="text-align:center; padding:20px; color:#9ca3af;">${t("searching")}</div>`;

      fetch("/api/scan", { method: "POST" })
        .then(r => r.json())
        .then(data => {
          btn.disabled = false;
          st.textContent = t("found", data.devices.length);
          list.innerHTML = "";
          if (data.devices.length === 0) {
            list.innerHTML = `<div style="text-align:center; padding:20px;">${t("none_found")}</div>`;
            return;
          }
          data.devices.forEach(d => {
            const item = document.createElement("div");
            item.className = "device-item" + (d.is_lamp ? " is-lamp" : "");
            item.innerHTML = `
              <div>
                <div class="device-name">${d.name} ${d.is_lamp ? t("lamp") : ""}</div>
                <div class="device-addr">${d.address} ${d.rssi ? `| ${d.rssi} dBm` : ""}</div>
              </div>
              <button class="btn btn-primary" onclick="connectTo('${d.address}')">${t("connect")}</button>
            `;
            list.appendChild(item);
          });
        })
        .catch(err => {
          btn.disabled = false;
          st.textContent = t("scan_err");
          list.innerHTML = `<div style="color:#ef4444; padding:10px;">${err.message}</div>`;
        });
    }

    function connectTo(addr) {
      const st = document.getElementById("scanStatus");
      st.textContent = t("connecting_to", addr);
      fetch("/api/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: addr })
      })
      .then(r => r.json())
      .then(res => {
        closeScanner();
      })
      .catch(err => {
        alert(t("conn_err") + err.message);
      });
    }

    // Color conversion helpers
    function hsvToRgb(h, s, v) {
      let r, g, b, i = Math.floor(h * 6), f = h * 6 - i, p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
      switch (i % 6) {
        case 0: r = v; g = t; b = p; break; case 1: r = q; g = v; b = p; break;
        case 2: r = p; g = v; b = t; break; case 3: r = p; g = q; b = v; break;
        case 4: r = t; g = p; b = v; break; case 5: r = v; g = p; b = q; break;
      }
      return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
    }
    function rgbToHex(r, g, b) {
      return "#" + [r, g, b].map(x => x.toString(16).padStart(2, "0")).join("");
    }
    function hexToRgb(hex) {
      const num = parseInt(hex.slice(1), 16);
      return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
    }
    function rgbToHsv(r, g, b) {
      r /= 255; g /= 255; b /= 255;
      let max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min, h, s = max === 0 ? 0 : d / max, v = max;
      if (max === min) h = 0;
      else {
        switch (max) {
          case r: h = (g - b) / d + (g < b ? 6 : 0); break;
          case g: h = (b - r) / d + 2; break;
          case b: h = (r - g) / d + 4; break;
        }
        h /= 6;
      }
      return [h, s, v];
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return HTML_PAGE


def run(host: str = "0.0.0.0", port: int = 8080, open_browser: bool = True):
    """Avvia il server web."""
    if open_browser:
        import threading
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Avvia il server Web LEDLYD")
    parser.add_argument("--port", type=int, default=8080, help="Porta HTTP (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="Host binding (default: 0.0.0.0)")
    parser.add_argument("--no-browser", action="store_true", help="Non aprire il browser automaticamente")
    args = parser.parse_args()

    run(host=args.host, port=args.port, open_browser=not args.no_browser)

"""
Modulo del protocollo completo per lampade LEDLYD / LTF_MWRGB.
Reverse-engineered direttamente da assets/apps/__UNI__6FB700B/www/app-service.js
"""

HEAD = 0xAA

# Mappatura comandi base
CMD = {
    "LIGHT": 1,
    "SPEED": 2,
    "FIXED_MODE": 3,
    "PALETTE": 4,
    "DIY_MODE": 5,
    "MUSIC_MODE": 6,
    "MIC_SET": 7,
    "DEVICE_SWITCH": 8,
    "RGB_SWITCH": 9,
    "SET_PWM": 10,
    "OPEN_CODE": 11,
    "CLOSE_CODE": 12,
    # Modalità a 10-byte (primo byte del frame)
    "OFF_CODE": 0,
    "CCT_CODE": 1,
    "HSI_CODE": 2,
    "MLM_CODE": 3,  # Effetti scena dinamici
    "APP_CODE": 4,
}

SERVICE_UUID = "0000FFF0-0000-1000-8000-00805F9B34FB"
TX_UUID = "0000FFF3-0000-1000-8000-00805F9B34FB"
RX_UUID = "0000FFF4-0000-1000-8000-00805F9B34FB"

TARGET_NAMES = ("LTF_MWRGB", "LYD_MWRGB", "Bough_Systems", "LYDBough_Systems")

# 24 Effetti ufficiali dell'app originale LEDLYD (moduli EEF-P e 820a)
# id: 1..24, modsub corrispondente alla logica interna
EFFECTS = [
    {"id": 1,  "name": "Flash",        "cat": "Flash",      "modsub": 1},
    {"id": 2,  "name": "Flash 2",      "cat": "Flash",      "modsub": 2},
    {"id": 3,  "name": "TV Screen",    "cat": "Flash",      "modsub": 3},
    {"id": 4,  "name": "Candle",       "cat": "Candle",     "modsub": 6},
    {"id": 5,  "name": "Flame 1",      "cat": "Candle",     "modsub": 10},
    {"id": 6,  "name": "Flame 2",      "cat": "Candle",     "modsub": 11},
    {"id": 7,  "name": "Police",       "cat": "Emergency",  "modsub": 7},
    {"id": 8,  "name": "Ambulance",    "cat": "Emergency",  "modsub": 8},
    {"id": 9,  "name": "Fire Truck",   "cat": "Emergency",  "modsub": 9},
    {"id": 10, "name": "Strobe 1",     "cat": "Strobe",     "modsub": 12},
    {"id": 11, "name": "Strobe 2",     "cat": "Strobe",     "modsub": 13},
    {"id": 12, "name": "Strobe 3",     "cat": "Strobe",     "modsub": 14},
    {"id": 13, "name": "Chase 1",      "cat": "Chase",      "modsub": 4},
    {"id": 14, "name": "Chase 2",      "cat": "Chase",      "modsub": 15},
    {"id": 15, "name": "Chase 3",      "cat": "Chase",      "modsub": 5},
    {"id": 16, "name": "Firework 1",   "cat": "Firework",   "modsub": 16},
    {"id": 17, "name": "Firework 2",   "cat": "Firework",   "modsub": 17},
    {"id": 18, "name": "Firework 3",   "cat": "Firework",   "modsub": 18},
    {"id": 19, "name": "Club 1",       "cat": "Party",      "modsub": 19},
    {"id": 20, "name": "Club 2",       "cat": "Party",      "modsub": 20},
    {"id": 21, "name": "Romantic",     "cat": "Party",      "modsub": 21},
    {"id": 22, "name": "Music",        "cat": "Audio/Wave", "modsub": 22},
    {"id": 23, "name": "Wave 1",       "cat": "Audio/Wave", "modsub": 23},
    {"id": 24, "name": "Wave 2",       "cat": "Audio/Wave", "modsub": 24},
]

EFFECT_BY_NAME = {eff["name"].lower(): eff for eff in EFFECTS}
EFFECT_BY_ID = {eff["id"]: eff for eff in EFFECTS}


def checksum(cmd: int, payload: list | bytes) -> int:
    """Funzione di checksum dell'app: u(t, e) = (0xAA + cmd + len + sum(payload)) & 0xFF"""
    return (HEAD + cmd + len(payload) + sum(payload)) & 0xFF


def build_packet(cmd: int, payload: list | bytes) -> bytes:
    p = list(payload)
    return bytes([HEAD, cmd, len(p)] + p + [checksum(cmd, p)])


def pkt_open() -> bytes:
    """Accende la lampada: AA 0B 01 00 B6"""
    return build_packet(CMD["OPEN_CODE"], [0])


def pkt_close() -> bytes:
    """Spegne la lampada: AA 0C 01 00 B7"""
    return build_packet(CMD["CLOSE_CODE"], [0])


def pkt_rgb(r: int, g: int, b: int, area: int = 0) -> bytes:
    """Imposta il colore RGB diretto (area: 0=tutti, 1=zona1, 2=zona2)"""
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return build_packet(CMD["PALETTE"], [area, r, g, b])


def pkt_brightness(brightness: int, area: int = 0) -> bytes:
    """Imposta la luminosità generale 0-100%"""
    brightness = max(0, min(100, int(brightness)))
    return build_packet(CMD["LIGHT"], [area, brightness])


def pkt_speed(speed: int, area: int = 0) -> bytes:
    """Imposta la velocità effetti 0-100%"""
    speed = max(0, min(100, int(speed)))
    return build_packet(CMD["SPEED"], [area, speed])


def _pkt_pair(cmd: int, a: int, b: int) -> bytes:
    return build_packet(cmd, [a, b])


def pkt_fixed_mode(area: int, mode: int) -> bytes:
    """Modalità fissa (area, mode)"""
    return _pkt_pair(CMD["FIXED_MODE"], area, mode)


def pkt_mic(a: int, b: int) -> bytes:
    return _pkt_pair(CMD["MIC_SET"], a, b)


def pkt_device_switch(a: int, b: int) -> bytes:
    return _pkt_pair(CMD["DEVICE_SWITCH"], a, b)


def pkt_rgb_switch(area: int, on_off: int) -> bytes:
    """Power zona RGB (area, 0/1): usato dal toggle on/off della pagina HSI."""
    return _pkt_pair(CMD["RGB_SWITCH"], area, 1 if on_off else 0)


def pkt_pwm(area: int, value: int) -> bytes:
    value = max(0, min(100, int(value)))
    return _pkt_pair(CMD["SET_PWM"], area, value)


def pkt_diy_seg(t: int, total: int, index: int, a: int,
                r: int, g: int, b: int) -> bytes:
    """Singolo segmento DIY (invio segmentato con ACK, vedi PROTOCOL.md §5)."""
    return build_packet(CMD["DIY_MODE"], [t, total, index, a, r, g, b])


def pkt_music_seg(t: int, total: int, index: int, a: int,
                  r: int, g: int, b: int) -> bytes:
    """Singolo segmento musica (come DIY)."""
    return build_packet(CMD["MUSIC_MODE"], [t, total, index, a, r, g, b])


def pkt_mode10(mode: int, modsub: int = 0, p: int = 100, k: int = 56,
               h: int = 0, s: int = 0, flashmod: int = 0, tnum: int = 0, freq: int = 1) -> bytes:
    """
    Struttura dei pacchetti a 10 byte raw:
    [mode, modsub, P, K, H_low, H_high, S, flashmod, Tnum, Freq]
    - mode: 0=OFF, 1=CCT, 2=HSI, 3=MLM/Effetti
    - modsub: sub-id effetto o modalità
    - P: Potenza / Luminosità (0-100)
    - K: Kelvin / 100 (es. 2500K -> 25, 5600K -> 56, 8500K -> 85)
    - H: Hue (0-360), little-endian: [H%256, H//256]
    - S: Saturation (0-100)
    - flashmod: modalità flash / strobe
    - tnum: timer o parametro tempo
    - freq: velocità/frequenza (1-20)
    Nessun clamp qui: l'app invia i valori raw di gdata (es. K=0, Freq=0
    di default); le validazioni stanno nei wrapper di alto livello.
    """
    return bytes([
        mode & 0xFF,
        modsub & 0xFF,
        p & 0xFF,
        k & 0xFF,
        h % 256,
        h // 256,
        s & 0xFF,
        flashmod & 0xFF,
        tnum & 0xFF,
        freq & 0xFF
    ])


def pkt_cct(kelvin: int = 5600, brightness: int = 100, modsub: int = 0) -> bytes:
    """Modalità temperatura colore bianco (2500K - 8500K) + luminosità (0-100)"""
    k_byte = int(round(kelvin / 100.0))
    k_byte = max(25, min(85, k_byte))
    return pkt_mode10(mode=CMD["CCT_CODE"], modsub=modsub, p=brightness, k=k_byte)


def pkt_hsi(hue: int = 0, saturation: int = 100, brightness: int = 100, modsub: int = 0) -> bytes:
    """Modalità HSI (Hue 0-360°, Saturation 0-100%, Brightness 0-100%).
    Hue 0 viene mandato come 360: il firmware scarta H=0.
    K=0 esplicito: fuori dal modo CCT la temperatura è ignorata."""
    if int(hue) % 360 == 0:
        hue = 360
    return pkt_mode10(mode=CMD["HSI_CODE"], modsub=modsub, p=brightness, k=0,
                      h=hue, s=saturation)


def rgb_to_hsv(r: int, g: int, b: int) -> tuple[int, int, int]:
    """RGB 0-255 -> (H 0-360, S 0-100, V 0-100), stessa scala dei cursori dell'app."""
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    d = mx - mn
    if d == 0:
        h = 0
    elif mx == rf:
        h = (60 * ((gf - bf) / d) + 360) % 360
    elif mx == gf:
        h = 60 * ((bf - rf) / d) + 120
    else:
        h = 60 * ((rf - gf) / d) + 240
    s = 0 if mx == 0 else (d / mx) * 100
    return round(h), round(s), round(mx * 100)


def pkt_rgb_hsi(r: int, g: int, b: int, brightness: int | None = None) -> bytes:
    """Colore RGB arbitrario come pacchetto HSI raw a 10 byte (percorso reale
    del color picker: changeColor -> hsiMode). Se brightness e' None usa V del colore.
    Default campi come gdata dell'app: modsub=0, K=0, flashmod=0, Tnum=100, Freq=0."""
    h, s, v = rgb_to_hsv(r, g, b)
    if h == 0:
        h = 360  # il firmware scarta H=0 (solo il rosso falliva): rosso = 360
    return pkt_mode10(mode=CMD["HSI_CODE"], modsub=0, p=v if brightness is None else brightness,
                      k=0, h=h, s=s, flashmod=0, tnum=100, freq=0)


def pkt_effect(effect_id_or_name: int | str, brightness: int = 100, speed: int = 1) -> bytes:
    """Attiva uno dei 24 effetti di scena con luminosità (0-100) e velocità (1-20)"""
    if isinstance(effect_id_or_name, int):
        eff = EFFECT_BY_ID.get(effect_id_or_name)
    else:
        eff = EFFECT_BY_NAME.get(str(effect_id_or_name).strip().lower())
        if not eff:
            # ricerca parziale
            for k, v in EFFECT_BY_NAME.items():
                if str(effect_id_or_name).strip().lower() in k:
                    eff = v
                    break

    if not eff:
        raise ValueError(f"Effetto non trovato: {effect_id_or_name}")

    return pkt_mode10(mode=CMD["MLM_CODE"], modsub=eff["modsub"], p=brightness,
                      k=0, freq=speed)


# Fallback per lo spegnimento quando non si conosce lo stato (testato dal vivo):
# pacchetto modo con mode=0, stile CCT 5600K/80%.
OFF_FALLBACK = bytes([0, 0, 80, 56, 0, 0, 0, 0, 100, 0])


def pkt_off_last(last_mode10: bytes | None) -> bytes:
    """Spegnimento vero (verificato dal vivo): l'ultimo pacchetto modo a 10 byte
    con il primo byte forzato a 0 (OFF_CODE), come fa l'app (onoffs=false).
    CLOSE_CODE headed riduce solo la luminosita', non spegne."""
    if last_mode10 and len(last_mode10) == 10:
        return bytes([0]) + bytes(last_mode10[1:])
    return bytes(OFF_FALLBACK)

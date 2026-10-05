"""openliyadi — open BLE control for Liyadi RGB lights (LP540-PRO & co). MIT."""

__version__ = "0.1.0"

from .protocol import (
    HEAD,
    CMD,
    SERVICE_UUID,
    TX_UUID,
    RX_UUID,
    TARGET_NAMES,
    EFFECTS,
    EFFECT_BY_ID,
    EFFECT_BY_NAME,
    OFF_FALLBACK,
    checksum,
    build_packet,
    pkt_open,
    pkt_close,
    pkt_rgb,
    pkt_brightness,
    pkt_speed,
    pkt_fixed_mode,
    pkt_mic,
    pkt_device_switch,
    pkt_rgb_switch,
    pkt_pwm,
    pkt_diy_seg,
    pkt_music_seg,
    pkt_mode10,
    pkt_cct,
    pkt_hsi,
    rgb_to_hsv,
    pkt_rgb_hsi,
    pkt_effect,
    pkt_off_last,
)
from .controller import LEDController
from .scanner import classify, scan_once, probe_devices
from .ambilight import Ambilight, list_monitors, grab_average, grab_spot, grab_center, grab_points
from .music import MusicSync, list_sources, band_levels

__all__ = [
    "__version__",
    "HEAD", "CMD", "SERVICE_UUID", "TX_UUID", "RX_UUID", "TARGET_NAMES",
    "EFFECTS", "EFFECT_BY_ID", "EFFECT_BY_NAME", "OFF_FALLBACK",
    "checksum", "build_packet",
    "pkt_open", "pkt_close", "pkt_rgb", "pkt_brightness", "pkt_speed",
    "pkt_fixed_mode", "pkt_mic", "pkt_device_switch", "pkt_rgb_switch",
    "pkt_pwm", "pkt_diy_seg", "pkt_music_seg",
    "pkt_mode10", "pkt_cct", "pkt_hsi", "rgb_to_hsv", "pkt_rgb_hsi",
    "pkt_effect", "pkt_off_last",
    "LEDController",
    "classify", "scan_once", "probe_devices",
    "Ambilight", "list_monitors", "grab_average", "grab_spot",
    "grab_center", "grab_points",
    "MusicSync", "list_sources", "band_levels",
]

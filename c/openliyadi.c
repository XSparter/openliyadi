/*
 * openliyadi — MIT License, see ../LICENSE
 *
 * Implementation. Pure C99, no dependencies, no heap allocation:
 * every builder writes into a caller-provided buffer.
 */

#include "openliyadi.h"

const char *OLY_NAMES[OLY_NAME_COUNT] = {
    "LTF_MWRGB",
    "LYD_MWRGB",
    "Bough_Systems",
    "LYDBough_Systems"
};

const oly_effect_t OLY_EFFECTS[OLY_EFFECT_COUNT] = {
    {  1, "Flash",      "Flash",      1 },
    {  2, "Flash 2",    "Flash",      2 },
    {  3, "TV",         "Flash",      3 },
    {  4, "Candle",     "Candle",     6 },
    {  5, "Flame 1",    "Candle",    10 },
    {  6, "Flame 2",    "Candle",    11 },
    {  7, "Police",     "Emergency",  7 },
    {  8, "AMB",        "Emergency",  8 },
    {  9, "FireTruck",  "Emergency",  9 },
    { 10, "Strobe 1",   "Strobe",    12 },
    { 11, "Strobe 2",   "Strobe",    13 },
    { 12, "Strobe 3",   "Strobe",    14 },
    { 13, "Chase 1",    "Chase",      4 },
    { 14, "Chase 2",    "Chase",     15 },
    { 15, "Chase 3",    "Chase",      5 },
    { 16, "Firework 1", "Firework",  16 },
    { 17, "Firework 2", "Firework",  17 },
    { 18, "Firework 3", "Firework",  18 },
    { 19, "Club 1",     "Party",     19 },
    { 20, "Club 2",     "Party",     20 },
    { 21, "Romantic",   "Party",     21 },
    { 22, "Music",      "Audio/Wave", 22 },
    { 23, "Wave 1",     "Audio/Wave", 23 },
    { 24, "Wave 2",     "Audio/Wave", 24 },
};

uint8_t oly_checksum(uint8_t cmd, const uint8_t *payload, size_t len) {
    unsigned sum = (unsigned)OLY_HEAD + (unsigned)cmd + (unsigned)len;
    size_t i;
    for (i = 0; i < len; i++)
        sum += payload[i];
    return (uint8_t)(sum & 0xFFu);
}

size_t oly_build(uint8_t cmd, const uint8_t *payload, size_t len,
                 uint8_t *out, size_t out_sz) {
    size_t i;
    if (out_sz < len + 4)
        return 0;
    out[0] = OLY_HEAD;
    out[1] = cmd;
    out[2] = (uint8_t)len;
    for (i = 0; i < len; i++)
        out[i + 3] = payload[i];
    out[len + 3] = oly_checksum(cmd, payload, len);
    return len + 4;
}

size_t oly_open(uint8_t *out, size_t out_sz) {
    const uint8_t p[1] = { 0 };
    return oly_build(OLY_OPEN_CODE, p, 1, out, out_sz);
}

size_t oly_close(uint8_t *out, size_t out_sz) {
    const uint8_t p[1] = { 0 };
    return oly_build(OLY_CLOSE_CODE, p, 1, out, out_sz);
}

static size_t oly_pair(uint8_t cmd, uint8_t a, uint8_t b,
                       uint8_t *out, size_t out_sz) {
    const uint8_t p[2] = { a, b };
    return oly_build(cmd, p, 2, out, out_sz);
}

size_t oly_light(uint8_t area, uint8_t brightness_0_100,
                 uint8_t *out, size_t out_sz) {
    if (brightness_0_100 > 100)
        brightness_0_100 = 100;
    return oly_pair(OLY_LIGHT, area, brightness_0_100, out, out_sz);
}

size_t oly_speed(uint8_t area, uint8_t speed_0_100,
                 uint8_t *out, size_t out_sz) {
    if (speed_0_100 > 100)
        speed_0_100 = 100;
    return oly_pair(OLY_SPEED, area, speed_0_100, out, out_sz);
}

size_t oly_fixed_mode(uint8_t area, uint8_t mode, uint8_t *out, size_t out_sz) {
    return oly_pair(OLY_FIXED_MODE, area, mode, out, out_sz);
}

size_t oly_palette(uint8_t area, uint8_t r, uint8_t g, uint8_t b,
                   uint8_t *out, size_t out_sz) {
    const uint8_t p[4] = { area, r, g, b };
    return oly_build(OLY_PALETTE, p, 4, out, out_sz);
}

static size_t oly_seg7(uint8_t cmd, uint8_t t, uint8_t total, uint8_t index,
                       uint8_t a, uint8_t r, uint8_t g, uint8_t b,
                       uint8_t *out, size_t out_sz) {
    const uint8_t p[7] = { t, total, index, a, r, g, b };
    return oly_build(cmd, p, 7, out, out_sz);
}

size_t oly_diy_seg(uint8_t t, uint8_t total, uint8_t index, uint8_t a,
                   uint8_t r, uint8_t g, uint8_t b,
                   uint8_t *out, size_t out_sz) {
    return oly_seg7(OLY_DIY_MODE, t, total, index, a, r, g, b, out, out_sz);
}

size_t oly_music_seg(uint8_t t, uint8_t total, uint8_t index, uint8_t a,
                     uint8_t r, uint8_t g, uint8_t b,
                     uint8_t *out, size_t out_sz) {
    return oly_seg7(OLY_MUSIC_MODE, t, total, index, a, r, g, b, out, out_sz);
}

size_t oly_mic(uint8_t a, uint8_t b, uint8_t *out, size_t out_sz) {
    return oly_pair(OLY_MIC_SET, a, b, out, out_sz);
}

size_t oly_device_switch(uint8_t a, uint8_t b, uint8_t *out, size_t out_sz) {
    return oly_pair(OLY_DEVICE_SWITCH, a, b, out, out_sz);
}

size_t oly_rgb_switch(uint8_t area, uint8_t on_off, uint8_t *out, size_t out_sz) {
    return oly_pair(OLY_RGB_SWITCH, area, on_off ? 1 : 0, out, out_sz);
}

size_t oly_pwm(uint8_t area, uint8_t v_0_100, uint8_t *out, size_t out_sz) {
    if (v_0_100 > 100)
        v_0_100 = 100;
    return oly_pair(OLY_SET_PWM, area, v_0_100, out, out_sz);
}

size_t oly_mode10(uint8_t mode, uint8_t modsub, uint8_t p, uint8_t k,
                  unsigned h, uint8_t s, uint8_t flashmod, uint8_t tnum,
                  uint8_t freq, uint8_t *out, size_t out_sz) {
    if (out_sz < 10)
        return 0;
    out[0] = mode;
    out[1] = modsub;
    out[2] = p;
    out[3] = k;
    out[4] = (uint8_t)(h % 256u);
    out[5] = (uint8_t)((h / 256u) & 0xFFu);
    out[6] = s;
    out[7] = flashmod;
    out[8] = tnum;
    out[9] = freq;
    return 10;
}

size_t oly_cct(int kelvin, int brightness, uint8_t *out, size_t out_sz) {
    int k, p;
    if (kelvin < 2500)
        kelvin = 2500;
    if (kelvin > 8500)
        kelvin = 8500;
    if (brightness < 0)
        brightness = 0;
    if (brightness > 100)
        brightness = 100;
    k = (kelvin + 50) / 100; /* round to K/100 byte */
    p = brightness;
    return oly_mode10(OLY_MODE_CCT, 0, (uint8_t)p, (uint8_t)k,
                      0, 0, 0, 0, 1, out, out_sz);
}

size_t oly_hsi(int hue, int saturation, int brightness,
               uint8_t *out, size_t out_sz) {
    unsigned h;
    if (saturation < 0)
        saturation = 0;
    if (saturation > 100)
        saturation = 100;
    if (brightness < 0)
        brightness = 0;
    if (brightness > 100)
        brightness = 100;
    h = (unsigned)(((hue % 360) + 360) % 360);
    if (h == 0)
        h = 360; /* firmware drops H=0 */
    return oly_mode10(OLY_MODE_HSI, 0, (uint8_t)brightness, 0, h,
                      (uint8_t)saturation, 0, 0, 1, out, out_sz);
}

void oly_rgb_to_hsv(uint8_t r, uint8_t g, uint8_t b,
                    int *h, int *s, int *v) {
    /* Integer math on 0..255, result H 0..359, S/V 0..100. */
    int mx = r, mn = r, d, hh = 0;
    if ((int)g > mx)
        mx = g;
    if ((int)b > mx)
        mx = b;
    if ((int)g < mn)
        mn = g;
    if ((int)b < mn)
        mn = b;
    d = mx - mn;
    if (d != 0) {
        if (mx == r)
            hh = ((int)(g - b) * 60) / d;
        else if (mx == (int)g)
            hh = ((int)(b - r) * 60) / d + 120;
        else
            hh = ((int)(r - g) * 60) / d + 240;
        if (hh < 0)
            hh += 360;
    }
    if (h)
        *h = hh;
    if (s)
        *s = (mx == 0) ? 0 : (d * 100) / mx;
    if (v)
        *v = (mx * 100) / 255;
}

size_t oly_rgb_hsi(uint8_t r, uint8_t g, uint8_t b, int brightness,
                   uint8_t *out, size_t out_sz) {
    int h, s, v;
    oly_rgb_to_hsv(r, g, b, &h, &s, &v);
    if (brightness >= 0) {
        if (brightness > 100)
            brightness = 100;
        v = brightness;
    }
    return oly_hsi(h, s, v, out, out_sz);
}

size_t oly_effect(int id, int brightness, int speed,
                  uint8_t *out, size_t out_sz) {
    int i;
    if (brightness < 0)
        brightness = 0;
    if (brightness > 100)
        brightness = 100;
    if (speed < 1)
        speed = 1;
    if (speed > 20)
        speed = 20;
    for (i = 0; i < OLY_EFFECT_COUNT; i++) {
        if (OLY_EFFECTS[i].id == id) {
            return oly_mode10(OLY_MODE_MLM, (uint8_t)OLY_EFFECTS[i].modsub,
                              (uint8_t)brightness, 0, 0, 0, 0, 0,
                              (uint8_t)speed, out, out_sz);
        }
    }
    return 0; /* unknown id */
}

static int oly_strieq(const char *a, const char *b) {
    while (*a && *b) {
        char ca = *a, cb = *b;
        if (ca >= 'A' && ca <= 'Z')
            ca = (char)(ca + ('a' - 'A'));
        if (cb >= 'A' && cb <= 'Z')
            cb = (char)(cb + ('a' - 'A'));
        if (ca != cb)
            return 0;
        a++;
        b++;
    }
    return *a == *b;
}

int oly_effect_find(const char *name) {
    int i;
    if (!name)
        return -1;
    for (i = 0; i < OLY_EFFECT_COUNT; i++) {
        if (oly_strieq(name, OLY_EFFECTS[i].name))
            return OLY_EFFECTS[i].id;
    }
    return -1;
}

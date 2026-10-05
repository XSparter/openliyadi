/*
 * openliyadi — MIT License, see ../LICENSE
 *
 * Open control library for Liyadi / LEDLYD RGB photo lights (e.g. LP540-PRO).
 * Pure C99, no dependencies. Transport-agnostic: feed the produced byte
 * packets to any BLE GATT write (service 0xFFF0, characteristic 0xFFF3).
 *
 * Packet formats (reverse engineered from LEDLYD Android app):
 *  - short: [0xAA, CMD, LEN, payload..., (0xAA+CMD+LEN+sum(payload)) & 0xFF]
 *  - mode10: raw 10 bytes [mode, modsub, P, K, H_lo, H_hi, S, flash, Tnum, Freq]
 */
#ifndef OPENLIYADI_H
#define OPENLIYADI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define OLY_HEAD 0xAA

/* Short command codes */
#define OLY_LIGHT         1
#define OLY_SPEED         2
#define OLY_FIXED_MODE    3
#define OLY_PALETTE       4
#define OLY_DIY_MODE      5
#define OLY_MUSIC_MODE    6
#define OLY_MIC_SET       7
#define OLY_DEVICE_SWITCH 8
#define OLY_RGB_SWITCH    9
#define OLY_SET_PWM      10
#define OLY_OPEN_CODE    11
#define OLY_CLOSE_CODE   12

/* First byte of raw 10-byte mode packets */
#define OLY_MODE_OFF 0
#define OLY_MODE_CCT 1
#define OLY_MODE_HSI 2
#define OLY_MODE_MLM 3
#define OLY_MODE_APP 4

/* GATT identifiers (full 128-bit strings) */
#define OLY_SVC_FFF0 "0000FFF0-0000-1000-8000-00805F9B34FB"
#define OLY_CHR_TX   "0000FFF3-0000-1000-8000-00805F9B34FB" /* phone -> lamp (write) */
#define OLY_CHR_RX   "0000FFF4-0000-1000-8000-00805F9B34FB" /* lamp -> phone (notify) */

/* BLE advertisement names used by compatible lamps */
#define OLY_NAME_COUNT 4
extern const char *OLY_NAMES[OLY_NAME_COUNT];

/* Max bytes of any packet this library produces (short max = 3 + 7 + 1). */
#define OLY_BUF_SIZE 12

/* ---- core ---------------------------------------------------------- */

/* Checksum: (HEAD + cmd + len + sum(payload)) & 0xFF */
uint8_t oly_checksum(uint8_t cmd, const uint8_t *payload, size_t len);

/*
 * Build a short headed packet into out[].
 * Returns bytes written (len + 4), or 0 if out_sz < len + 4.
 */
size_t oly_build(uint8_t cmd, const uint8_t *payload, size_t len,
                 uint8_t *out, size_t out_sz);

/* ---- short commands (return bytes written, 0 on buffer too small) --- */

size_t oly_open(uint8_t *out, size_t out_sz);            /* AA 0B 01 00 B6 */
size_t oly_close(uint8_t *out, size_t out_sz);           /* AA 0C 01 00 B7 */
size_t oly_light(uint8_t area, uint8_t brightness_0_100,
                 uint8_t *out, size_t out_sz);
size_t oly_speed(uint8_t area, uint8_t speed_0_100,
                 uint8_t *out, size_t out_sz);
size_t oly_fixed_mode(uint8_t area, uint8_t mode, uint8_t *out, size_t out_sz);
size_t oly_palette(uint8_t area, uint8_t r, uint8_t g, uint8_t b,
                   uint8_t *out, size_t out_sz);
size_t oly_diy_seg(uint8_t t, uint8_t total, uint8_t index, uint8_t a,
                   uint8_t r, uint8_t g, uint8_t b, uint8_t *out, size_t out_sz);
size_t oly_music_seg(uint8_t t, uint8_t total, uint8_t index, uint8_t a,
                     uint8_t r, uint8_t g, uint8_t b, uint8_t *out, size_t out_sz);
size_t oly_mic(uint8_t a, uint8_t b, uint8_t *out, size_t out_sz);
size_t oly_device_switch(uint8_t a, uint8_t b, uint8_t *out, size_t out_sz);
size_t oly_rgb_switch(uint8_t area, uint8_t on_off, uint8_t *out, size_t out_sz);
size_t oly_pwm(uint8_t area, uint8_t v_0_100, uint8_t *out, size_t out_sz);

/* ---- raw 10-byte mode packets (return 10, 0 on buffer too small) ---- */

/*
 * h: hue 0..360, sent little-endian [h%256, h/256].
 * Returns 10, or 0 if out_sz < 10.
 */
size_t oly_mode10(uint8_t mode, uint8_t modsub, uint8_t p, uint8_t k,
                  unsigned h, uint8_t s, uint8_t flashmod, uint8_t tnum,
                  uint8_t freq, uint8_t *out, size_t out_sz);

/* White temperature 2500..8500 K + brightness 0..100 (clamped). */
size_t oly_cct(int kelvin, int brightness, uint8_t *out, size_t out_sz);

/*
 * HSI color. hue 0 is sent as 360: firmware drops H=0.
 * ranges: hue 0..360, saturation 0..100, brightness 0..100.
 */
size_t oly_hsi(int hue, int saturation, int brightness,
               uint8_t *out, size_t out_sz);

/* RGB 0..255 -> H 0..360, S 0..100, V 0..100. */
void oly_rgb_to_hsv(uint8_t r, uint8_t g, uint8_t b,
                    int *h, int *s, int *v);

/*
 * Arbitrary RGB via the HSI raw packet (the color-picker path of the
 * original app). brightness<0 selects V of the color itself.
 */
size_t oly_rgb_hsi(uint8_t r, uint8_t g, uint8_t b, int brightness,
                   uint8_t *out, size_t out_sz);

/* ---- scene effects -------------------------------------------------- */

typedef struct {
    int id;            /* 1..24 */
    const char *name;
    const char *cat;
    int modsub;
} oly_effect_t;

#define OLY_EFFECT_COUNT 24
extern const oly_effect_t OLY_EFFECTS[OLY_EFFECT_COUNT];

/* Effect packet by id (1..24); brightness 0..100, speed 1..20. */
size_t oly_effect(int id, int brightness, int speed,
                  uint8_t *out, size_t out_sz);

/* Effect id by (case-insensitive) name, or -1. */
int oly_effect_find(const char *name);

#ifdef __cplusplus
}
#endif

#endif /* OPENLIYADI_H */

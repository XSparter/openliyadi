/*
 * openliyadi example — MIT License, see ../LICENSE
 *
 * Prints packets as hex and self-checks against known-good vectors.
 * Returns 0 on success, 1 on any mismatch.
 *
 * Build:
 *   gcc -std=c99 -Wall -Wextra -o example example.c openliyadi.c
 *   clang -std=c99 -Wall -Wextra -o example example.c openliyadi.c
 *   cl /W4 /std:clatest example.c openliyadi.c
 */

#include <stdio.h>
#include <string.h>

#include "openliyadi.h"

static void print_hex(const char *label, const uint8_t *p, size_t n) {
    size_t i;
    printf("%-10s (%2u) : ", label, (unsigned)n);
    for (i = 0; i < n; i++)
        printf("%02X%s", p[i], i + 1 < n ? " " : "");
    printf("\n");
}

static int fails = 0;

static void check(const char *label, const uint8_t *got, size_t got_n,
                  const uint8_t *want, size_t want_n) {
    if (got_n != want_n || memcmp(got, want, want_n) != 0) {
        printf("[FAIL] %s\n", label);
        fails++;
    } else {
        printf("[ok]   %s\n", label);
    }
    print_hex(label, got, got_n);
}

int main(void) {
    uint8_t b[OLY_BUF_SIZE];
    size_t n;

    /* OPEN: AA 0B 01 00 B6 */
    static const uint8_t WANT_OPEN[] = { 0xAA, 0x0B, 0x01, 0x00, 0xB6 };
    n = oly_open(b, sizeof b);
    check("open", b, n, WANT_OPEN, sizeof WANT_OPEN);

    /* CLOSE: AA 0C 01 00 B7 */
    static const uint8_t WANT_CLOSE[] = { 0xAA, 0x0C, 0x01, 0x00, 0xB7 };
    n = oly_close(b, sizeof b);
    check("close", b, n, WANT_CLOSE, sizeof WANT_CLOSE);

    /* brightness 100, area 0: AA 01 02 00 64 11 */
    static const uint8_t WANT_BRI[] = { 0xAA, 0x01, 0x02, 0x00, 0x64, 0x11 };
    n = oly_light(0, 100, b, sizeof b);
    check("light100", b, n, WANT_BRI, sizeof WANT_BRI);

    /* red via HSI: 02 00 64 00 68 01 64 00 64 00 (H=360, firmware drops H=0) */
    static const uint8_t WANT_RED[] =
        { 0x02, 0x00, 0x64, 0x00, 0x68, 0x01, 0x64, 0x00, 0x64, 0x00 };
    n = oly_rgb_hsi(255, 0, 0, -1, b, sizeof b);
    check("red-hsi", b, n, WANT_RED, sizeof WANT_RED);

    /* green via HSI: H=120 */
    static const uint8_t WANT_GREEN[] =
        { 0x02, 0x00, 0x64, 0x00, 0x78, 0x00, 0x64, 0x00, 0x64, 0x00 };
    n = oly_rgb_hsi(0, 255, 0, -1, b, sizeof b);
    check("green-hsi", b, n, WANT_GREEN, sizeof WANT_GREEN);

    /* blue via HSI: H=240 */
    static const uint8_t WANT_BLUE[] =
        { 0x02, 0x00, 0x64, 0x00, 0xF0, 0x00, 0x64, 0x00, 0x64, 0x00 };
    n = oly_rgb_hsi(0, 0, 255, -1, b, sizeof b);
    check("blue-hsi", b, n, WANT_BLUE, sizeof WANT_BLUE);

    /* CCT 5600K/100%: 01 00 64 38 00 00 00 00 00 01 */
    static const uint8_t WANT_CCT[] =
        { 0x01, 0x00, 0x64, 0x38, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01 };
    n = oly_cct(5600, 100, b, sizeof b);
    check("cct5600", b, n, WANT_CCT, sizeof WANT_CCT);

    /* HSI diretto H=120: 02 00 64 00 78 00 64 00 00 01 */
    static const uint8_t WANT_HSI[] =
        { 0x02, 0x00, 0x64, 0x00, 0x78, 0x00, 0x64, 0x00, 0x00, 0x01 };
    n = oly_hsi(120, 100, 100, b, sizeof b);
    check("hsi120", b, n, WANT_HSI, sizeof WANT_HSI);

    /* effect Flash (id 1): 03 01 64 00 00 00 00 00 00 08 */
    static const uint8_t WANT_FX[] =
        { 0x03, 0x01, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08 };
    n = oly_effect(1, 100, 8, b, sizeof b);
    check("fx-flash", b, n, WANT_FX, sizeof WANT_FX);

    /* buffer too small must fail cleanly */
    {
        uint8_t tiny[3];
        if (oly_open(tiny, sizeof tiny) != 0) {
            printf("[FAIL] small-buffer not rejected\n");
            fails++;
        } else {
            printf("[ok]   small-buffer rejected\n");
        }
        if (oly_rgb_hsi(255, 0, 0, -1, tiny, sizeof tiny) != 0) {
            printf("[FAIL] small-buffer mode10 not rejected\n");
            fails++;
        } else {
            printf("[ok]   small-buffer mode10 rejected\n");
        }
    }

    /* effect lookup */
    if (oly_effect_find("police") != 7 || oly_effect_find("Nope") != -1) {
        printf("[FAIL] effect_find\n");
        fails++;
    } else {
        printf("[ok]   effect_find\n");
    }

    /* true OFF: red-hsi with mode byte forced to 0 */
    {
        uint8_t prev[10], off[10];
        static const uint8_t WANT_OFF[] =
            { 0x00, 0x00, 0x64, 0x00, 0x68, 0x01, 0x64, 0x00, 0x64, 0x00 };
        oly_rgb_hsi(255, 0, 0, -1, prev, sizeof prev);
        n = oly_mode_off(prev, off, sizeof off);
        check("mode-off", off, n, WANT_OFF, sizeof WANT_OFF);
        if (oly_mode_off(0, off, sizeof off) != 0) {
            printf("[FAIL] mode_off NULL not rejected\n");
            fails++;
        } else {
            printf("[ok]   mode_off NULL rejected\n");
        }
    }

    printf(fails ? "RESULT: FAIL (%d)\n" : "RESULT: ALL OK\n", fails);
    return fails ? 1 : 0;
}

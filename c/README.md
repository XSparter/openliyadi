# openliyadi — libreria C (MIT)

Implementazione C99 del protocollo, zero dipendenze, zero allocazioni
(tutti i builder scrivono in un buffer del chiamante). Stessi vettori
verificati byte-a-byte con `led_protocol.py`.

La libreria produce **solo i pacchetti**: il trasporto BLE resta alla
piattaforma (es. Android `BluetoothGatt`, iOS CoreBluetooth, BlueZ, …).
Scrivere i byte su service `FFF0` / caratteristica `FFF3`
(`0000FFF3-0000-1000-8000-00805F9B34FB`), notifiche su `FFF4`.

## Build

```bash
gcc -std=c99 -Wall -Wextra -o example example.c openliyadi.c
clang -std=c99 -Wall -Wextra -o example example.c openliyadi.c
cl /W4 /std:clatest example.c openliyadi.c   # MSVC
./example   # self-test, exit 0 se tutto combacia
```

## API (estratto)

```c
uint8_t oly_checksum(uint8_t cmd, const uint8_t *payload, size_t len);
size_t  oly_build(uint8_t cmd, const uint8_t *payload, size_t len,
                  uint8_t *out, size_t out_sz);   /* ritorna byte scritti */

size_t oly_open(uint8_t *out, size_t out_sz);
size_t oly_close(uint8_t *out, size_t out_sz);
size_t oly_light(uint8_t area, uint8_t brightness, uint8_t *out, size_t out_sz);
size_t oly_palette(uint8_t area, uint8_t r, uint8_t g, uint8_t b, ...);
size_t oly_mode10(...);            /* raw 10 byte */
size_t oly_cct(int kelvin, int brightness, ...);
size_t oly_hsi(int hue, int sat, int bri, ...);   /* hue 0 -> 360 */
size_t oly_rgb_hsi(uint8_t r, uint8_t g, uint8_t b, int brightness, ...);
size_t oly_effect(int id_1_24, int brightness, int speed, ...);
int    oly_effect_find(const char *name);         /* id o -1 */
void   oly_rgb_to_hsv(...);
```

Tutti i builder ritornano i byte scritti, `0` se il buffer è troppo piccolo
(`OLY_BUF_SIZE` = 12 basta per qualunque pacchetto).

## Note Android (JNI)

Due strade:
1. **Solo byte via JNI**: esporre `oly_rgb_hsi`/`oly_cct`/… come `jbyteArray`
   e usare `BluetoothGatt.writeCharacteristic` in Kotlin/Java (consigliato:
   meno codice nativo, debug facile).
2. **GATT in C**: possibile ma ogni stack BLE Android passa comunque da Java;
   non ne vale la pena.

Documentazione completa del protocollo: `../PROTOCOL.md`.

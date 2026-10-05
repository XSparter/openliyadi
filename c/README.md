# openliyadi — libreria C (MIT)

Implementazione C99 del protocollo Liyadi/LEDLYD, **zero dipendenze, zero
allocazioni**: tutti i builder scrivono in un buffer del chiamante.
Stessi vettori verificati byte-a-byte con `led_protocol.py` (vedi `example.c`).

La libreria produce **solo i pacchetti**: il trasporto BLE resta al tuo
progetto (Android, iOS, desktop, ESP32, …). Scrivi i byte su service `FFF0` /
caratteristica `FFF3` (`0000FFF3-0000-1000-8000-00805F9B34FB`), notifiche su `FFF4`.

## Integrare in un progetto personale

Copia `openliyadi.h` + `openliyadi.c` nel tuo sorgente e includi l'header.
Niente build system richiesto (ma vedi sotto per CMake).

```c
#include "openliyadi.h"

uint8_t pkt[OLY_BUF_SIZE];   /* 12 byte bastano per qualunque pacchetto */
size_t n;

/* Accendi */
n = oly_open(pkt, sizeof pkt);          /* -> AA 0B 01 00 B6, n == 5 */
gatt_write(FFF3_HANDLE, pkt, n);        /* la tua funzione di scrittura BLE */

/* Rosso (via HSI, il percorso del color picker: H=360, il firmware scarta H=0) */
n = oly_rgb_hsi(255, 0, 0, -1, pkt, sizeof pkt);  /* brightness -1 = V del colore */

/* Bianco studio 5600K al 100% */
n = oly_cct(5600, 100, pkt, sizeof pkt);

/* Effetto Flash n.1, velocita' 8 */
n = oly_effect(1, 100, 8, pkt, sizeof pkt);

/* Spegni davvero: ripete l'ultimo pacchetto modo con mode=0.
   (CLOSE_CODE headed dimmera soltanto, non spegne.) */
uint8_t last[10]; /* conserva l'ultimo mode10 inviato */
memcpy(last, pkt, 10);
...
n = oly_mode_off(last, pkt, sizeof pkt);
```

Ogni builder ritorna i byte scritti, oppure `0` se il buffer è troppo piccolo
o l'id effetto non esiste: controlla sempre il ritorno.

```c
if (oly_rgb_hsi(r, g, b, -1, pkt, sizeof pkt) == 0) { /* errore */ }
```

## API completa

```c
/* Base */
uint8_t oly_checksum(uint8_t cmd, const uint8_t *payload, size_t len);
size_t  oly_build(uint8_t cmd, const uint8_t *payload, size_t len,
                  uint8_t *out, size_t out_sz);

/* Comandi brevi headed [AA CMD LEN ... CHK] */
size_t oly_open(uint8_t *out, size_t out_sz);
size_t oly_close(uint8_t *out, size_t out_sz);          /* NOTA: dimmera, non spegne */
size_t oly_light(uint8_t area, uint8_t brightness, ...);/* area 0=globale */
size_t oly_speed(uint8_t area, uint8_t speed, ...);
size_t oly_fixed_mode(uint8_t area, uint8_t mode, ...);
size_t oly_palette(uint8_t area, uint8_t r, uint8_t g, uint8_t b, ...);
size_t oly_diy_seg(t, total, index, a, r, g, b, ...);   /* segmenti + ACK, vedi PROTOCOL.md */
size_t oly_music_seg(t, total, index, a, r, g, b, ...);
size_t oly_mic(uint8_t a, uint8_t b, ...);
size_t oly_device_switch(uint8_t a, uint8_t b, ...);
size_t oly_rgb_switch(uint8_t area, uint8_t on_off, ...);
size_t oly_pwm(uint8_t area, uint8_t v, ...);

/* Modi raw a 10 byte (senza header/checksum) */
size_t oly_mode10(mode, modsub, p, k, h, s, flashmod, tnum, freq, ...);
size_t oly_cct(int kelvin_2500_8500, int brightness, ...);
size_t oly_hsi(int hue, int sat, int bri, ...);
size_t oly_rgb_hsi(uint8_t r, uint8_t g, uint8_t b, int brightness, ...);
void   oly_rgb_to_hsv(uint8_t r, uint8_t g, uint8_t b, int *h, int *s, int *v);
size_t oly_mode_off(const uint8_t prev10[10], uint8_t *out, size_t out_sz);

/* Effetti 1..24 (tabella OLY_EFFECTS: id, nome, categoria, modsub) */
size_t oly_effect(int id, int brightness, int speed, ...);
int    oly_effect_find(const char *name);   /* case-insensitive, -1 se assente */
```

Costanti utili: `OLY_SVC_FFF0`, `OLY_CHR_TX`, `OLY_CHR_RX` (stringhe UUID),
`OLY_NAMES[]` (nomi advertising), `OLY_BUF_SIZE` (12).

## Esempi per piattaforma

### Android (Kotlin, consigliato: byte via JNI, GATT in Kotlin)

```kotlin
// 1. Genera i byte in C via JNI (o porta oly_rgb_hsi: sono 10 byte facili)
// 2. Scrivili con il tuo BluetoothGatt:
gatt.getService(UUID.fromString("0000FFF0-0000-1000-8000-00805F9B34FB"))
    ?.getCharacteristic(UUID.fromString("0000FFF3-0000-1000-8000-00805F9B34FB"))
    ?.let {
        it.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
        it.value = byteArrayOf(0x02, 0x00, 0x64, 0x00, 0x68, 0x01, 0x64, 0x00, 0x64, 0x00) // rosso
        gatt.writeCharacteristic(it)
    }
// Abilita le notifiche su ...FFF4 per gli stati/ACK.
```

### ESP32 / embedded (NimBLE, Bluedroid, ArduinoBLE)

I pacchetti sono ≤ 11 byte: stanno in un singolo write GATT, nessun chunking.
Chiama `oly_*` al bisogno (stack: poche decine di byte) e passa il buffer a
`ble_gattc_write_*` / `characteristic->writeValue()`. Niente `malloc` richiesto.

### Desktop (BlueZ / WinRT / CoreBluetooth)

Stesso principio: `oly_*` → write sulla char `FFF3` dopo aver scoperto il
service `FFF0`. Vedi `example.c` per i vettori attesi.

## CMake (opzionale)

```cmake
add_library(openliyadi STATIC openliyadi.c)
target_include_directories(openliyadi PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
```

## Self-test

```bash
gcc -std=c99 -Wall -Wextra -o example example.c openliyadi.c && ./example
# cl /W4 /std:clatest example.c openliyadi.c   (MSVC)
```

Deve stampare `RESULT: ALL OK` (8 vettori noti + gestione buffer corti).

## Regole pratiche (imparate sul campo)

- La lampada accetta **una sola connessione**: chiudi app/nRF del telefono.
- Il MAC è **random e ruota**: riscopri via nome (`LTF_MWRGB`…) o sonda GATT (`FFF0`).
- Colori sempre via **HSI**, mai PALETTE headed (ignorato in modo CCT).
- Spegni con **mode-OFF** (`oly_mode_off`), non con CLOSE.
- Documentazione completa del protocollo: [`../PROTOCOL.md`](../PROTOCOL.md).

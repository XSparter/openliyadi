# Protocollo lampade Liyadi / LEDLYD (LP540-PRO e compatibili)

Reverse engineering dell'app Android `LED.apk` (LEDLYD v2.0.15, uni-app
`__UNI__6FB700B`, logica in `assets/apps/__UNI__6FB700B/www/app-service.js`)
+ verifiche dal vivo con nRF Connect e script Python/WinRT.
Ogni affermazione sotto è confermata dal codice o dal vivo.

## 1. Trasporto BLE

| Voce | Valore |
|---|---|
| Nomi advertising | `LTF_MWRGB`, `LYD_MWRGB`, `Bough_Systems`, `LYDBough_Systems` |
| Advertising osservato | service `0000FEFF`, nome spesso assente (scan-response rado), MAC random che ruota |
| Service GATT | `0000FFF0-0000-1000-8000-00805F9B34FB` |
| TX telefono→lampada (write) | `0000FFF3-…` props `READ, WRITE, WRITE NO RESPONSE` |
| RX lampada→telefono (notify) | `0000FFF4-…` props `NOTIFY, READ` |
| Altro sullo stesso service | `FFF1` R/W/WNR, `FFF2` R, `FFF5` NOTIFY/WRITE, `FFF6` R (uso non necessario) |
| Connessioni | **una sola** alla volta; con telefono/app connessi il PC non entra |
| Bonding | non richiesto (lampada `NOT BONDED`, funziona senza pairing) |

Nota: i service in advertising (`FEFF`) sono diversi da quelli GATT (`FFF0`).
Per trovare la lampada senza nome: connettersi e cercare `FFF0` in GATT.

## 2. Pacchetti brevi (header `0xAA`)

Formato: `[0xAA, CMD, LEN, payload…, CHECKSUM]`

```
CHECKSUM = (0xAA + CMD + LEN + sum(payload)) & 0xFF
```

Riferimento: `common/msg-helper.js`, `u(t,e)`, `p(t)` (ArrayBuffer), invio con
`bluetooth/sendMsg` → `writeBLECharacteristicValue` su `FFF3`, nessun chunking.

| CMD | Nome | Payload | Esempio live |
|---|---|---|---|
| 1 | LIGHT | `[area, brightness 0-100]` | `AA 01 02 00 64 11` (100%) |
| 2 | SPEED | `[area, speed 0-100]` | — |
| 3 | FIXED_MODE | `[area, mode]` | — |
| 4 | PALETTE | `[area, R, G, B]` | `AA 04 04 00 FF 00 00 B1` (rosso) |
| 5 | DIY_MODE | `[t, total, index, a, R, G, B]` (segmentato, con ACK, vedi §5) | — |
| 6 | MUSIC_MODE | come DIY | — |
| 7 | MIC_SET | `[a, b]` | — |
| 8 | DEVICE_SWITCH | `[a, b]` | — |
| 9 | RGB_SWITCH | `[area, on/off]` (power zone, usato dal toggle HSI) | — |
| 10 | SET_PWM | `[area, v 0-100]` | — |
| 11 | OPEN_CODE | `[0]` → `AA 0B 01 00 B6` (accendi) | live OK |
| 12 | CLOSE_CODE | `[0]` → `AA 0C 01 00 B7` (spegni) | live OK |

`area`: 0 = globale, 1/2 = zone. Il comando 4 (PALETTE) **non ha chiamanti
nella UI** e in modo CCT viene ignorato: i colori passano dal §3.

## 3. Pacchetti modo raw a 10 byte (senza header/checksum)

Inviati così come sono su `FFF3` (`cctMode`/`hsiMode`/`effMode`/`paletteMode`).

```
[mode, modsub, P, K, H_lo, H_hi, S, flashmod, Tnum, Freq]
```

| Byte | Significato |
|---|---|
| mode | 0 OFF, 1 CCT, 2 HSI, 3 effetti (MLM), 4 APP |
| modsub | sotto-modo / id effetto 1–24 (clamp lampada: 0→1, >24→24) |
| P | potenza/luminosità 0–100 |
| K | kelvin/100 (es. 56 = 5600 K); significativo solo in modo CCT |
| H | hue 0–360 little-endian; **H=0 scartato dal firmware → rosso = 360** |
| S | saturazione 0–100 |
| flashmod / Tnum / Freq | parametri effetto (default app: 0 / 100 / 0) |

Il color picker chiama `changeColor → hsiMode()`: qualunque RGB va convertito
in HSV e mandato come modo 2. Conversione: H 0–360, S/V in %; V→P (se non
specificata altra luminosità); H=0→360.

Esempi live:
- rosso `02 00 64 00 68 01 64 00 64 00` (H=0x168=360)
- verde `02 00 64 00 78 00 64 00 64 00` (H=120)
- blu `02 00 64 00 F0 00 64 00 64 00` (H=240)
- bianco `02 00 64 00 00 00 00 00 64 00` (S=0)
- CCT 5600K `01 00 64 38 00 00 00 00 00 01`

## 4. Effetti di scena (24)

`LIST_EFF` dell'app: Flash, Flash2, TV, Candle, Flame1, Flame2, Police, AMB,
FireTruck, Strobe1–3, Chase1–3, Firework1–3, Club1–2, Romantic, Music, Wave1–2.
Pacchetto: modo 3 + modsub (tabella in `led_protocol.EFFECTS` / `OLY_EFFECTS`),
P = luminosità, Freq = velocità 1–20. Tutti i 24 testati dal vivo.

## 5. DIY / musica (segmentati, con ACK)

Un pacchetto headed (cmd 5/6) per segmento `[t, total, index, a, R, G, B]`.
Dopo ogni invio l'app attende su notify la risposta
`[0xAA, CMD+0x80, 02, payload[5], 01, checksum]` (confronto su stringhe
`join(",")` in `notifyList`, max 50 voci). Non implementato nei client
(serve solo per DIY/musica).

## 6. Notifiche di stato (RX su `FFF4`)

- Pacchetti brevi con primo byte ≠ 5: stato ON/OFF, zone, valori
  (`P=s[2]`, zone `s[1]`, 16-bit `256*s[5]+s[4]`).
- Pacchetti `0x05` (13 byte): stato effetti con H a 16 bit anche in
  `256*s[12]+s[11]`, K in `s[10]`. L'app vi allinea `mod/modsub/P/K/H/S/…`.

## 7. Comportamenti firmware osservati

- H=0 ignorato (rosso solo come H=360).
- PALETTE headed ignorato in modo CCT; nessun OPEN richiesto davanti ai
  pacchetti modo (l'app non lo manda in `changeColor`).
- **Spegnimento vero = pacchetto modo con primo byte 0** (l'app manda lo stato
  corrente con `mode` forzato a `OFF_CODE` quando `onoffs=false`); il
  `CLOSE_CODE` headed (`AA 0C 01 00 B7`) riduce solo la luminosità.
   Senza stato noto va bene `[00,00,80,56,0,0,0,0,100,0]` (stile CCT).
- Advertising rado (~20–30 s), MAC random non risolvibile che ruota.
- Una connessione alla volta; GATT raggiungibile solo a slot libero.
- K fuori dal modo CCT è ignorato (verificato K=0 e K=56).

## 8. Riferimenti nel codice originale

- Costanti: `e.MSG_HEAD=170`, `e.MSG_CODE={…}`, `e.BLE={…}` (service/TX/RX/nomi).
- Checksum/invio: `u(t,e)`, `p(t)`, `g(t)`, `_(e)` + `h(t,e)` per gli ACK.
- UI: `changeColor→cctMode/hsiMode/effMode`, power→`RGBSwitch`, `open()/clone()`
  per ON/OFF, lista device con `deviceId.substr(-2)`.
- Store BLE: `store/modules/bluetooth.js` (scansione filtrata per nome+`FFF0`,
  `createBLEConnection` timeout 6 s, notify su `FFF4`, `ADD_NOTIFY`).

## 9. Implementazioni in questo repo

- Python: `led_protocol.py` (pacchetti), `led_controller.py` (client Windows
  WinRT persistente), `led_lyd.py` (CLI bleak multipiattaforma).
- C99: `c/openliyadi.{h,c}` (stessi vettori, verificati byte-a-byte),
  `c/example.c` (self-test).

# AGENT.md — Contesto per un'altra IA

## 1. Obiettivo del progetto
Controllare da PC (Python + BLE) una luce RGB gestita dall'app Android `LED.apk`
(app **LEDLYD v2.0.15**, azienda produttrice fallita — nessun cloud, tutto locale via BLE).
Directory di lavoro: `E:\AltriDocumenti\ProgettieSviluppo\Script\Python\liyadifoto`

## 2. File presenti
- `LED.apk` (~20 MB) — app originale (uni-app DCloud, id `__UNI__6FB700B`).
- `led_lyd.py` — script Python (dipendenza: `pip install bleak`) che implementa il protocollo.
  Comandi: `scan | on | off | rgb R G B | brightness N | speed N | fixedmode M | raw HEX`
  Opzioni: `--addr MAC` (va PRIMA del comando), `--listen/--no-listen`.
  Esempio: `python led_lyd.py --addr 12:22:33:44:70:E0 rgb 0 255 0`

## 3. Cosa si sa dall'APK (verificato leggendo il JS, non a intuito)
- APK scompattato con `Expand-Archive`; logica in
  `assets/apps/__UNI__6FB700B/www/app-service.js` (bundle webpack minificato, 358705 byte).
- Costanti (offset ~172855, modulo con `e.MSG_HEAD=170`):
  `HEAD=0xAA (170)`, `RES_CODE=128`,
  `MSG_CODE = {LIGHT:1, SPEED:2, FIXED_MODE:3, PALETTE:4, DIY_MODE:5, MUSIC_MODE:6,
  MIC_SET:7, DEVICE_SWITCH:8, RGB_SWITCH:9, SET_PWM:10, OPEN_CODE:11, CLOSE_CODE:12,
  OFF_CODE:0, CCT_CODE:1, HSI_CODE:2, MLM_CODE:3, APP_CODE:4}`
- BLE: nomi `LTF_MWRGB / LYD_MWRGB / Bough_Systems / LYDBough_Systems`,
  service `0000FFF0-…`, TX write `…FFF3`, RX notify `…FFF4`.
- Filtro scansione app: `startBluetoothDevicesDiscovery({services: FFF0})` +
  match sottostringa sui 4 nomi; lista UI mostra `deviceId.substr(-2)` + MAC completo.
- Il plugin nativo `ibe` (`com.example.ibe`) fa SOLO advertising dal telefono
  (`openBlue`/`stopAdvertising`) — non invia comandi alla lampada. Unica via di
  controllo = GATT FFF0/FFF3/FFF4.

## 4. Protocollo byte-level (confermato)
- Pacchetti brevi: `[0xAA, CMD, LEN, ...payload..., CHK]`,
  `CHK = (0xAA + CMD + LEN + sum(payload)) & 0xFF` (funzione `u(t,e)` in `common/msg-helper.js`).
- `OPEN=[AA,0B,01,00,B6]`, `CLOSE=[AA,0C,01,00,B7]`,
  `RGB(area,R,G,B)=[AA,04,04,area,R,G,B,CHK]`,
  `LIGHT(area,0-100)=[AA,01,02,area,val,CHK]`, SPEED/ FIXED_MODE analoghi a 2 byte.
- Pacchetti modo CCT/HSI/effetto = **10 byte GREZZI senza header/checksum**:
  `[mode, modsub, P, K, H_low, H_high, S, flashmod, Tnum, Freq]` (H little-endian).
  Stato effeti app = `[5, modsub, P, dc/100, H_lo, H_hi, S, modebits, T, freq]`.
- DIY/music = pacchetti `[AA,05|06,07,t,total,idx,a,R,G,B,CHK]` con attesa ACK su notify
  (`sendMsgs` confronta `notifyList` con `[AA, CMD+0x80, 02, a[5], 01, CHK]`).
- `sendMsg` dello store = `writeBLECharacteristicValue` diretta su FFF3, nessuno chunking.
- Vettori noti buoni: rosso `AA040400FF0000B1`, verde `AA04040000FF00B1`,
  blu `AA0404000000FFB1`, brightness 100 `AA01020064 11`.

## 5. Verifiche live già fatte (via nRF Connect dal telefono)
- Connessione a `12:22:33:44:70:E0` (nome `LTF_…`): servizio `0xFFF0` presente con
  `FFF1 (R/W/WNR)`, `FFF2 (R)`, `FFF3 (R/W/WNR)`, `FFF4 (NOTIFY/R)`, `FFF5 (NOTIFY/W)`, `FFF6 (R)`.
- Scrittura `AA0B0100B6` su FFF3 → lampada **accesa**; scrittura colore → **colore cambiato**.
  ⇒ protocollo e trasporto confermati al 100% dal vivo.

## 6. Problema aperto: connessione BLE dal PC (Windows + bleak 3.0.2)
- La lampada accetta **1 sola connessione** (se telefono/nRF connessi, il PC non entra).
- Advertising **rado** (~ogni 20–30 s), service `0000FEFF`, nome spesso assente
  (lo scan-response con il nome arriva di rado); dopo il reboot il MAC random cambia.
- Sintomi: `BleakDeviceNotFoundError` (cache Windows scade tra scan e connect),
  `TimeoutError` anche con race ADV→connect immediato usando l'oggetto BLEDevice.
- `led_lyd.py` implementa già: tentativo diretto → race su ADV fresco (fino a ~120 s),
  write con fallback `response=False→True`, notify RX, disconnect finale.
- Una volta il PC si è connesso per un attimo durante i tentativi → il link è possibile,
  solo instabile. Ipotesi da esplorare: pairing/bonding da Impostazioni Windows,
  dongle BT con antenna migliore, PC più vicino, Moments di ADV veloce post-reboot.

## 8. Stato open-source (ottobre 2026)
Lampada identificata: **Liyadi LP540-PRO** (famiglia LTF_MWRGB/LYD_MWRGB presumibilmente compatibile).
Repo pubblicato come MIT con: `README.md`, `requirements.txt`, `LICENSE`,
`led_scan.py` (scanner: lampade certe via nome/FFF0, FEFF-only = "sospetta"),
`server.py` fixato (`mac_address`, era `target_address`).
Colori via HSI raw (`pkt_rgb_hsi`), hue 1-360 (rosso=360, H=0 scartato dal firmware).
Tabella effetti modsub testata dal vivo: tutti i 24 rispondono.

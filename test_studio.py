import asyncio
from openliyadi.controller import LEDController

async def test_full_controller():
    c = LEDController()  # auto-scoperta: scan + sonda GATT
    print("Connessione con LEDController...")
    await c.connect()
    
    print("1. Accensione (ON)...")
    await c.turn_on()
    await asyncio.sleep(1.0)
    
    print("2. CCT Caldo (3200K, 100% luminosita)...")
    await c.set_cct(3200, 100)
    await asyncio.sleep(2.0)
    
    print("3. CCT Freddo / Daylight (5600K, 100% luminosita)...")
    await c.set_cct(5600, 100)
    await asyncio.sleep(2.0)
    
    print("4. Colore Viola / Magenta RGB...")
    await c.set_rgb(255, 0, 180)
    await asyncio.sleep(2.0)

    print("5. Effetto Flash...")
    await c.set_effect("Flash", brightness=100, speed=8)
    await asyncio.sleep(3.0)

    print("6. Ritorno a luce bianca neutra 4000K...")
    await c.set_cct(4000, 80)
    await asyncio.sleep(1.0)
    
    await c.stop()
    print("[TEST COMPLETATO CON SUCCESSO]")

if __name__ == "__main__":
    asyncio.run(test_full_controller())

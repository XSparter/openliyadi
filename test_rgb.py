import asyncio
from led_controller import LEDController

async def test():
    c = LEDController("12:22:33:44:70:E0")
    await c.connect()
    
    print("Test RGB: ROSSO puro...")
    await c.set_rgb(255, 0, 0)
    await asyncio.sleep(2.0)

    print("Test RGB: VERDE puro...")
    await c.set_rgb(0, 255, 0)
    await asyncio.sleep(2.0)

    print("Test RGB: BLU puro...")
    await c.set_rgb(0, 0, 255)
    await asyncio.sleep(2.0)

    print("Test CCT: Daylight 5600K...")
    await c.set_cct(5600, 100)
    await asyncio.sleep(2.0)

    print("Test RGB: ARANCIONE da CCT...")
    await c.set_rgb(255, 100, 0)
    await asyncio.sleep(2.0)

    await c.stop()
    print("[OK] Test RGB completato!")

asyncio.run(test())

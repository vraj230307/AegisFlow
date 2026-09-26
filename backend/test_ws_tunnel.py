import asyncio
import websockets

async def main():
    async with websockets.connect("wss://sweet-roses-win.loca.lt/ws/pipeline") as ws:
        msg = await ws.recv()
        print("WS RECEIVED:", msg[:100])

if __name__ == "__main__":
    asyncio.run(main())

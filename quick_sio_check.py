import asyncio, socketio, requests

#BASE = "http://localhost:8001"
BASE = "https://cozii.onrender.com"

async def main():
    # Login to get token
    r = requests.post(f"{BASE}/api/auth/login", json={"email":"test@cozii.app","password":"test1234"})
    token = r.json()["token"]
    print(f"token={token[:20]}...")

    sio = socketio.AsyncClient(logger=False, engineio_logger=False)
    hello_evt = asyncio.Event()
    hello_data = {}

    @sio.on("hello")
    async def on_hello(data):
        hello_data.update(data)
        hello_evt.set()

    try:
        await sio.connect(BASE, socketio_path="/api/socket.io", auth={"token": token}, transports=["polling","websocket"])
        print(f"connected, sid={sio.sid}")
        try:
            await asyncio.wait_for(hello_evt.wait(), timeout=5)
            print(f"hello received: {hello_data}")
        except asyncio.TimeoutError:
            print("NO hello event received within 5s")
        await sio.disconnect()
    except Exception as e:
        print(f"CONNECT FAILED: {type(e).__name__}: {e}")

asyncio.run(main())

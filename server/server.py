import asyncio
import os
import re
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from telethon import TelegramClient, events
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Load env
load_dotenv()

# --- CONFIGURATION ---
API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'
CHANNEL_USERNAME = 'StakecomDailyDrops'
VALID_KEYS = ["ADMIN-TEST-KEY", "USER-12345"]

# --- CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, key: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[key] = websocket
        print(f"➕ User connected: {key}")

    def disconnect(self, key: str):
        if key in self.active_connections:
            del self.active_connections[key]
            print(f"➖ User disconnected: {key}")

    async def broadcast_drop(self, code: str):
        print(f"📡 Broadcasting code: {code} to {len(self.active_connections)} users")
        message = json.dumps({"type": "DROP", "code": code})
        for key, connection in self.active_connections.items():
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# --- TELEGRAM CLIENT ---
client = TelegramClient('broadcaster_session', API_ID, API_HASH)

@client.on(events.NewMessage(chats=CHANNEL_USERNAME))
async def handler(event):
    text = (event.raw_text or "").replace('\n', ' ')
    codes = re.findall(r'stakecom[a-zA-Z0-9]+', text)
    if not codes:
        codes = re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
    valid_codes = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
    for code in valid_codes:
        print(f"🔥 NEW DROP DETECTED: {code}")
        await manager.broadcast_drop(code)

# --- LIFESPAN HANDLER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Telegram Monitor...")
    await client.start()
    asyncio.create_task(client.run_until_disconnected())
    yield
    print("🛑 Shutting down...")
    await client.disconnect()

app = FastAPI(lifespan=lifespan)

# --- ROUTES ---
@app.get("/")
async def root():
    return {"status": "Stake Broadcaster Online", "users": list(manager.active_connections.keys())}

@app.get("/test-drop/{code}")
async def test_drop(code: str):
    print(f"🧪 Manual test drop triggered: {code}")
    await manager.broadcast_drop(code)
    return {"status": "Broadcasted", "code": code}

@app.websocket("/ws/{license_key}")
async def websocket_endpoint(websocket: WebSocket, license_key: str):
    if license_key not in VALID_KEYS:
        print(f"🚫 Invalid license attempt: {license_key}")
        await websocket.close(code=4003) 
        return

    await manager.connect(license_key, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(license_key)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
import asyncio
import os
import re
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from telethon import TelegramClient, events
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Enable logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"➕ User connected: {key}")

    def disconnect(self, key: str):
        if key in self.active_connections:
            del self.active_connections[key]
            logger.info(f"➖ User disconnected: {key}")

    async def broadcast_drop(self, code: str):
        logger.info(f"📡 Broadcasting code: {code} to {len(self.active_connections)} users")
        message = json.dumps({"type": "DROP", "code": code})
        for key, connection in self.active_connections.items():
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# --- TELEGRAM CLIENT ---
# Note: Ensure the session name matches the one used in login.py
client = TelegramClient('broadcaster_session', API_ID, API_HASH)

@client.on(events.NewMessage(chats=CHANNEL_USERNAME))
async def handler(event):
    text = (event.raw_text or "").replace('\n', ' ')
    codes = re.findall(r'stakecom[a-zA-Z0-9]+', text)
    if not codes:
        codes = re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
    valid_codes = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
    for code in valid_codes:
        logger.info(f"🔥 NEW DROP DETECTED: {code}")
        await manager.broadcast_drop(code)

async def start_telegram():
    logger.info("🚀 Connecting to Telegram...")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("❌ ERROR: Not authorized! Run login.py first.")
        else:
            logger.info("✅ Telegram Monitor Active.")
            await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"❌ Telegram Connection Error: {e}")

# --- LIFESPAN HANDLER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Telegram monitor in the background so it doesn't block FastAPI startup
    tg_task = asyncio.create_task(start_telegram())
    yield
    # Cleanup
    tg_task.cancel()
    await client.disconnect()
    logger.info("🛑 Shutting down...")

app = FastAPI(lifespan=lifespan)

# --- ROUTES ---
@app.get("/")
async def root():
    return {"status": "Stake Broadcaster Online", "users": list(manager.active_connections.keys())}

@app.get("/test-drop/{code}")
async def test_drop(code: str):
    logger.info(f"🧪 Manual test drop triggered: {code}")
    await manager.broadcast_drop(code)
    return {"status": "Broadcasted", "code": code}

@app.websocket("/ws/{license_key}")
async def websocket_endpoint(websocket: WebSocket, license_key: str):
    if license_key not in VALID_KEYS:
        logger.warning(f"🚫 Invalid license attempt: {license_key}")
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
    # Log to 0.0.0.0 so external extensions can connect via public IP
    uvicorn.run(app, host="0.0.0.0", port=8000)